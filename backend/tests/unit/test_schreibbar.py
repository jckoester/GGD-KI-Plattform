"""Schreibbare Verzeichnisse (0.15.1) — Prüfung, Startmeldung, Endpunkte, Compose.

Auf Produktion hängte die Compose `config/` schreibgeschützt ein; `/budget` und der
Ferienkalender scheiterten erst beim Speichern, mit einem 500. Jetzt meldet der Start es,
die Seiten sagen es selbst, und die Endpunkte antworten mit einem lesbaren Satz.

Schreibschutz entsteht hier über die Rechtebits (`chmod 0o555`). Root ignoriert sie —
unter root laufen diese Tests deshalb nicht.
"""
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import schreibbar
from app.core.schreibbar import Schreibziel, grund, pruefe_beim_start, schreibschutz

REPO = Path(__file__).resolve().parents[3]

unter_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root schreibt trotz fehlender Rechtebits",
)


@contextmanager
def schreibgeschuetzt(ordner: Path):
    ordner.chmod(0o555)
    try:
        yield ordner
    finally:
        ordner.chmod(0o755)


# ── Die Prüfung selbst ───────────────────────────────────────────────────────


def test_schreibbares_verzeichnis(tmp_path):
    assert grund(tmp_path) is None
    assert list(tmp_path.iterdir()) == [], "die Probedatei muss wieder weg sein"


@unter_root
def test_schreibgeschuetztes_verzeichnis(tmp_path):
    with schreibgeschuetzt(tmp_path):
        assert grund(tmp_path)


def test_fehlendes_verzeichnis_unter_schreibbarem(tmp_path):
    """Die Ablagen unter `data/` legen ihr Verzeichnis selbst an — fehlen darf es."""
    assert grund(tmp_path / "noch" / "nicht" / "da") is None


@unter_root
def test_fehlendes_verzeichnis_unter_schreibgeschuetztem(tmp_path):
    with schreibgeschuetzt(tmp_path):
        assert grund(tmp_path / "neu")


def test_datei_statt_verzeichnis(tmp_path):
    datei = tmp_path / "datei"
    datei.write_text("x")
    assert "kein Verzeichnis" in grund(datei)


@unter_root
def test_meldung_nennt_verzeichnis_und_abhilfe(tmp_path):
    datei = tmp_path / "budget_tiers.yaml"
    assert schreibschutz(datei) is None
    with schreibgeschuetzt(tmp_path):
        meldung = schreibschutz(datei)
    assert str(tmp_path) in meldung and ":ro" in meldung


# ── Startmeldung ─────────────────────────────────────────────────────────────


@unter_root
def test_start_meldet_beide_config_funktionen_in_einer_zeile(tmp_path, caplog):
    config = tmp_path / "config"
    daten = tmp_path / "data"
    config.mkdir()
    daten.mkdir()
    ziele = [Schreibziel(config, "Budget-Stufen"), Schreibziel(config, "Ferienkalender")]
    with patch.object(schreibbar, "config_ziele", return_value=ziele), \
         patch.object(schreibbar, "daten_ziele", return_value=[Schreibziel(daten, "Bibliothek")]), \
         schreibgeschuetzt(config), caplog.at_level(logging.WARNING, logger="app.core.schreibbar"):
        betroffen = pruefe_beim_start()

    assert [z.wozu for z in betroffen] == ["Budget-Stufen", "Ferienkalender"]
    zeilen = [r.getMessage() for r in caplog.records]
    assert len(zeilen) == 1
    assert "Budget-Stufen, Ferienkalender" in zeilen[0] and str(config) in zeilen[0]


def test_start_schweigt_wenn_alles_schreibbar(tmp_path, caplog):
    with patch.object(schreibbar, "config_ziele", return_value=[Schreibziel(tmp_path, "a")]), \
         patch.object(schreibbar, "daten_ziele", return_value=[Schreibziel(tmp_path / "neu", "b")]), \
         caplog.at_level(logging.WARNING, logger="app.core.schreibbar"):
        assert pruefe_beim_start() == []
    assert caplog.records == []


def test_start_kennt_die_echten_ziele():
    """Gegen ein Auseinanderlaufen: Wer eine neue Schreibstelle in `config/` baut, trägt
    sie hier ein — sonst meldet der Start sie nicht."""
    wozu = " ".join(z.wozu for z in [*schreibbar.config_ziele(), *schreibbar.daten_ziele()])
    for teil in ("/budget", "/settings/holidays", "Bilder", "Bibliothek", "Export-Vorlagen"):
        assert teil in wozu


