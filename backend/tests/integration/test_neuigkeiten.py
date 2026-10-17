"""Hinweise auf Neuerungen über die Endpunkte (0.17, Plan Schritt 6).

Die Hinweise kommen aus einer Attrappe statt aus der ausgelieferten Datei, die
Darstellungsstufen aus `config/ui_levels.example.yaml` — die eigene Datei der Schule ist
nicht eingecheckt. Die Regeln im Einzelnen prüft `tests/unit/test_neuigkeiten.py`.
"""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
import yaml
from sqlalchemy import text

from app.neuigkeiten.quelle import Neuigkeit
from app.ui.levels import UiLevels
from tests.integration.conftest import STUDENT_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

NEU_PSEUDO = "neuigkeiten-neu-pseudo"
ADMIN_PSEUDO = "neuigkeiten-admin-pseudo"
BEISPIEL = Path(__file__).resolve().parents[3] / "config" / "ui_levels.example.yaml"
STUFEN = UiLevels.model_validate(yaml.safe_load(BEISPIEL.read_text(encoding="utf-8")))
HINWEISE = (
    Neuigkeit(id="t-planung", version="0.17.0", datum=date.today() - timedelta(days=3),
              rollen=["teacher"], titel="Planung", text="Für Lehrkräfte", eintrag="planner",
              link="/help/unterrichtsplanung"),
    Neuigkeit(id="t-alle", version="0.17.0", datum=date.today() - timedelta(days=3),
              rollen=["student", "teacher"], titel="Alle", text="Für alle"),
)
PERSONEN = [TEACHER2_PSEUDO, STUDENT_PSEUDO, NEU_PSEUDO, ADMIN_PSEUDO]


@pytest_asyncio.fixture
async def umgebung(async_engine):
    async def aufraeumen():
        async with async_engine.begin() as conn:
            await conn.execute(text("DELETE FROM user_preferences WHERE pseudonym = ANY(:p)"), {"p": PERSONEN})
            await conn.execute(text("DELETE FROM pseudonym_audit WHERE pseudonym = :p"), {"p": NEU_PSEUDO})
    await aufraeumen()
    with patch("app.neuigkeiten.router.alle", return_value=HINWEISE), \
         patch("app.neuigkeiten.router.load_ui_levels", return_value=STUFEN), \
         patch("app.preferences.router.load_ui_levels", return_value=STUFEN), \
         patch("app.ui.levels.load_ui_levels", return_value=STUFEN):
        yield
    await aufraeumen()


def _kopf(jwt_service, pseudonym, rollen, grade=None):
    token, _ = jwt_service.issue(pseudonym=pseudonym, roles=rollen, grade=grade)
    return {"Cookie": f"session={token}"}


async def _ids(client, kopf):
    resp = await client.get("/neuigkeiten", headers=kopf)
    assert resp.status_code == 200, resp.text
    return [n["id"] for n in resp.json()]


async def test_rolle_und_stufe(test_client, umgebung, auth_headers_teacher2, auth_headers_student):
    # Ohne gespeicherte Stufe gilt die Startstufe 1 — die Planung liegt bei Lehrkräften auf 3.
    assert await _ids(test_client, auth_headers_teacher2) == ["t-alle"]
    assert (await test_client.patch("/preferences", headers=auth_headers_teacher2,
                                    json={"ui_level": 3})).status_code == 200
    assert await _ids(test_client, auth_headers_teacher2) == ["t-planung", "t-alle"]
    assert await _ids(test_client, auth_headers_student) == ["t-alle"]


async def test_admin_sieht_hinweise_fuer_lehrkraefte(test_client, umgebung, jwt_service):
    """Rollen sind additiv: Ein Token nur mit `admin` sieht, was Lehrkräften gilt."""
    assert "t-planung" in await _ids(test_client, _kopf(jwt_service, ADMIN_PSEUDO, ["admin"]))


async def test_wegklicken(test_client, umgebung, auth_headers_student):
    for _ in range(2):                                            # zweimal: idempotent
        resp = await test_client.post("/neuigkeiten/t-alle/gelesen", headers=auth_headers_student)
        assert resp.status_code == 204
    assert await _ids(test_client, auth_headers_student) == []
    prefs = (await test_client.get("/preferences", headers=auth_headers_student)).json()
    assert prefs["neuigkeiten_gelesen"] == ["t-alle"]


async def test_unbekannter_hinweis(test_client, umgebung, auth_headers_student):
    resp = await test_client.post("/neuigkeiten/gibt-es-nicht/gelesen", headers=auth_headers_student)
    assert resp.status_code == 404


async def test_neues_konto_sieht_alte_hinweise_nicht(test_client, umgebung, async_engine, jwt_service):
    async with async_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO pseudonym_audit (pseudonym, role, created_at) VALUES (:p, 'student', :t)"),
            {"p": NEU_PSEUDO, "t": datetime.now(timezone.utc)})
    assert await _ids(test_client, _kopf(jwt_service, NEU_PSEUDO, ["student"], "8")) == []
