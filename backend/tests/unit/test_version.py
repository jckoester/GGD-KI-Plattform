"""Die Plattformversion in `/health` — aus einer einzigen Quelle (0.13, P4).

Das Obsidian-Plugin schreibt Phasen nur zurück, wenn `/health` eine Version nennt, die
P1–P3 hat. Gegen eine ältere Plattform verlöre es sonst still den Nachbereitungsstatus.
"""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import version

BACKEND = Path(__file__).resolve().parents[2]
WURZEL = BACKEND.parent


def test_health_nennt_die_version_ohne_anmeldung():
    from app.main import app

    resp = TestClient(app).get("/health")   # ohne Cookie, ohne Token
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": (BACKEND / "VERSION").read_text().strip()}


def test_version_hat_die_form_x_y_z():
    assert re.fullmatch(r"\d+\.\d+\.\d+", version.plattformversion())


def test_fehlende_datei_macht_health_nicht_kaputt(tmp_path, monkeypatch):
    """`/health` ist der Healthcheck des Containers — eine fehlende Versionsdatei darf
    das Backend nicht als „unhealthy" neu starten lassen."""
    monkeypatch.setattr(version, "DATEI", tmp_path / "fehlt")
    version.plattformversion.cache_clear()
    try:
        assert version.plattformversion() == version.UNBEKANNT
    finally:
        version.plattformversion.cache_clear()


def test_die_datei_kommt_in_beide_images():
    """Docker ist in der Entwicklung nicht installiert — also statisch: Das Backend-Image
    (Kontext `./backend`, `COPY . .`) schließt die Datei nicht aus, und der Frontend-Build
    (Kontext Wurzel) kopiert sie dorthin, wo `vite.config.js` sie liest."""
    ausschluss = [z.strip() for z in (BACKEND / ".dockerignore").read_text().splitlines()
                  if z.strip() and not z.startswith("#")]
    assert not any(muster.rstrip("/") in ("VERSION", "*", "/VERSION") for muster in ausschluss)
    assert "COPY . ." in (BACKEND / "Dockerfile").read_text()
    assert "COPY backend/VERSION /repo/backend/VERSION" in (WURZEL / "frontend" / "Dockerfile").read_text()
