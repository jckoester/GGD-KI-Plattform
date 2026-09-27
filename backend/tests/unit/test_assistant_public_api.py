"""Unit tests für den öffentlichen Assistenten-Endpunkt."""
import pytest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.assistants import router as assistants_router
from app.assistants.sichtbarkeit import Zugang, darf_nutzen


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def make_assistant(
    *,
    status: str = "active",
    audience: str = "all",
    available_from: datetime | None = None,
    available_until: datetime | None = None,
    scope: str = "all",
    scope_group_id: int | None = None,
    created_by: str = "wer-anders",
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        audience=audience,
        available_from=available_from,
        available_until=available_until,
        scope=scope,
        scope_group_id=scope_group_id,
        created_by=created_by,
    )


def zugang(*rollen: str, gruppen=(), lehrgruppen=(), pseudonym="pseudo-abc") -> Zugang:
    return Zugang(
        pseudonym=pseudonym,
        rollen=frozenset(rollen),
        gruppen=frozenset(gruppen),
        lehrgruppen=frozenset(lehrgruppen),
    )


def make_jwt_payload(roles: list[str] = None):
    from app.auth.jwt import JwtPayload
    return JwtPayload(
        sub="pseudo-abc",
        roles=roles or ["student"],
        grade="8",
        jti="test-jti",
        iat=1000000,
        exp=9999999999,
    )


def _make_mini_app(mock_db, roles: list[str] = None):
    app = FastAPI()

    from app.auth.dependencies import get_current_user
    from app.db.session import get_db

    payload = make_jwt_payload(roles or ["student"])

    app.dependency_overrides[get_current_user] = lambda: payload
    app.dependency_overrides[get_db] = lambda: mock_db
    app.include_router(assistants_router)
    return app


def _make_mock_db(assistants: list) -> AsyncMock:
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = assistants
    mock_db = AsyncMock()
    mock_db.execute.return_value = execute_result
    return mock_db


def _make_assistant_ns(
    id: int = 1,
    name: str = "Test",
    description: str | None = None,
    subject_id: int | None = None,
    audience: str = "all",
    scope: str = "private",
    visibility: str = "public",
    icon: str | None = None,
    tags: list | None = None,
    min_grade: int | None = None,
    max_grade: int | None = None,
    created_by: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        name=name,
        description=description,
        subject_id=subject_id,
        audience=audience,
        scope=scope,
        visibility=visibility,
        icon=icon,
        tags=tags,
        min_grade=min_grade,
        max_grade=max_grade,
        created_by=created_by,
    )


# =============================================================================
# Zielgruppe und Zeitfenster — die Regel aus `app/assistants/sichtbarkeit.py`
#
# Die Scopes stehen in `tests/integration/test_assistenten_sichtbarkeit.py`: Dort
# laufen Funktion und SQL-Bedingung am selben Bestand gegeneinander.
# =============================================================================

