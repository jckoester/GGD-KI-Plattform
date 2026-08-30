"""
Tests für app.api.admin.guardrail
"""
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SCHOOL_SECRET", "test-secret")
os.environ.setdefault("JWT_SECRET", "test-jwt")
os.environ.setdefault("PUBLIC_STUDENT_GRADES", "[5,6,7,8,9,10,11,12]")

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.db.models import SiteConfig
from app.db.session import get_db
from app.api.admin.guardrail import router


def _admin() -> JwtPayload:
    return JwtPayload(sub="p-admin", roles=["admin"], grade=None,
                      jti="j-1", iat=1, exp=9999999999)


def _teacher() -> JwtPayload:
    return JwtPayload(sub="p-teacher", roles=["teacher"], grade=None,
                      jti="j-2", iat=1, exp=9999999999)


def _make_app(payload: JwtPayload, mock_db) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    async def fake_user():
        return payload

    async def fake_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_db] = fake_db
    return app


def _db_with_row(row) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    session.execute.return_value = result
    return session


# ========== GET /prompt ==========


def test_get_guardrail_prompt_returns_prompt():
    """DB-Eintrag vorhanden → Prompt + Metadaten zurück."""
    row = MagicMock(spec=SiteConfig)
    row.value = "Sei stets altersgerecht."
    row.updated_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    row.updated_by = "p-admin"

    app = _make_app(_admin(), _db_with_row(row))
    response = TestClient(app).get("/guardrail/prompt")

    assert response.status_code == 200
    data = response.json()
    assert data["prompt"] == "Sei stets altersgerecht."
    assert data["updated_by"] == "p-admin"


def test_get_guardrail_prompt_returns_null_when_missing():
    """Kein DB-Eintrag → prompt: null."""
    app = _make_app(_admin(), _db_with_row(None))
    response = TestClient(app).get("/guardrail/prompt")

    assert response.status_code == 200
    assert response.json()["prompt"] is None


def test_get_guardrail_prompt_requires_admin():
    """Lehrkraft → 403."""
    app = _make_app(_teacher(), AsyncMock())
    response = TestClient(app).get("/guardrail/prompt")
    assert response.status_code == 403


# ========== PUT /prompt ==========


def test_put_guardrail_prompt_sets_new_prompt():
    """PUT mit Prompt → 200, Prompt wird zurückgegeben, Cache wird geleert."""
    import app.chat.router as chat_router
    chat_router._guardrail_prompt_cache = ("alter Wert", 9999999999.0)

    updated_row = MagicMock(spec=SiteConfig)
    updated_row.value = "Neuer Prompt"
    updated_row.updated_at = datetime(2026, 5, 21, tzinfo=timezone.utc)
    updated_row.updated_by = "p-admin"

    session = AsyncMock()
    result_after = MagicMock()
    result_after.scalar_one.return_value = updated_row
    session.execute.return_value = result_after
    session.commit = AsyncMock()

    app = _make_app(_admin(), session)
    response = TestClient(app).put("/guardrail/prompt", json={"prompt": "Neuer Prompt"})

    assert response.status_code == 200
    assert response.json()["prompt"] == "Neuer Prompt"
    assert chat_router._guardrail_prompt_cache is None


def test_put_guardrail_prompt_null_deactivates():
    """PUT mit prompt=null → 200, prompt: null."""
    updated_row = MagicMock(spec=SiteConfig)
    updated_row.value = None
    updated_row.updated_at = datetime(2026, 5, 21, tzinfo=timezone.utc)
    updated_row.updated_by = "p-admin"

    session = AsyncMock()
    result_after = MagicMock()
    result_after.scalar_one.return_value = updated_row
    session.execute.return_value = result_after
    session.commit = AsyncMock()

    app = _make_app(_admin(), session)
    response = TestClient(app).put("/guardrail/prompt", json={"prompt": None})

    assert response.status_code == 200
    assert response.json()["prompt"] is None


def test_put_guardrail_prompt_too_long_returns_422():
    """Prompt > 10 000 Zeichen → 422."""
    app = _make_app(_admin(), AsyncMock())
    response = TestClient(app).put("/guardrail/prompt", json={"prompt": "x" * 10_001})
    assert response.status_code == 422


