"""UP-8 Schritt 13 — Abnahme des Stundenplan-Abgleichs an der echten Aufzeichnung.

Die übrigen Testdateien prüfen jede Regel einzeln, mit von Hand gebauten Stunden. Hier
läuft **eine ganze aufgezeichnete Woche** durch den Abgleich — dieselbe Woche ab dem
06.07.2026, die auch die Adapter-Tests speist.

Der Unterschied ist nicht Redundanz, sondern Blickwinkel: Einzelregeln können alle stimmen
und im Zusammenspiel trotzdem das Falsche tun (eine Verlegung, deren Ursprungsseite als
Ausfall *und* deren Zielseite als Ausfall gilt; eine Vertretung, die im Bündel mit
Ausfällen untergeht). Diese Datei prüft das Ergebnis eines vollständigen Laufs.

Die beiden Abnahmen aus dem Plan:

* ein simulierter Lauf über eine Woche mit `CANCEL`, `SUBSTITUTION` und `SHIFT`;
* Gegenprobe — ein `pinned`-Slot überlebt **alle drei**.
"""
import json
from collections import Counter
from pathlib import Path

import pytest

from app.calendar.base import LessonState
from app.calendar.sync import SlotRef, plan_sync

FIXTURES = Path(__file__).parent / "fixtures"


def _echte_woche():
    """Die aufgezeichnete Woche als Stunden — über den echten Adapter-Parser."""
    from app.calendar.webuntis import WebUntisAdapter, _parse_untis_time

    woche = json.loads((FIXTURES / "webuntis_week.json").read_text(encoding="utf-8"))
    raster = json.loads((FIXTURES / "webuntis_timegrid.json").read_text(encoding="utf-8"))
    starts = sorted(
        {_parse_untis_time(u["startTime"]) for t in raster for u in t["timeUnits"]}
    )
    adapter = WebUntisAdapter.__new__(WebUntisAdapter)
    return adapter._parse_week(woche, starts).lessons


def _gruppen_id(lesson, _register={}):
    """Jede Lerngruppe bekommt eine eigene ID — so wie `match_groups` es täte.

    **Nicht kosmetisch.** Am 06.07. tauschen zwei Klassen ihre Stunden: E72 geht von der
    3. in die 4. Stunde, E06 kommt von der 6. in die 3. An Position „06.07., 3. Stunde"
    liegen damit ein Ausfall *und* ein Verlegungsziel. Wirft man beide in dieselbe Gruppe,
    entsteht eine Kollision, die es in Wirklichkeit nicht gibt — es sind zwei Klassen,
    also zwei Slots. Ein Test, der so etwas erfindet, prüft seine eigene Vereinfachung.
    """
    schluessel = lesson.student_group or (lesson.subject, lesson.class_names)
    return _register.setdefault(schluessel, len(_register) + 1)


def _zugeordnet(lessons):
    return [(_gruppen_id(l), l) for l in lessons]


def _slots(lessons, *, pinned=False):
    """Zu jeder Stunde ein passender Slot — die Jahresplanung ist vollständig gepflegt.

    So wird `kein_slot` als Störgröße ausgeschlossen: Was der Lauf nicht ändert, liegt
    dann an einer Regel und nicht daran, dass die Stelle unbekannt war.
    """
    gesehen = set()
    slots = []
    for l in lessons:
        if not l.creates_slot or l.start_period is None:
            continue
        gid = _gruppen_id(l)
        if (gid, l.date, l.start_period) in gesehen:
            continue
        gesehen.add((gid, l.date, l.start_period))
        slots.append(
            SlotRef(
                id=f"s-{gid}-{l.date}-{l.start_period}",
                group_id=gid,
                datum=l.date,
                start_period=l.start_period,
                kategorie="unterricht",
                pinned=pinned,
                source="pattern",
                note=None,
            )
        )
    return slots


@pytest.fixture(scope="module")
def woche():
    return _echte_woche()


def test_aufzeichnung_enthaelt_alle_drei_zustaende(woche):
    """Wächter für die Abnahme selbst.

    Würde die Aufzeichnung einmal ausgetauscht und enthielte dann keine Vertretung mehr,
    liefen die Tests unten **grün durch, ohne den Fall zu prüfen** — die gefährlichste
    Art von Testerfolg.
    """
    zustaende = Counter(l.state for l in woche)
    assert zustaende[LessonState.CANCELLED] >= 1
    assert zustaende[LessonState.SUBSTITUTION] >= 1
    assert zustaende[LessonState.SHIFTED] >= 1


# ── Abnahme 1: der volle Lauf ────────────────────────────────────────────────