# ── Compose ──────────────────────────────────────────────────────────────────


def _modus(dienst: dict, ziel: str) -> str:
    for eintrag in dienst.get("volumes", []):
        teile = eintrag.split(":")
        if len(teile) >= 2 and teile[1] == ziel:
            return teile[2] if len(teile) > 2 else "rw"
    raise AssertionError(f"{ziel} ist nicht eingehängt")


def test_modus_erkennt_ro():
    """Gegenprobe zur Hilfsfunktion — sonst bliebe der Compose-Test auch bei `:ro` grün."""
    assert _modus({"volumes": ["./config:/app/config:ro"]}, "/app/config") == "ro"
    assert _modus({"volumes": ["./config:/app/config"]}, "/app/config") == "rw"


def test_backend_haengt_config_schreibbar_ein():
    compose = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    dienste = compose["services"]
    assert _modus(dienste["backend"], "/app/config") == "rw"
    # Der Cron liest nur — er bleibt schreibgeschützt.
    assert _modus(dienste["cron"], "/app/config") == "ro"


# ── Endpunkte ────────────────────────────────────────────────────────────────


def _app(router, payload):
    from app.auth.dependencies import get_current_user
    from app.db.session import get_db

    app = FastAPI()
    app.include_router(router)
    session = AsyncMock()
    leer = MagicMock()
    leer.fetchall.return_value = []
    session.execute.return_value = leer

    async def nutzer():
        return payload

    async def db():
        yield session

    app.dependency_overrides[get_current_user] = nutzer
    app.dependency_overrides[get_db] = db
    return TestClient(app)


def _admin():
    from app.auth.jwt import JwtPayload

    return JwtPayload(sub="p-1", roles=["admin"], grade=None, jti="j", iat=1, exp=9999999999)


@unter_root
def test_budget_speichern_ohne_schreibrecht_503_und_datei_unveraendert(tmp_path):
    from app.api.admin.budgets import router
    from app.config import settings

    datei = tmp_path / "budget_tiers.yaml"
    vorher = "roles:\n  teacher:\n    wochenbudget_eur: 1.0\n"
    datei.write_text(vorher, encoding="utf-8")
    with patch.object(settings, "budget_tiers_path", str(datei)), \
         patch("app.api.admin.budgets.get_current_rate", new=AsyncMock(return_value=1.08)), \
         patch("app.api.admin.budgets.LiteLLMClient") as litellm, \
         schreibgeschuetzt(tmp_path):
        antwort = _app(router, _admin()).post(
            "/budgets/grades", json={"grades": [{"key": "jahrgang-10", "max_budget_eur": 3.5}]}
        )

    assert antwort.status_code == 503
    assert str(tmp_path) in antwort.json()["detail"]
    assert datei.read_text(encoding="utf-8") == vorher
    litellm.assert_not_called()


@unter_root
def test_budget_seite_erfaehrt_vom_schreibschutz(tmp_path):
    from app.api.admin.budgets import router
    from app.config import settings

    datei = tmp_path / "budget_tiers.yaml"
    datei.write_text("roles: {}\n", encoding="utf-8")
    with patch.object(settings, "budget_tiers_path", str(datei)), \
         patch("app.api.admin.budgets.get_current_rate", new=AsyncMock(return_value=1.08)), \
         patch("app.api.admin.budgets._load_budget_tiers", return_value={"roles": {}, "grades": {}}):
        client = _app(router, _admin())
        assert client.get("/budgets/grades").json()["schreibschutz"] is None
        with schreibgeschuetzt(tmp_path):
            assert str(tmp_path) in client.get("/budgets/grades").json()["schreibschutz"]


@unter_root
def test_ferien_uebernehmen_ohne_schreibrecht_503_vor_dem_abruf(tmp_path):
    from app.api.admin.holidays import router

    datei = tmp_path / "school_year.yaml"
    with patch("app.api.admin.holidays._DEFAULT_PATH", datei), \
         patch("app.api.admin.holidays.is_configured", return_value=True), \
         patch("app.api.admin.holidays._hole_vorschlag", new=AsyncMock()) as abruf, \
         schreibgeschuetzt(tmp_path):
        antwort = _app(router, _admin()).post("/holidays/apply", json={})

    assert antwort.status_code == 503
    assert str(tmp_path) in antwort.json()["detail"]
    abruf.assert_not_called()
    assert not datei.exists()