def test_put_guardrail_prompt_requires_admin():
    """Lehrkraft → 403."""
    app = _make_app(_teacher(), AsyncMock())
    response = TestClient(app).put("/guardrail/prompt", json={"prompt": "Text"})
    assert response.status_code == 403


# ========== GET /litellm ==========


def test_get_litellm_guardrails_returns_list():
    """LiteLLM liefert zwei Guardrails → normalisierte Liste."""
    guardrails = [
        {"name": "pii-guard", "mode": "pre_call"},
        {"name": "violence-guard", "mode": "post_call"},
    ]
    app = _make_app(_admin(), AsyncMock())

    with patch("app.api.admin.guardrail._litellm") as mock_client:
        mock_client.list_guardrails = AsyncMock(return_value=guardrails)
        response = TestClient(app).get("/guardrail/litellm")

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert len(data["guardrails"]) == 2
    assert data["guardrails"][0]["name"] == "pii-guard"
    assert data["guardrails"][0]["mode"] == "pre_call"


def test_get_litellm_guardrails_empty_when_none_configured():
    """LiteLLM liefert leere Liste → leere guardrails, available: True."""
    app = _make_app(_admin(), AsyncMock())

    with patch("app.api.admin.guardrail._litellm") as mock_client:
        mock_client.list_guardrails = AsyncMock(return_value=[])
        response = TestClient(app).get("/guardrail/litellm")

    assert response.status_code == 200
    assert response.json()["guardrails"] == []
    assert response.json()["available"] is True


def test_get_litellm_guardrails_requires_admin():
    """Lehrkraft → 403."""
    app = _make_app(_teacher(), AsyncMock())
    response = TestClient(app).get("/guardrail/litellm")
    assert response.status_code == 403


# ── /guardrail/health ────────────────────────────────────────────────────────
#
# Der Guardrail läuft im LiteLLM-Proxy, nicht im Backend. Er legt seinen Zählerstand als
# JSON ab; dieser Endpunkt reicht ihn durch. Der wichtigste Fall ist die FEHLENDE Datei:
# Sie darf nicht als „alles in Ordnung" durchgehen — sonst meldet ein Monitoring grün,
# obwohl der Guardrail womöglich gar nicht läuft.

def _health_app(tmp_path, inhalt: str | None):
    from app.config import settings
    pfad = tmp_path / "guardrail_health.json"
    if inhalt is not None:
        pfad.write_text(inhalt, encoding="utf-8")
    alt = settings.guardrail_health_file
    settings.guardrail_health_file = str(pfad)
    return _make_app(_admin(), MagicMock()), alt


def test_health_missing_file_is_not_healthy(tmp_path):
    from app.config import settings
    app, alt = _health_app(tmp_path, None)
    try:
        r = TestClient(app).get("/guardrail/health")
    finally:
        settings.guardrail_health_file = alt

    assert r.status_code == 200
    d = r.json()
    assert d["available"] is False
    assert d["healthy"] is None, "kein Bericht heißt NICHT gesund"
    assert "health_file" in d["hinweis"]


def test_health_unreadable_file_is_not_healthy(tmp_path):
    from app.config import settings
    app, alt = _health_app(tmp_path, "{kaputt")
    try:
        r = TestClient(app).get("/guardrail/health")
    finally:
        settings.guardrail_health_file = alt

    assert r.json()["available"] is False
    assert r.json()["healthy"] is None


def test_health_reports_the_counters(tmp_path):
    from app.config import settings
    bericht = (
        '{"classifier_model": "openai/gpt-4o-mini", "fallback_model": null,'
        ' "checked_at": "2026-08-28T10:00:00+00:00", "total": 100,'
        ' "counters": {"primary_ok": 90, "retry_ok": 5, "fallback_ok": 0,'
        ' "failed_open": 3, "failed_closed": 2, "blocked": 7},'
        ' "failure_rate": 0.05, "healthy": false}'
    )
    app, alt = _health_app(tmp_path, bericht)
    try:
        r = TestClient(app).get("/guardrail/health")
    finally:
        settings.guardrail_health_file = alt

    d = r.json()
    assert d["available"] is True and d["healthy"] is False
    assert d["failure_rate"] == 0.05
    assert d["counters"]["retry_ok"] == 5
    assert d["classifier_model"] == "openai/gpt-4o-mini"