class TestIsVisibleForUser:
    def test_active_audience_all_is_visible_for_student(self):
        a = make_assistant(status="active", audience="all")
        assert darf_nutzen(a, zugang("student")) is True

    def test_active_audience_all_is_visible_for_teacher(self):
        a = make_assistant(status="active", audience="all")
        assert darf_nutzen(a, zugang("teacher")) is True

    def test_audience_student_visible_for_student(self):
        a = make_assistant(audience="student")
        assert darf_nutzen(a, zugang("student")) is True

    def test_audience_student_not_visible_for_teacher(self):
        a = make_assistant(audience="student")
        assert darf_nutzen(a, zugang("teacher")) is False

    def test_audience_teacher_not_visible_for_student(self):
        a = make_assistant(audience="teacher")
        assert darf_nutzen(a, zugang("student")) is False

    def test_audience_teacher_visible_for_teacher(self):
        a = make_assistant(audience="teacher")
        assert darf_nutzen(a, zugang("teacher")) is True

    def test_audience_teacher_visible_for_admin(self):
        a = make_assistant(audience="teacher")
        assert darf_nutzen(a, zugang("admin")) is True

    def test_status_draft_is_not_visible(self):
        a = make_assistant(status="draft")
        assert darf_nutzen(a, zugang("student")) is False

    def test_status_disabled_is_not_visible(self):
        a = make_assistant(status="disabled")
        assert darf_nutzen(a, zugang("student")) is False

    def test_available_from_in_future_is_not_visible(self):
        future = datetime.now(timezone.utc) + timedelta(days=1)
        a = make_assistant(available_from=future)
        assert darf_nutzen(a, zugang("student")) is False

    def test_available_until_in_past_is_not_visible(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        a = make_assistant(available_until=past)
        assert darf_nutzen(a, zugang("student")) is False

    def test_both_time_bounds_now_in_between_is_visible(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        future = datetime.now(timezone.utc) + timedelta(days=1)
        a = make_assistant(available_from=past, available_until=future)
        assert darf_nutzen(a, zugang("student")) is True

    def test_no_time_bounds_is_visible(self):
        a = make_assistant(available_from=None, available_until=None)
        assert darf_nutzen(a, zugang("student")) is True


# =============================================================================
# HTTP-Endpunkt-Tests (Mini-App, DB-Mock)
# =============================================================================

class TestListAssistantsEndpoint:
    def test_no_auth_returns_401_or_403(self):
        app = FastAPI()
        app.include_router(assistants_router)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/assistants")
        assert response.status_code in (401, 403)

    def test_empty_db_returns_empty_list(self):
        mock_db = _make_mock_db([])
        client = TestClient(_make_mini_app(mock_db))
        response = client.get("/assistants")
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_returns_assistants_for_student(self):
        a = _make_assistant_ns(id=1, name="Mathe-Hilfe", audience="student", tags=["mathe"])
        mock_db = _make_mock_db([a])
        client = TestClient(_make_mini_app(mock_db, roles=["student"]))
        response = client.get("/assistants")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["name"] == "Mathe-Hilfe"

    def test_system_prompt_not_in_response(self):
        """system_prompt darf niemals ausgeliefert werden."""
        a = _make_assistant_ns(id=2, name="Test")
        mock_db = _make_mock_db([a])
        client = TestClient(_make_mini_app(mock_db))
        response = client.get("/assistants")
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert "system_prompt" not in item


# =============================================================================
# Jeder gültige Scope ist entschieden
# =============================================================================

class TestScopeAbdeckung:
    """⚠️ **Dieselbe Liste an zwei Orten** — die Scopes, die der Router zulässt, und
    die, über die die Sichtbarkeitsregel etwas sagt.

    Ein neuer Scope, der nur in `VALID_SCOPES` landet, fiele in der Funktion durch die
    Aufzählung und wäre für niemanden sichtbar — lautlos, und der Assistent wäre
    angelegt, aber unauffindbar. Ein Wert, der **nur** hier steht, ist eine Regel für
    etwas, das es nicht gibt.

    ⚠️ Der Test entstand aus einer Gegenprobe, die grün blieb: Ein erfundener Scope
    lässt sich gar nicht speichern (CHECK-Bedingung), also war er über die Datenbank
    nicht zu prüfen. Die Gefahr liegt eine Ebene höher — beim Hinzufügen.
    """

    def test_router_und_regel_kennen_dieselben(self):
        from app.api.assistants import VALID_SCOPES
        from app.assistants.sichtbarkeit import GRUPPENSCOPES, OFFENE_SCOPES

        entschieden = GRUPPENSCOPES | OFFENE_SCOPES | {"private", "teachers"}
        assert entschieden == VALID_SCOPES, (
            f"nur im Router: {sorted(VALID_SCOPES - entschieden)} · "
            f"nur in der Regel: {sorted(entschieden - VALID_SCOPES)}"
        )

    def test_ein_unbekannter_scope_schliesst_alle_aus(self):
        """Die Funktion zählt auf, sie fällt nicht durch. Ein durchlässiges Ende gäbe
        einen neuen Scope für alle frei, während die Abfrage ihn ausschlösse."""
        a = make_assistant(scope="ausgedacht", audience="all")
        assert darf_nutzen(a, zugang("student")) is False
        assert darf_nutzen(a, zugang("teacher", "admin")) is False
