"""UP-8 Schritt 5 — die neuen Slot-Felder.

Geprüft wird das **Modell**, nicht die Datenbank (die Migration selbst läuft in der
Integrationsumgebung). Der Wert dieser Tests liegt darin, die Bedeutung der Felder
festzuhalten — vor allem die von `external_uid`, die leicht falsch verstanden wird.
"""
import json
from pathlib import Path

from sqlalchemy import CheckConstraint, Index

from app.calendar.base import SLOT_CATEGORY, LessonState
from app.db.models import GroupWeekPattern, LessonSlot

FIXTURES = Path(__file__).parent / "fixtures"


def _constraint(model, name):
    return next(
        (
            c
            for c in model.__table__.constraints
            if isinstance(c, CheckConstraint) and c.name == name
        ),
        None,
    )


def _index(model, name):
    return next((i for i in model.__table__.indexes if i.name == name), None)


# ── lesson_slots.source ──────────────────────────────────────────────────────


def test_source_hat_die_drei_werte():
    """`pattern` (Generator), `import` (Quelle), `manual` (von Hand)."""
    constraint = _constraint(LessonSlot, "check_ls_source")
    assert constraint is not None
    text = str(constraint.sqltext)
    for wert in ("pattern", "import", "manual"):
        assert wert in text


def test_source_hat_pattern_als_vorgabe():
    """Bestehende Slots stammen vom Generator — sie dürfen nicht als Import gelten,
    sonst überschriebe der Sync sie beim ersten Lauf."""
    spalte = LessonSlot.__table__.columns["source"]
    assert not spalte.nullable
    assert "pattern" in str(spalte.server_default.arg)


def test_slot_kategorien_und_source_sind_getrennte_achsen():
    """`kategorie` sagt, WAS stattfindet; `source`, WOHER der Slot stammt.

    Beide zu vermischen wäre naheliegend („Import-Slot" als Kategorie) und falsch: Ein
    importierter Slot kann jede Kategorie haben.
    """
    kategorien = str(_constraint(LessonSlot, "check_ls_kategorie").sqltext)
    for kategorie in set(SLOT_CATEGORY.values()):
        assert kategorie in kategorien
    assert "import" not in kategorien


# ── lesson_slots.external_uid ────────────────────────────────────────────────


def test_external_uid_ist_optional():
    """Vom Generator erzeugte Slots haben keine — die Spalte muss leer bleiben dürfen."""
    assert LessonSlot.__table__.columns["external_uid"].nullable


def test_external_uid_ist_nicht_eindeutig():
    """Der Punkt, an dem man sich vertun kann.

    `lessonId` identifiziert die Unterrichts**reihe**. In der Aufzeichnung vom 06.08.2026
    teilen sich fünf Perioden dieselbe. Ein Unique-Index darauf wäre falsch und würde beim
    ersten Import einer Doppelstunde brechen.
    """
    index = _index(LessonSlot, "idx_lesson_slots_external")
    assert index is not None and not index.unique


def test_lessonid_ist_in_echten_daten_mehrfach_vergeben():
    """Der Beleg zur Aussage oben — an der aufgezeichneten Woche."""
    woche = json.loads((FIXTURES / "webuntis_week.json").read_text(encoding="utf-8"))
    perioden = [
        eintrag
        for liste in woche["data"]["result"]["data"]["elementPeriods"].values()
        for eintrag in liste
    ]
    haeufigkeit = {}
    for eintrag in perioden:
        haeufigkeit[eintrag["lessonId"]] = haeufigkeit.get(eintrag["lessonId"], 0) + 1
    assert max(haeufigkeit.values()) > 1
    # Die Perioden-`id` wäre eindeutig — taugt aber nicht, weil sie sich beim Neuimport
    # des Stundenplans ändern kann.
    assert len({eintrag["id"] for eintrag in perioden}) == len(perioden)


def test_slot_identitaet_bleibt_datum_und_stunde():
    """Der Index, der die Zeilenidentität trägt, ist unverändert vorhanden."""
    assert _index(LessonSlot, "idx_lesson_slots_group_date") is not None


# ── group_week_patterns.rhythmus ─────────────────────────────────────────────


def test_rhythmus_hat_die_drei_werte():
    text = str(_constraint(GroupWeekPattern, "check_gwp_rhythmus").sqltext)
    for wert in ("woechentlich", "a_woche", "b_woche"):
        assert wert in text


def test_rhythmus_ist_standardmaessig_woechentlich():
    """Bestehende Muster sind wöchentlich — alles andere wäre eine stille Änderung
    am Stundenplan aller Gruppen."""
    spalte = GroupWeekPattern.__table__.columns["rhythmus"]
    assert not spalte.nullable
    assert "woechentlich" in str(spalte.server_default.arg)


def test_unique_index_enthaelt_rhythmus_nicht():
    """Eine Slot-Position gehört zu genau einem Rhythmus.

    Mit `rhythmus` im Index wäre „wöchentlich UND A-Woche" an derselben Position möglich —
    und erzeugte doppelte Slots. Der Preis (A- und B-Woche mit unterschiedlicher Länge)
    ist exotisch, der verhinderte Fall häufiger und teurer.
    """
    index = _index(GroupWeekPattern, "idx_gwp_unique")
    assert index is not None and index.unique
    assert [c.name for c in index.columns] == [
        "group_id", "halbjahr", "weekday", "start_period",
    ]


def test_zustand_zu_kategorie_deckt_alle_slot_erzeugenden_zustaende_ab():
    """Was einen Slot erzeugt, braucht eine Kategorie — sonst scheitert Schritt 8."""
    from datetime import date

    from app.calendar.base import Lesson

    for zustand in LessonState:
        lesson = Lesson(
            date=date(2026, 5, 18), start_period=1, periods=1, state=zustand
        )
        if lesson.creates_slot:
            assert zustand in SLOT_CATEGORY, f"{zustand} erzeugt einen Slot ohne Kategorie"
