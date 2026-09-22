"""Entfall und Vertretung in die Jahresplanung übernehmen (UP-8, Schritt 8).

Der Abgleich ist **zweistufig**: `plan_sync` rechnet aus, was zu tun wäre — ohne
Datenbank, ohne Seiteneffekt; `apply_sync` führt es aus. Das erlaubt eine Vorschau vor dem
Schreiben und macht die Regeln prüfbar, ohne eine Datenbank aufzusetzen.

**Der Sync ändert Kategorien, keine Inhalte.** Thema, verknüpfte Unterrichtseinheit und
Stunde bleiben unangetastet — was aus einer ausgefallenen Stunde wird, entscheidet die
Lehrkraft im Verschiebe-Dialog aus UP-6. Drei Grenzen sichern das ab:

1. **`pinned` und `source='manual'` werden nie geändert**, nur gemeldet.
2. **Die Notiz wird nur ersetzt, wenn sie vom Import stammt** — erkennbar am Marker.
   Selbstgeschriebene Notizen bleiben, auch wenn sie im Weg stehen.
3. **Ohne passenden Slot wird einer angelegt** — seit dem 22.09.2026, vorher nicht.

   Die alte Regel lautete: „Eine Stunde, für die die Planung keinen Slot kennt, ist eine
   Abweichung — sie wird gemeldet, nicht stillschweigend behoben." Sie hielt der Praxis
   nicht stand. Beobachtet an einer echten Verlegung: Die Hälfte einer Doppelstunde
   wanderte auf einen Termin, an dem die Gruppe sonst keinen Unterricht hat. Der Entfall
   am Ursprung **wurde** geschrieben, der Termin am Ziel nicht — die Planung verlor eine
   Stunde und bekam keine zurück. Als Hinweis gemeint, wirkte es wie stiller Verlust.

   Angelegt wird ein leerer Termin mit `source='import'`; er überlebt damit den
   Neuaufbau eines Halbjahres. **Inhalt verschiebt der Abgleich weiterhin nicht** — er
   stellt nur den Termin bereit, auf den der Verschiebe-Dialog zeigen kann. Alles
   andere wäre ein Automatismus an der Planung, und die gehört der Lehrkraft (Regel 1).

⚠️ **Ein Slot kann mehrere Stunden überspannen.** Der Generator legt eine Doppelstunde
als **eine** Zeile mit `periods=2` an, der Abgleich prüft aber Stunde für Stunde. Ein
Termin gilt deshalb als abgedeckt, wenn ein Slot ihn **überspannt** — nicht nur, wenn
einer dort beginnt. Ohne diese Regel meldete der Abgleich für die zweite Hälfte jeder
Doppelstunde „kein Slot" (bis 22.09.2026 tat er das), und seit Punkt 3 entstünde dort
ein Phantom-Termin.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.calendar.base import SLOT_CATEGORY, Lesson, LessonState

logger = logging.getLogger(__name__)

# Präfix der vom Import geschriebenen Notizen. Nur was damit beginnt, wird überschrieben —
# so bleibt eine selbstgeschriebene Notiz erhalten und der Import trotzdem idempotent.
NOTIZ_MARKER = "[Stundenplan]"

# Ab wie vielen ausgefallenen Stunden an einem Tag zusammengefasst gemeldet wird. Zwei
# Ausfälle sind zwei Ereignisse; ab drei ist es erkennbar ein Tag, an dem etwas anderes
# stattfand (Wandertag, Projekttag) — und sechs Einzelmeldungen wären dann nur Lärm.
_TAGESMELDUNG_AB = 3


@dataclass(frozen=True)
class SlotChange:
    """Eine Änderung an genau einem Slot."""

    slot_id: object
    group_id: int
    datum: date
    start_period: int
    von_kategorie: str
    nach_kategorie: str
    anpassung_noetig: bool
    notiz: str | None
    external_uid: str | None

    @property
    def wirkt(self) -> bool:
        """Ob sich überhaupt etwas ändert — sonst ist der Schreibvorgang überflüssig."""
        return self.von_kategorie != self.nach_kategorie or self.notiz is not None


@dataclass(frozen=True)
class SyncConflict:
    """Etwas, das der Sync **nicht** angefasst hat, und warum."""

    datum: date
    start_period: int | None
    grund: str            # 'pinned' | 'manual' | 'kein_slot' | 'fremde_notiz'
    beschreibung: str


@dataclass(frozen=True)
class ShiftSuggestion:
    """Eine Verlegung, als Vorschlag für den Verschiebe-Dialog aus UP-6 (Schritt 9).

    **Ein Paar ergibt genau einen Vorschlag.** Eine Verlegung steht zweimal in den Daten:
    am Ursprung als `CANCEL` (`isSource = true`), am Ziel als `SHIFT` (`isSource = false`),
    beide mit derselben `lessonId`. Anker ist die **Ursprungsseite** — die Zielseite ist
    bereits das Ergebnis; sie erneut zum Verlegen anzubieten hieße, eine erledigte
    Entscheidung noch einmal zu stellen.
    """

    group_id: int
    slot_id: object | None        # Ursprungs-Slot, falls die Planung ihn kennt
    von_datum: date
    von_stunde: int
    nach_datum: date
    nach_stunde: int | None
    periods: int = 1
    external_uid: str | None = None

    @property
    def rueckwaerts(self) -> bool:
        """Ob die Stunde vorgezogen wurde — kommt vor (beobachtet: 09.07. → 06.07.)."""
        return self.nach_datum < self.von_datum


@dataclass(frozen=True)
class NeuerSlot:
    """Ein Termin, den der Stundenplan kennt und die Planung nicht.

    Entsteht vor allem bei Verlegungen auf einen Tag außerhalb des Wochenmusters. Er wird
    **leer** angelegt — den Inhalt bringt, wenn überhaupt, die Lehrkraft über den
    Verschiebe-Dialog mit.
    """

    group_id: int
    datum: date
    start_period: int
    kategorie: str
    notiz: str | None
    external_uid: str | None


@dataclass
class SyncPlan:
    changes: list[SlotChange] = field(default_factory=list)
    conflicts: list[SyncConflict] = field(default_factory=list)
    verlegungen: list[ShiftSuggestion] = field(default_factory=list)
    anzulegende: list[NeuerSlot] = field(default_factory=list)
    meldungen: list[str] = field(default_factory=list)

    @property
    def wirksame_changes(self) -> list[SlotChange]:
        return [c for c in self.changes if c.wirkt]


@dataclass(frozen=True)
class SlotRef:
    """Der Ausschnitt eines `lesson_slots`-Eintrags, den der Abgleich braucht."""

    id: object
    group_id: int
    datum: date
    start_period: int
    kategorie: str
    pinned: bool
    source: str
    note: str | None
    # Wie viele Stunden dieser Slot belegt. Eine Doppelstunde ist **eine** Zeile mit
    # `periods=2` — ohne diese Angabe hielte der Abgleich die zweite Hälfte für
    # ungedeckt.
    periods: int = 1


def _notiz_fuer(lesson: Lesson) -> str | None:
    """Die Notiz, die der Import setzen würde — oder None, wenn keine nötig ist."""
    if lesson.covered_by:
        return f"{NOTIZ_MARKER} Vertreten durch {lesson.covered_by}"
    return None


def _notiz_darf_geschrieben_werden(vorhanden: str | None) -> bool:
    """Nur leere oder vom Import stammende Notizen werden ersetzt.

    Eine selbstgeschriebene Notiz zu überschreiben wäre Datenverlust — und zwar einer, den
    niemand bemerkt, weil die neue Notiz plausibel aussieht.
    """
    return not (vorhanden or "").strip() or (vorhanden or "").lstrip().startswith(
        NOTIZ_MARKER
    )


def plan_sync(
    lessons: list[tuple[int, Lesson]],
    slots: list[SlotRef],
    *,
    zeitraum: tuple[date, date] | None = None,
) -> SyncPlan:
    """Was der Abgleich ändern würde. Keine Datenbank, kein Seiteneffekt.

    `lessons` sind Paare aus `groups.id` und Stunde — die Zuordnung trifft Schritt 7.
    `zeitraum` begrenzt auf die tatsächlich abgerufenen Tage: Ein Slot außerhalb wurde
    nicht geprüft und darf deshalb auch nicht geändert werden.
    """
    plan = SyncPlan()
    # Jede belegte Stunde zeigt auf ihren Slot — eine Doppelstunde also zweimal auf
    # dieselbe Zeile. Ohne das hielte der Abgleich ihre zweite Hälfte für ungedeckt.
    nach_position = {
        (s.group_id, s.datum, s.start_period + versatz): s
        for s in slots
        for versatz in range(max(1, s.periods))
    }
    # Welche Gruppen für diesen Zeitraum überhaupt eine Planung haben.
    mit_planung = {s.group_id for s in slots}
    # Ein Slot wird **einmal** geändert, auch wenn mehrere Stunden auf ihn zeigen. Bei
    # einer Doppelstunde tun sie das (beide Hälften, eine Zeile mit `periods=2`) — ohne
    # diese Sperre stünde dieselbe Änderung zweimal im Plan und dieselbe Meldung zweimal
    # auf dem Bildschirm.
    behandelte_slots: set = set()
    gesehen: set[tuple[int, date, int]] = set()

    for group_id, lesson in lessons:
        if not lesson.creates_slot or lesson.start_period is None:
            continue
        if zeitraum and not (zeitraum[0] <= lesson.date <= zeitraum[1]):
            continue

        ziel = SLOT_CATEGORY.get(lesson.state)
        if ziel is None:
            continue

        for versatz in range(max(1, lesson.periods)):
            position = (group_id, lesson.date, lesson.start_period + versatz)
            if position in gesehen:
                continue
            gesehen.add(position)
            slot = nach_position.get(position)

            if slot is None:
                # Kein Slot an dieser Stelle: Der Stundenplan kennt hier Unterricht, die
                # Planung nicht. Seit dem 22.09.2026 wird er **angelegt** statt nur
                # gemeldet — sonst verlöre eine Verlegung die Stunde (siehe Modulkopf,
                # Regel 3). Leer: Den Inhalt bringt die Lehrkraft über den
                # Verschiebe-Dialog mit, wenn sie es will.
                if group_id not in mit_planung:
                    # ⚠️ **Die Gruppe hat gar keine Planung.** Dann ist nicht ein Termin
                    # zu ergänzen, sondern das Wochenmuster einzurichten — aus dem
                    # Stundenplan hier ein ganzes Halbjahr anzulegen ginge am
                    # eigentlichen Schritt vorbei und erzeugte Termine, die niemand
                    # bestellt hat. Es bleibt bei der Meldung; die Oberfläche führt
                    # daraus zur Einrichtung (`fehlendesRaster`).
                    plan.conflicts.append(
                        SyncConflict(
                            datum=lesson.date,
                            start_period=lesson.start_period + versatz,
                            grund="kein_slot",
                            beschreibung=(
                                "Für diese Gruppe ist noch keine Planung angelegt — "
                                "zuerst das Wochenmuster einrichten."
                            ),
                        )
                    )
                    continue

                plan.anzulegende.append(
                    NeuerSlot(
                        group_id=group_id,
                        datum=lesson.date,
                        start_period=lesson.start_period + versatz,
                        kategorie=ziel,
                        notiz=_notiz_fuer(lesson),
                        external_uid=lesson.external_uid,
                    )
                )
                continue

            if slot.pinned or slot.source == "manual":
                grund = "pinned" if slot.pinned else "manual"
                warum = "festgehalten" if slot.pinned else "von Hand gesetzt"
                plan.conflicts.append(
                    SyncConflict(
                        datum=slot.datum,
                        start_period=slot.start_period,
                        grund=grund,
                        beschreibung=(
                            f"Slot ist {warum} — Stundenplan meldet "
                            f"{lesson.state.value}, geändert wurde nichts."
                        ),
                    )
                )
                continue

            if slot.id in behandelte_slots:
                continue
            behandelte_slots.add(slot.id)

            notiz = _notiz_fuer(lesson)
            if notiz is not None and not _notiz_darf_geschrieben_werden(slot.note):
                plan.conflicts.append(
                    SyncConflict(
                        datum=slot.datum,
                        start_period=slot.start_period,
                        grund="fremde_notiz",
                        beschreibung=(
                            "Eigene Notiz vorhanden — der Vertretungshinweis wurde nicht "
                            "geschrieben."
                        ),
                    )
                )
                notiz = None

            plan.changes.append(
                SlotChange(
                    slot_id=slot.id,
                    group_id=group_id,
                    datum=slot.datum,
                    start_period=slot.start_period,
                    von_kategorie=slot.kategorie,
                    nach_kategorie=ziel,
                    # Der Kern der Begriffsklärung (§2.1): Ausfall UND Vertretung lassen
                    # das Stundenziel offen — beides fordert Umplanung an.
                    anpassung_noetig=not lesson.delivers_planned_content,
                    notiz=notiz,
                    external_uid=lesson.external_uid,
                )
            )

    plan.verlegungen = _verlegungen(lessons, nach_position, zeitraum)
    plan.meldungen = (
        _meldungen(plan.wirksame_changes)
        + _verlegungsmeldungen(plan.verlegungen)
        + _anlagemeldungen(plan.anzulegende)
    )
    return plan


def _verlegungen(
    lessons: list[tuple[int, Lesson]],
    nach_position: dict,
    zeitraum: tuple[date, date] | None,
) -> list[ShiftSuggestion]:
    """Verlegungen als Vorschläge — einer je Paar, Blöcke zusammengefasst.

    Zwei Filter machen die Liste brauchbar:

    * **Nur die Ursprungsseite** (`is_source`). Die Zielseite trägt dieselbe Information
      spiegelverkehrt; beide zu melden ergäbe doppelte Vorschläge, von denen einer in die
      falsche Richtung zeigt.
    * **Aufeinanderfolgende Stunden derselben Verlegung werden gebündelt.** Beobachtet:
      Eine Doppelstunde wurde als zwei `CANCEL`-Einträge (15:40 und 16:25) mit je eigenem
      `rescheduleInfo` verlegt. Zwei Vorschläge dafür wären zwei Entscheidungen für
      denselben Sachverhalt.
    """
    roh: list[ShiftSuggestion] = []
    for group_id, lesson in lessons:
        info = lesson.reschedule
        if info is None or not info.is_source or lesson.start_period is None:
            continue
        if zeitraum and not (zeitraum[0] <= lesson.date <= zeitraum[1]):
            continue
        slot = nach_position.get((group_id, lesson.date, lesson.start_period))
        roh.append(
            ShiftSuggestion(
                group_id=group_id,
                slot_id=slot.id if slot else None,
                von_datum=lesson.date,
                von_stunde=lesson.start_period,
                nach_datum=info.date,
                nach_stunde=info.start_period,
                periods=max(1, lesson.periods),
                external_uid=lesson.external_uid,
            )
        )

    # Bündeln: gleiche Verlegung (Gruppe, Reihe, Tagespaar), anschließende Stunden.
    roh.sort(key=lambda v: (v.group_id, v.external_uid or "", v.von_datum, v.von_stunde))
    gebuendelt: list[ShiftSuggestion] = []
    for vorschlag in roh:
        if gebuendelt:
            letzter = gebuendelt[-1]
            passt = (
                letzter.group_id == vorschlag.group_id
                and letzter.external_uid == vorschlag.external_uid
                and letzter.von_datum == vorschlag.von_datum
                and letzter.nach_datum == vorschlag.nach_datum
                and letzter.von_stunde + letzter.periods == vorschlag.von_stunde
            )
            if passt:
                gebuendelt[-1] = ShiftSuggestion(
                    group_id=letzter.group_id,
                    slot_id=letzter.slot_id,
                    von_datum=letzter.von_datum,
                    von_stunde=letzter.von_stunde,
                    nach_datum=letzter.nach_datum,
                    nach_stunde=letzter.nach_stunde,
                    periods=letzter.periods + vorschlag.periods,
                    external_uid=letzter.external_uid,
                )
                continue
        gebuendelt.append(vorschlag)
    gebuendelt.sort(key=lambda v: (v.von_datum, v.von_stunde))
    return gebuendelt


def _verlegungsmeldungen(verlegungen: list[ShiftSuggestion]) -> list[str]:
    meldungen = []
    for v in verlegungen:
        umfang = "Doppelstunde" if v.periods == 2 else f"{v.periods} Stunden"
        was = "Stunde" if v.periods == 1 else umfang
        ziel = f"{v.nach_datum}"
        if v.nach_stunde:
            ziel += f", {v.nach_stunde}. Stunde"
        richtung = "vorgezogen auf" if v.rueckwaerts else "verlegt auf"
        meldungen.append(
            f"{v.von_datum}, {v.von_stunde}. Stunde: {was} {richtung} {ziel}."
        )
    return meldungen


def _anlagemeldungen(neue: list[NeuerSlot]) -> list[str]:
    """Angelegte Termine gehören benannt — sie sind eine Änderung an der Planung."""
    if not neue:
        return []
    n = len(neue)
    tage = sorted({x.datum for x in neue})
    wo = f"am {tage[0]}" if len(tage) == 1 else f"an {len(tage)} Tagen"
    return [
        f"{n} {'Stunde' if n == 1 else 'Stunden'} {wo} neu angelegt — der Stundenplan "
        "kennt dort Unterricht, die Planung hatte noch keinen Termin."
    ]


def _meldungen(changes: list[SlotChange]) -> list[str]:
    """Menschenlesbare Zusammenfassung — Tage mit Vollausfall gebündelt.

    Ein Wandertag erzeugt sechs Ausfälle. Sechs Meldungen dazu sind kein Bericht, sondern
    eine Wand; die eine Aussage, die zählt, ist „an diesem Tag fand kein Unterricht statt".
    """
    ausfall_je_tag: dict[date, list[SlotChange]] = defaultdict(list)
    einzeln: list[SlotChange] = []
    for change in changes:
        if change.nach_kategorie == "ausfall":
            ausfall_je_tag[change.datum].append(change)
        else:
            einzeln.append(change)

    meldungen: list[str] = []
    for tag, gruppe in sorted(ausfall_je_tag.items()):
        if len(gruppe) >= _TAGESMELDUNG_AB:
            meldungen.append(
                f"{tag}: {len(gruppe)} Stunden fallen aus — vermutlich ein "
                f"unterrichtsfreier Tag."
            )
        else:
            meldungen.extend(
                f"{c.datum}, {c.start_period}. Stunde: Ausfall." for c in gruppe
            )
    for change in sorted(einzeln, key=lambda c: (c.datum, c.start_period)):
        beschreibung = {
            "vertretung": "wird vertreten (Aufsicht, kein Unterricht)",
            "unterricht": "findet statt",
            "pruefung": "Prüfung",
        }.get(change.nach_kategorie, change.nach_kategorie)
        meldungen.append(
            f"{change.datum}, {change.start_period}. Stunde: {beschreibung}."
        )
    return meldungen


async def apply_sync(db, plan: SyncPlan) -> int:
    """Den Plan ausführen. Gibt die Zahl geänderter **und angelegter** Slots zurück.

    Geschrieben wird nur, was sich tatsächlich ändert — ein Sync ohne Neuigkeiten soll die
    `updated_at`-Zeitstempel nicht durchrütteln und keine Änderungshistorie erfinden.

    Angelegte Termine tragen `source='import'`. Das ist keine Formalie: Der Neuaufbau
    eines Halbjahres löscht nur Muster-Slots, ein importierter überlebt ihn also
    (`app/planning/slot_generator.py`). Ohne diese Herkunft wäre er beim nächsten
    „Stunden erzeugen" wieder weg.
    """
    from sqlalchemy import text

    from app.planning.calendar import load_school_year

    geaendert = 0
    for change in plan.wirksame_changes:
        felder = [
            "kategorie = :kategorie",
            "anpassung_noetig = :anpassung",
            "source = 'import'",
            "external_uid = :uid",
            "updated_at = now()",
        ]
        params = {
            "id": change.slot_id,
            "kategorie": change.nach_kategorie,
            "anpassung": change.anpassung_noetig,
            "uid": change.external_uid,
        }
        if change.notiz is not None:
            felder.append("note = :notiz")
            params["notiz"] = change.notiz
        await db.execute(
            text(f"UPDATE lesson_slots SET {', '.join(felder)} WHERE id = :id"), params
        )
        geaendert += 1
    # Was der Stundenplan kennt und die Planung nicht — leer angelegt, damit der
    # Verschiebe-Dialog ein Ziel hat. Inhalt bringt nur die Lehrkraft dorthin.
    if plan.anzulegende:
        kalender = load_school_year()
        for neu in plan.anzulegende:
            await db.execute(
                text(
                    "INSERT INTO lesson_slots (group_id, date, start_period, periods,"
                    " halbjahr, kategorie, source, external_uid, note)"
                    " VALUES (:gid, :datum, :sp, 1, :hj, :kat, 'import', :uid, :notiz)"
                ),
                {
                    "gid": neu.group_id,
                    "datum": neu.datum,
                    "sp": neu.start_period,
                    # Das Halbjahr steht nicht am Termin, es folgt aus dem Datum.
                    "hj": 1 if neu.datum < kalender.halbjahreswechsel else 2,
                    "kat": neu.kategorie,
                    "uid": neu.external_uid,
                    "notiz": neu.notiz,
                },
            )
            geaendert += 1

    if geaendert:
        await db.commit()
    return geaendert
