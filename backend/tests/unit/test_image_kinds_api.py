"""Unit-Tests für GET /image-kinds (Mehrmodell-Plan, Schritt 4).

Der Endpunkt speist die Bildart-Auswahl im Assistenten-Editor und die Warnung, dass ein
Bildmodell für bestimmte Jahrgänge gar nicht freigeschaltet ist.

Wichtigster Fall ist der **unbekannte** Freigabestand: Ist der Proxy nicht erreichbar, darf
der Endpunkt keine Lücken behaupten. Eine Falschwarnung bei jedem Speichern wird binnen
einer Woche weggeklickt — und mit ihr die echten.

Kein `/api`-Präfix: Der Router wird direkt eingebunden (CLAUDE.md).
"""

import os
import textwrap
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.api.image_kinds import router
from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.chat import image_models
from app.config import settings

BILDARTEN = """\
bildarten:
  - id: standard
    label: "Standard (quadratisch)"
    beschreibung: |
      Mehrzeilig,
      damit die Normalisierung geprüft wird.
    modell: bild-standard
    formate:
      quadratisch: "1024x1024"
    standardformat: quadratisch
  - id: formatwahl
    label: "Mit Formatwahl"
    modell: bild-flux2
    formate:
      quadratisch: "1024x1024"
      quer: "1344x768"
    standardformat: quer
standard_bildart: standard
"""


def _user(roles):
    return JwtPayload(sub="p", roles=roles, grade=None, jti="j", iat=1, exp=9999999999)


@pytest.fixture
def bildarten_datei(tmp_path, monkeypatch):
    pfad = tmp_path / "image_models.yaml"
    pfad.write_text(textwrap.dedent(BILDARTEN), encoding="utf-8")
    monkeypatch.setattr(settings, "image_models_path", str(pfad))
    image_models.invalidate_image_models_cache()
    yield
    image_models.invalidate_image_models_cache()


def _app(payload):
    app = FastAPI()
    app.include_router(router)

    async def fake_user():
        return payload

    # `require_any_role` hängt an get_current_user — das ist der Punkt zum Überschreiben;
    # der Rückgabewert von require_any_role(...) ist bei jedem Aufruf ein neues Objekt und
    # taugt deshalb nicht als Schlüssel.
    app.dependency_overrides[get_current_user] = fake_user
    return app


@pytest.fixture
def client(bildarten_datei):
    return TestClient(_app(_user(["teacher"])))


def _team(models):
    return {"models": models}


def test_liefert_bildarten_mit_formaten(client):
    with patch(
        "app.api.image_kinds._client.get_team_info",
        new=AsyncMock(return_value=_team(["bild-standard", "bild-flux2"])),
    ):
        resp = client.get("/image-kinds")

    assert resp.status_code == 200
    daten = resp.json()
    assert [b["id"] for b in daten["bildarten"]] == ["standard", "formatwahl"]
    assert daten["standard_bildart"] == "standard"
    assert daten["freigabe_bekannt"] is True
    assert daten["bildarten"][1]["formate"] == ["quadratisch", "quer"]


def test_beschreibung_wird_einzeilig(client):
    """Mehrzeiliger YAML-Text würde die Editor-Zeile sonst sprengen."""
    with patch(
        "app.api.image_kinds._client.get_team_info",
        new=AsyncMock(return_value=_team(["bild-standard", "bild-flux2"])),
    ):
        beschreibung = client.get("/image-kinds").json()["bildarten"][0]["beschreibung"]

    assert "\n" not in beschreibung
    assert beschreibung.startswith("Mehrzeilig, damit")


def test_vollstaendige_freigabe_meldet_keine_luecken(client):
    with patch(
        "app.api.image_kinds._client.get_team_info",
        new=AsyncMock(return_value=_team(["bild-standard", "bild-flux2"])),
    ):
        daten = client.get("/image-kinds").json()

    for b in daten["bildarten"]:
        assert b["fehlt_fuer_jahrgaenge"] == []
        assert b["fehlt_fuer_lehrkraefte"] is False


def test_fehlende_freigabe_wird_je_jahrgang_gemeldet(client):
    """Nur `bild-standard` ist freigeschaltet — `formatwahl` fehlt überall."""
    with patch(
        "app.api.image_kinds._client.get_team_info",
        new=AsyncMock(return_value=_team(["bild-standard"])),
    ):
        daten = client.get("/image-kinds").json()

    standard, formatwahl = daten["bildarten"]
    assert standard["fehlt_fuer_jahrgaenge"] == []
    assert standard["fehlt_fuer_lehrkraefte"] is False
    assert formatwahl["fehlt_fuer_jahrgaenge"] == [5, 6, 7, 8, 9, 10, 11, 12]
    assert formatwahl["fehlt_fuer_lehrkraefte"] is True


def test_no_default_models_zaehlt_als_keine_freigabe(client):
    """LiteLLMs Platzhalter für „nichts freigeschaltet" ist keine Modell-ID."""
    with patch(
        "app.api.image_kinds._client.get_team_info",
        new=AsyncMock(return_value=_team(["no-default-models"])),
    ):
        daten = client.get("/image-kinds").json()

    assert daten["bildarten"][0]["fehlt_fuer_lehrkraefte"] is True


def test_unerreichbarer_proxy_behauptet_keine_luecken(client):
    """Der wichtigste Fall: lieber keine Auskunft als eine erfundene."""
    with patch(
        "app.api.image_kinds._client.get_team_info",
        new=AsyncMock(side_effect=RuntimeError("Proxy weg")),
    ):
        daten = client.get("/image-kinds").json()

    assert daten["freigabe_bekannt"] is False
    for b in daten["bildarten"]:
        assert b["fehlt_fuer_jahrgaenge"] == []
        assert b["fehlt_fuer_lehrkraefte"] is False


def test_unbekanntes_team_wird_uebergangen_nicht_als_luecke_gewertet(client):
    """404 heißt „Team gibt es nicht", nicht „dort ist nichts freigeschaltet"."""
    with patch(
        "app.api.image_kinds._client.get_team_info", new=AsyncMock(return_value=None)
    ):
        daten = client.get("/image-kinds").json()

    assert daten["freigabe_bekannt"] is False
    assert daten["bildarten"][0]["fehlt_fuer_jahrgaenge"] == []


def test_schueler_duerfen_nicht(bildarten_datei):
    """Die Bildart-Konfiguration ist Lehrkraft-/Admin-Sache."""
    resp = TestClient(_app(_user(["student"]))).get("/image-kinds")

    assert resp.status_code == 403
