"""UP-8 Schritt 8 — Entfall und Vertretung in die Jahresplanung übernehmen.

Zwei Abnahmen aus dem Plan stehen hier im Mittelpunkt:
`test_pinned_slot_bleibt_unveraendert_und_wird_gemeldet` und
`test_ganztaegiger_ausfall_ergibt_eine_meldung`.
"""
from datetime import date, timedelta

import pytest

from app.calendar.base import Lesson, LessonState
from app.calendar.sync import (
    NOTIZ_MARKER,
    SlotRef,
    SyncPlan,
    apply_sync,
    plan_sync,
)

MONTAG = date(2026, 6, 8)


def slot(period, *, gruppe=1, tag=MONTAG, kategorie="unterricht", pinned=False,
         source="pattern", note=None, sid=None):
    return SlotRef(
        id=sid or f"{gruppe}-{tag}-{period}",
        group_id=gruppe,
        datum=tag,
        start_period=period,
        kategorie=kategorie,
        pinned=pinned,
        source=source,
        note=note,
    )


def stunde(period, state, *, tag=MONTAG, periods=1, covered_by=None,
           covering_for=None, uid="4711"):
    return Lesson(
        date=tag,
        start_period=period,
        periods=periods,
        state=state,
        external_uid=uid,
        covered_by=covered_by,
        covering_for=covering_for,
    )


# ── Kategorien ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "state,erwartet,anpassung",
    [
        (LessonState.REGULAR, "unterricht", False),
        (LessonState.EXAM, "pruefung", False),
        (LessonState.CANCELLED, "ausfall", True),
        (LessonState.SHIFTED, "unterricht", False),
    ],
)
def test_kategorie_und_anpassungsbedarf(state, erwartet, anpassung):
    plan = plan_sync([(1, stunde(3, state))], [slot(3)])
    assert len(plan.changes) == 1
    assert plan.changes[0].nach_kategorie == erwartet
    assert plan.changes[0].anpassung_noetig is anpassung


def test_vertretung_fordert_umplanung_an():
    """Der Kern der Begriffsklärung (§2.1): Aufsicht ist kein Unterricht.

    Slot ja, Inhalt nein — ohne `anpassung_noetig` gälte die Stunde als gehalten, obwohl
    das Stundenziel aussteht.
    """
    plan = plan_sync(
        [(1, stunde(3, LessonState.SUBSTITUTION, covered_by="XYZ"))], [slot(3)]
    )
    änderung = plan.changes[0]
    assert änderung.nach_kategorie == "vertretung"
    assert änderung.anpassung_noetig is True
    assert "XYZ" in änderung.notiz


def test_uebernommene_aufsicht_beruehrt_den_eigenen_plan_nicht():
    """Fremder Unterricht — er erzeugt weder Slot noch Änderung."""
    plan = plan_sync(
        [(1, stunde(3, LessonState.SUBSTITUTION, covering_for="XYZ"))], [slot(3)]
    )
    assert plan.changes == [] and plan.conflicts == []


def test_doppelstunde_deckt_beide_positionen_ab():
    plan = plan_sync(
        [(1, stunde(3, LessonState.CANCELLED, periods=2))], [slot(3), slot(4)]
    )
    assert sorted(c.start_period for c in plan.changes) == [3, 4]


# ── Grenzen des Schreibens (Abnahme) ─────────────────────────────────────────


def test_pinned_slot_bleibt_unveraendert_und_wird_gemeldet():
    """Abnahme aus dem Plan.

    Ein festgehaltener Slot ist eine Entscheidung der Lehrkraft. Der Sync meldet den
    Widerspruch, statt ihn aufzulösen — das Leitprinzip der ganzen Phase.
    """
    plan = plan_sync([(1, stunde(3, LessonState.CANCELLED))], [slot(3, pinned=True)])
    assert plan.changes == []
    assert len(plan.conflicts) == 1
    assert plan.conflicts[0].grund == "pinned"
    assert "geändert wurde nichts" in plan.conflicts[0].beschreibung


def test_manuell_gesetzter_slot_bleibt_unveraendert():
    plan = plan_sync(
        [(1, stunde(3, LessonState.CANCELLED))], [slot(3, source="manual")]
    )
    assert plan.changes == []
    assert plan.conflicts[0].grund == "manual"


def test_eigene_notiz_wird_nicht_ueberschrieben():
    """Datenverlust, den niemand bemerkt — die neue Notiz sähe plausibel aus."""
    plan = plan_sync(
        [(1, stunde(3, LessonState.SUBSTITUTION, covered_by="XYZ"))],
        [slot(3, note="Arbeit zurückgeben!")],
    )
    assert plan.changes[0].notiz is None          # Kategorie ja, Notiz nein
    assert plan.conflicts[0].grund == "fremde_notiz"


