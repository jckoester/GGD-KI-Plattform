"""Vorschau und Darstellungsstufe (0.48, Päckchen N, Schritt 8 / Päckchen O Punkt 3).

Festgehalten wird, wie es ist:

- `GET /ui/levels` liefert in der Vorschau den Zuschnitt der **Schüler:innen** (Rolle aus dem
  Vorschau-Token).
- Die Stufe selbst kommt aus den Einstellungen der **Lehrkraft** (`GET /preferences` liest
  dasselbe Pseudonym); die Oberfläche klemmt sie auf die Stufen der Schüler:innen
  (`wirksameStufe`, Frontend-Test `ui_level.test.js`).
- Ändern lässt sie sich in der Vorschau nicht: `PATCH /preferences` ist gesperrt, die eigene
  Stufe der Lehrkraft bleibt unberührt.
"""
import time

import pytest

from app.auth.vorschau import Vorschau
from app.ui.levels import load_ui_levels
from tests.integration.conftest import TEACHER1_PSEUDO

pytestmark = pytest.mark.asyncio


def _kopf(jwt_service, *, vorschau: bool):
    if not vorschau:
        token, _ = jwt_service.issue(pseudonym=TEACHER1_PSEUDO, roles=["teacher"], grade=None)
    else:
        jetzt = int(time.time())
        token, _ = jwt_service.issue(
            pseudonym=TEACHER1_PSEUDO, roles=["student"], grade="9",
            preview=Vorschau(echte_rollen=["teacher"], beginn=jetzt, sitzung_ablauf=jetzt + 3600),
            exp=jetzt + 3600,
        )
    return {"Cookie": f"session={token}"}


@pytest.fixture
async def eigene_stufe(test_client, jwt_service):
    """Die Lehrkraft auf ihre höchste Stufe; danach die vorige wiederherstellen."""
    lehrkraft = _kopf(jwt_service, vorschau=False)
    vorher = (await test_client.get("/preferences", headers=lehrkraft)).json().get("ui_level")
    hoechste = load_ui_levels().rollen["teacher"].hoechste
    r = await test_client.patch("/preferences", json={"ui_level": hoechste}, headers=lehrkraft)
    assert r.status_code == 200, r.text
    yield hoechste
    if vorher is not None:
        await test_client.patch("/preferences", json={"ui_level": vorher}, headers=lehrkraft)


async def test_vorschau_bekommt_den_zuschnitt_der_schuelerinnen(test_client, jwt_service, eigene_stufe):
    r = await test_client.get("/ui/levels", headers=_kopf(jwt_service, vorschau=True))
    assert r.status_code == 200
    daten = r.json()
    schueler = load_ui_levels().rollen["student"]
    assert daten["rolle"] == "student"
    assert daten["hoechste"] == schueler.hoechste
    assert {s["stufe"] for s in daten["stufen"]} == {s.stufe for s in schueler.stufen}


async def test_stufe_kommt_aus_den_einstellungen_der_lehrkraft(test_client, jwt_service, eigene_stufe):
    prefs = (await test_client.get("/preferences", headers=_kopf(jwt_service, vorschau=True))).json()
    assert prefs["ui_level"] == eigene_stufe


async def test_stufe_laesst_sich_in_der_vorschau_nicht_aendern(test_client, jwt_service, eigene_stufe):
    r = await test_client.patch("/preferences", json={"ui_level": 1},
                                headers=_kopf(jwt_service, vorschau=True))
    assert r.status_code == 403
    lehrkraft = (await test_client.get("/preferences", headers=_kopf(jwt_service, vorschau=False))).json()
    assert lehrkraft["ui_level"] == eigene_stufe