def test_simulierter_lauf_ueber_die_echte_woche(woche):
    """Jede der 13 nicht-regulären Stunden landet in der richtigen Kategorie."""
    plan = plan_sync(_zugeordnet(woche), _slots(woche))

    # Position **einschließlich Gruppe** — sonst verdeckt der Stundentausch am 06.07.
    # die Zuordnung wieder.
    nach_position = {
        (c.group_id, c.datum, c.start_period): c for c in plan.wirksame_changes
    }

    for gid, lesson in _zugeordnet(woche):
        if not lesson.creates_slot or lesson.start_period is None:
            continue
        change = nach_position.get((gid, lesson.date, lesson.start_period))

        if lesson.state is LessonState.CANCELLED:
            assert change is not None, f"Ausfall nicht übernommen: {lesson.date}"
            assert change.nach_kategorie == "ausfall"
            assert change.anpassung_noetig
        elif lesson.state is LessonState.SUBSTITUTION:
            assert change is not None, f"Vertretung nicht übernommen: {lesson.date}"
            assert change.nach_kategorie == "vertretung"
            # Kern der Schulpraxis: Aufsicht ≠ gehaltener Unterricht.
            assert change.anpassung_noetig
        elif lesson.state is LessonState.SHIFTED:
            # Der Ersatztermin findet statt. Eine Änderung wäre hier falsch — der Slot
            # steht bereits auf `unterricht`.
            assert change is None, f"Verlegungsziel angefasst: {lesson.date}"


def test_verlegungen_bleiben_vorschlaege(woche):
    """Kein Verlegungspaar wird still ausgeführt — es wird berichtet.

    Umplanen ist eine pädagogische Entscheidung; der Abgleich bereitet sie nur vor.
    """
    plan = plan_sync(_zugeordnet(woche), _slots(woche))

    assert plan.verlegungen, "Woche enthält Verlegungen, der Plan meldet keine"
    for v in plan.verlegungen:
        assert v.nach_datum is not None and v.nach_stunde is not None
        # Anker ist immer die Ursprungsseite; die Zielseite darf nicht erneut
        # zum Verlegen angeboten werden.
        assert (v.von_datum, v.von_stunde) != (v.nach_datum, v.nach_stunde)


def test_lauf_ist_wiederholbar(woche):
    """Zweiter Lauf auf dem Ergebnis des ersten ändert nichts mehr.

    Der Cron läuft täglich über dieselben Wochen. Bliebe der Abgleich nicht idempotent,
    schriebe er jeden Morgen dieselben Zeilen neu — und die `[Stundenplan]`-Notizen
    wüchsen mit jedem Lauf.
    """
    slots = _slots(woche)
    erst = plan_sync(_zugeordnet(woche), slots)

    # Ergebnis des ersten Laufs auf die Slots anwenden.
    nach_id = {s.id: s for s in slots}
    for change in erst.wirksame_changes:
        alt = nach_id[change.slot_id]
        nach_id[alt.id] = SlotRef(
            id=alt.id, group_id=alt.group_id, datum=alt.datum,
            start_period=alt.start_period, kategorie=change.nach_kategorie,
            pinned=alt.pinned, source="untis",
            note=change.notiz if change.notiz is not None else alt.note,
        )

    zweit = plan_sync(_zugeordnet(woche), list(nach_id.values()))
    assert zweit.wirksame_changes == []


# ── Abnahme 2: Gegenprobe ────────────────────────────────────────────────────


def test_pinned_slots_ueberleben_alle_drei_zustaende(woche):
    """Die Abnahme aus dem Plan, an echten Daten.

    Nicht „ein pinned-Slot bleibt stehen", sondern: **keiner** wird angefasst, und zwar
    bei Ausfall, Vertretung und Verlegung gleichermaßen. Ein Sync, der eine Entscheidung
    der Lehrkraft überschreibt, ist schlimmer als gar keiner — er zerstört Arbeit, die
    niemand automatisch wiederherstellen kann.
    """
    plan = plan_sync(_zugeordnet(woche), _slots(woche, pinned=True))

    assert plan.changes == [], "Ein festgehaltener Slot wurde geändert"

    gemeldet = {
        (k.datum, k.start_period) for k in plan.conflicts if k.grund == "pinned"
    }
    fuer_zustand = {
        zustand: [
            (l.date, l.start_period)
            for l in woche
            if l.state is zustand and l.creates_slot and l.start_period is not None
        ]
        for zustand in (
            LessonState.CANCELLED,
            LessonState.SUBSTITUTION,
            LessonState.SHIFTED,
        )
    }

    for zustand, positionen in fuer_zustand.items():
        assert positionen, f"Kein Fall für {zustand.name} in der Aufzeichnung"
        if zustand is LessonState.SHIFTED:
            # Der Ersatztermin ist bereits `unterricht` — es gibt keinen Widerspruch
            # zu melden. Geändert wird trotzdem nichts, das prüft die Zusicherung oben.
            continue
        fehlend = [p for p in positionen if p not in gemeldet]
        assert not fehlend, f"{zustand.name} nicht als Konflikt gemeldet: {fehlend}"


def test_pinned_und_ungepinnt_unterscheiden_sich_wirklich(woche):
    """Ohne diesen Vergleich könnte die Gegenprobe aus dem falschen Grund grün sein —
    etwa weil der Lauf ohnehin nichts zu tun fand."""
    ohne = plan_sync(_zugeordnet(woche), _slots(woche))
    mit = plan_sync(_zugeordnet(woche), _slots(woche, pinned=True))

    assert len(ohne.wirksame_changes) >= 9  # 7 Ausfälle + 2 Vertretungen
    assert mit.changes == []