def test_eigene_importnotiz_wird_ersetzt():
    """Sonst wäre der Sync nicht idempotent — die Notiz wüchse bei jedem Lauf."""
    alt = f"{NOTIZ_MARKER} Vertreten durch ABC"
    plan = plan_sync(
        [(1, stunde(3, LessonState.SUBSTITUTION, covered_by="XYZ"))],
        [slot(3, note=alt)],
    )
    assert plan.changes[0].notiz == f"{NOTIZ_MARKER} Vertreten durch XYZ"


def test_ohne_slot_wird_nichts_angelegt():
    """Die Planung kennt die Stunde nicht — das ist eine Abweichung, keine Aufgabe."""
    plan = plan_sync([(1, stunde(7, LessonState.CANCELLED))], [slot(3)])
    assert plan.changes == []
    assert plan.conflicts[0].grund == "kein_slot"


def test_slot_ausserhalb_des_abrufzeitraums_bleibt_unberuehrt():
    """Was nicht geprüft wurde, darf auch nicht geändert werden."""
    spaet = MONTAG + timedelta(days=30)
    plan = plan_sync(
        [(1, stunde(3, LessonState.CANCELLED, tag=spaet))],
        [slot(3, tag=spaet)],
        zeitraum=(MONTAG, MONTAG + timedelta(days=4)),
    )
    assert plan.changes == [] and plan.conflicts == []


# ── Zusammenfassung der Meldungen (Abnahme) ──────────────────────────────────


def test_ganztaegiger_ausfall_ergibt_eine_meldung():
    """Abnahme aus dem Plan.

    Ein Wandertag erzeugt sechs Ausfälle. Sechs Meldungen dazu sind kein Bericht, sondern
    eine Wand — die eine Aussage, die zählt, ist „an diesem Tag fand kein Unterricht
    statt".
    """
    stunden = [(1, stunde(p, LessonState.CANCELLED)) for p in range(1, 7)]
    slots = [slot(p) for p in range(1, 7)]
    plan = plan_sync(stunden, slots)
    assert len(plan.changes) == 6           # geschrieben wird jeder Slot einzeln
    assert len(plan.meldungen) == 1         # gemeldet wird einmal
    assert "6 Stunden fallen aus" in plan.meldungen[0]


def test_einzelne_ausfaelle_werden_einzeln_gemeldet():
    """Zwei Ausfälle sind zwei Ereignisse, kein unterrichtsfreier Tag."""
    stunden = [(1, stunde(p, LessonState.CANCELLED)) for p in (1, 3)]
    plan = plan_sync(stunden, [slot(1), slot(3)])
    assert len(plan.meldungen) == 2


def test_ausfaelle_verschiedener_tage_werden_nicht_vermischt():
    dienstag = MONTAG + timedelta(days=1)
    stunden = [
        *[(1, stunde(p, LessonState.CANCELLED)) for p in range(1, 5)],
        (1, stunde(1, LessonState.CANCELLED, tag=dienstag)),
    ]
    slots = [*[slot(p) for p in range(1, 5)], slot(1, tag=dienstag)]
    plan = plan_sync(stunden, slots)
    assert len(plan.meldungen) == 2
    assert any("4 Stunden fallen aus" in m for m in plan.meldungen)


# ── Idempotenz ───────────────────────────────────────────────────────────────


def test_unveraenderte_slots_erzeugen_keinen_schreibvorgang():
    """Ein Sync ohne Neuigkeiten soll keine Änderungshistorie erfinden."""
    plan = plan_sync(
        [(1, stunde(3, LessonState.CANCELLED))], [slot(3, kategorie="ausfall")]
    )
    assert plan.changes and not plan.wirksame_changes


@pytest.mark.asyncio
async def test_apply_schreibt_nur_wirksame_aenderungen():
    class FakeDB:
        def __init__(self):
            self.statements = []
            self.committed = False

        async def execute(self, stmt, params=None):
            self.statements.append(params)

        async def commit(self):
            self.committed = True

    db = FakeDB()
    plan = plan_sync(
        [(1, stunde(3, LessonState.CANCELLED))], [slot(3, kategorie="ausfall")]
    )
    assert await apply_sync(db, plan) == 0
    assert db.statements == [] and not db.committed


@pytest.mark.asyncio
async def test_apply_setzt_kategorie_und_anpassung():
    class FakeDB:
        def __init__(self):
            self.params = []

        async def execute(self, stmt, params=None):
            self.params.append((str(stmt), params))

        async def commit(self):
            pass

    db = FakeDB()
    plan = plan_sync([(1, stunde(3, LessonState.CANCELLED))], [slot(3)])
    assert await apply_sync(db, plan) == 1
    sql, params = db.params[0]
    assert params["kategorie"] == "ausfall"
    assert params["anpassung"] is True
    assert "source = 'import'" in sql


@pytest.mark.asyncio
async def test_leerer_plan_bleibt_folgenlos():
    assert await apply_sync(object(), SyncPlan()) == 0