def test_health_requires_admin(tmp_path):
    app = _make_app(_teacher(), MagicMock())

    assert TestClient(app).get("/guardrail/health").status_code == 403


def test_health_path_is_anchored_at_the_repo_root():
    """Backend läuft aus `backend/`, der Proxy aus `infra/` — ein cwd-relativer Pfad
    meinte damit zwei verschiedene Dateien, und der Endpunkt meldete „kein Bericht",
    obwohl der Proxy einen schrieb.

    Die Wurzel bestimmt seit 08/2026 `app.core.paths.aufloesen`. Dieses Modul liegt eine
    Ebene tiefer als die übrigen Verwender und rechnete deshalb mit `parents[4]` statt
    `parents[3]` — genau die Art Rechnung, die im Container um eins danebenging.
    """
    from pathlib import Path

    from app.api.admin.guardrail import _resolve

    repo = Path(__file__).resolve().parents[3]
    assert _resolve("data/x.json") == repo / "data" / "x.json"
    assert _resolve("/abs/x.json").as_posix() == "/abs/x.json"
    assert (repo / "backend").is_dir(), "Repo-Wurzel falsch bestimmt"


# ── Veralteter Bericht ───────────────────────────────────────────────────────
#
# Der gefährlichste Zustand überhaupt: Stoppt der Proxy — oder bricht die gemeinsam
# gemountete Ablage weg, was bei getrennten Compose-Stacks realistisch ist —, bleibt die
# Datei mit `healthy: true` liegen. Ohne Altersprüfung meldete ein Monitoring unbegrenzt
# Entwarnung, obwohl seit Tagen nichts geprüft wird.

def _bericht(checked_at: str | None, healthy: bool = True) -> str:
    import json as _json
    return _json.dumps({
        "classifier_model": "m", "fallback_model": None, "checked_at": checked_at,
        "total": 10, "counters": {"primary_ok": 10}, "failure_rate": 0.0,
        "healthy": healthy,
    })


def _hole(tmp_path, inhalt):
    from app.config import settings
    app, alt = _health_app(tmp_path, inhalt)
    try:
        return TestClient(app).get("/guardrail/health").json()
    finally:
        settings.guardrail_health_file = alt


def test_fresh_report_is_healthy(tmp_path):
    from datetime import datetime, timedelta, timezone
    jetzt = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    d = _hole(tmp_path, _bericht(jetzt))

    assert d["available"] is True and d["healthy"] is True and d["stale"] is False


def test_stale_report_is_not_healthy(tmp_path):
    """Ein gestoppter Proxy darf nicht als gesund durchgehen."""
    from datetime import datetime, timedelta, timezone
    alt = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()

    d = _hole(tmp_path, _bericht(alt))

    assert d["available"] is True, "die Datei ist ja da"
    assert d["stale"] is True
    assert d["healthy"] is False, "trotz healthy:true im Bericht"
    assert "Proxy" in d["hinweis"]


def test_report_without_timestamp_is_not_healthy(tmp_path):
    d = _hole(tmp_path, _bericht(None))

    assert d["stale"] is True and d["healthy"] is False


def test_report_with_unparsable_timestamp_is_not_healthy(tmp_path):
    d = _hole(tmp_path, _bericht("neulich mal"))

    assert d["stale"] is True and d["healthy"] is False


def test_stale_beats_a_naive_timezone(tmp_path):
    """Zeitstempel ohne Zonenangabe als UTC lesen — sonst wäre ein frischer Bericht
    je nach Serverzone scheinbar Stunden alt und löste Fehlalarm aus."""
    from datetime import datetime, timezone
    ohne_zone = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    d = _hole(tmp_path, _bericht(ohne_zone))

    assert d["stale"] is False and d["healthy"] is True
