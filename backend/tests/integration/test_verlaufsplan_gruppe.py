"""Plan der Fachschaft im Planer einer Gruppe (BD Teil B, Schritt 1). Erfordert TEST_DATABASE_URL.

Welt und Kalender wie in `test_verlaufsplan_endpunkte.py`: laufend ist 2025/26.
"""
import uuid

import pytest

from app.db.models import Group, GroupMembership

from tests.integration.test_verlaufsplan_endpunkte import (  # noqa: F401 — Fixtures
    FS, LK, TOKEN, _anlegen, _client, _person, db, welt,
)

pytestmark = pytest.mark.asyncio

LEHRKRAFT = f"vp-gr-{TOKEN}"


def _gruppen_client(db, user):
    c = _client(db, user)
    from app.planning.verlaufsplan_gruppe_router import router

    c._transport.app.include_router(router)
    return c


async def _gruppe(db, welt, *, jahrgang=9, name=None, fach=True):
    g = Group(name=name or f"9a M {uuid.uuid4().hex[:4]}", slug=f"g-{uuid.uuid4().hex[:8]}",
              type="teaching_group", subject_id=welt["fach"].id if fach else None, jahrgang=jahrgang)
    db.add(g)
    await db.flush()
    db.add(GroupMembership(group_id=g.id, pseudonym=LEHRKRAFT, role_in_group="teacher"))
    await db.flush()
    return g


def _lk():
    return _person(LEHRKRAFT, "teacher")


async def _lesen(db, g, user=None):
    async with _gruppen_client(db, user or _lk()) as c:
        return await c.get(f"/planning/groups/{g.id}/verlaufsplan")


async def test_entwurf_der_stufe_mit_wochen(db, welt):
    plan = (await _anlegen(db, welt)).json()
    g = await _gruppe(db, welt)
    r = await _lesen(db, g)
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["schuljahr"], d["stufe"], d["grund"]) == ("2025/26", 9, None)
    assert d["plan"]["id"] == plan["id"] and d["plan"]["status"] == "draft"
    # Eine Lehrkraft der Gruppe ist nicht in der Fachschaft: lesen ja, bearbeiten nein
    assert not d["plan"]["darf_bearbeiten"]
    # 4 + 6 Wochen; Woche 1 beginnt am 15.09.2025 (KW 38), die Herbstferien liegen nach Woche 6
    woche = d["abschnitt_je_woche"]
    assert len(woche) == 10
    assert woche["2025-W38"] == 0 and woche["2025-W41"] == 0 and woche["2025-W42"] == 1
    assert "2025-W44" not in woche  # Herbstferien
    assert max(woche.values()) == 1


async def test_ohne_plan_ohne_stufe_ohne_fach(db, welt):
    await _anlegen(db, welt)
    andere = await _gruppe(db, welt, jahrgang=10)
    d = (await _lesen(db, andere)).json()
    assert (d["stufe"], d["grund"], d["plan"], d["abschnitt_je_woche"]) == (10, "kein_plan", None, {})

    unbekannt = await _gruppe(db, welt, jahrgang=None, name="Projektkurs Astronomie")
    d = (await _lesen(db, unbekannt)).json()
    assert (d["stufe"], d["grund"], d["plan"]) == (None, "keine_stufe", None)

    ohne_fach = await _gruppe(db, welt, fach=False)
    assert (await _lesen(db, ohne_fach)).json()["grund"] == "kein_fach"


async def test_plan_anderer_schuljahre_zaehlt_nicht(db, welt):
    assert (await _anlegen(db, welt, schuljahr="2026/27")).status_code == 201
    g = await _gruppe(db, welt)
    d = (await _lesen(db, g)).json()
    assert (d["grund"], d["plan"]) == ("kein_plan", None)


async def test_nur_lehrkraefte_der_gruppe(db, welt):
    await _anlegen(db, welt)
    g = await _gruppe(db, welt)
    # Fachschaft und fremde Lehrkraft sind nicht in der Gruppe
    assert (await _lesen(db, g, FS())).status_code == 403
    assert (await _lesen(db, g, LK())).status_code == 403
    assert (await _lesen(db, g, _person(LEHRKRAFT, "student"))).status_code == 403
