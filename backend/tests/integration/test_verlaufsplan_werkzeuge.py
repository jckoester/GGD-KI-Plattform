"""Die Funktionen des Jahresplan-Assistenten zum Jahresverlaufsplan (0.61, Schritt 2) — ohne Modell,
mit `ToolContext` auf der Test-Datenbank. Welt wie in `test_verlaufsplan_gruppe.py`."""
import json
from datetime import date

import pytest

from app.chat.tools import ToolContext
from app.planning import assistant_tools as at

from tests.integration.test_verlaufsplan_endpunkte import _anlegen, db, welt  # noqa: F401 — Fixtures
from tests.integration.test_verlaufsplan_gruppe import _einheiten, _gruppe, _lk, _termine

pytestmark = pytest.mark.asyncio


@pytest.fixture
def heute(monkeypatch):
    from app.context import verlaufsplan as vp

    monkeypatch.setattr(vp, "heute", lambda: date(2025, 9, 1))


def _ctx(db, g):
    return ToolContext(db=db, user=_lk(), group_id=g.id, conversation_id=None)


async def _welt(db, welt):
    await _anlegen(db, welt, abschnitte=[
        {"titel": "", "wochen": 1, "kapitel_ids": [str(welt["kapitel"][0].id)], "notiz": "mit GeoGebra"},
        {"titel": "Luft", "wochen": 1, "puffer": True},
        {"titel": "", "wochen": 1, "kapitel_ids": [str(welt["kapitel"][1].id)]},
    ])
    g = await _gruppe(db, welt)
    await _termine(db, g, [date(2025, 9, 15), date(2025, 9, 22), date(2025, 9, 29)])
    return g


async def test_lesen_anlegen_zuruecknehmen(db, welt, heute):
    g = await _welt(db, welt)
    gid, ctx = g.id, _ctx(db, g)

    bilanz = await at._handle_get_plan_balance({}, ctx)
    assert bilanz["verlaufsplan"]["status"] == "entwurf"

    plan = await at._handle_get_verlaufsplan({}, ctx)
    json.dumps(plan)
    assert plan["verlaufsplan"]["abschnitte"][0]["notiz"] == "mit GeoGebra"
    assert [(v["nr"], v["anlegen"], v["grund"]) for v in plan["vorschau"]] == [
        (1, True, None), (2, False, "puffer"), (3, True, None)]
    assert (plan["neu"], plan["stunden"]) == (2, 2)

    erg = await at._handle_verlaufsplan_einheiten_anlegen(
        {"auslassen": [3], "umbenennen": [{"nr": 1, "titel": "Strahlensätze"}]}, ctx)
    json.dumps(erg)
    assert (erg["ok"], erg["einheiten"], erg["stunden"]) == (True, 1, 1) and erg["lauf_id"]
    assert erg["angelegt"] == [{"nr": 1, "titel": "Strahlensätze", "kapitel": "Ähnlichkeit", "stunden": 1}]
    assert "balance" in erg

    # „Mach das rückgängig“ über undo_last_change: verweist auf die eigene Rücknahme
    undo = await at._handle_undo_last_change({}, ctx)
    assert "verlaufsplan_anlegen_zuruecknehmen" in undo["error"] and undo["lauf_id"] == erg["lauf_id"]
    assert len(await _einheiten(db, gid)) == 1

    # Rücknahme ohne lauf_id: das jüngste Anlegen
    zurueck = await at._handle_verlaufsplan_anlegen_zuruecknehmen({}, ctx)
    json.dumps(zurueck)
    assert (zurueck["ok"], zurueck["einheiten_geloescht"]) == (True, 1)
    assert await _einheiten(db, gid) == []
    assert "keine Einheiten" in (await at._handle_verlaufsplan_anlegen_zuruecknehmen({}, ctx))["error"]


async def test_nichts_anzulegen_und_fehler(db, welt, heute):
    g = await _welt(db, welt)
    ctx = _ctx(db, g)
    assert (await at._handle_verlaufsplan_einheiten_anlegen({"auslassen": [1, 3]}, ctx))["einheiten"] == 0
    assert "error" in await at._handle_verlaufsplan_einheiten_anlegen({"auslassen": ["drei"]}, ctx)
    assert "error" in await at._handle_verlaufsplan_einheiten_anlegen({"umbenennen": [{"nr": 1}]}, ctx)
    assert "error" in await at._handle_verlaufsplan_anlegen_zuruecknehmen({"lauf_id": "gibtsnicht"}, ctx)


async def test_ohne_plan(db, welt, heute):
    g = await _gruppe(db, welt, jahrgang=10)
    ctx = _ctx(db, g)
    assert (await at._handle_get_plan_balance({}, ctx))["verlaufsplan"] is None
    erg = await at._handle_get_verlaufsplan({}, ctx)
    assert erg["verlaufsplan"] is None and "keinen Jahresverlaufsplan" in erg["error"]
    assert "keinen Jahresverlaufsplan" in (await at._handle_verlaufsplan_einheiten_anlegen({}, ctx))["error"]
