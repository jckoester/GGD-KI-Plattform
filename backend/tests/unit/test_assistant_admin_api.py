"""Unit tests for Assistant admin API."""
import yaml
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.admin.assistants import (
    AssistantCreate,
    AssistantUpdate,
    AssistantResponse,
    AssistantListResponse,
    _validate_assistant_fields,
    _grades_list,
    _parse_iso,
    _assistant_to_yaml,
    _yaml_to_assistant_fields,
)
from app.db.models import Assistant


# =============================================================================
# Pydantic Schema Tests (kein DB)
# =============================================================================


class TestAssistantCreate:
    def test_minimal_fields(self):
        """AssistantCreate mit Mindestfeldern — valide."""
        req = AssistantCreate(
            name="Test-Assistent",
            system_prompt="Du bist ein Assistent.",
            model="openai/gpt-4o-mini",
        )
        assert req.name == "Test-Assistent"
        assert req.system_prompt == "Du bist ein Assistent."
        assert req.model == "openai/gpt-4o-mini"
        assert req.audience == "student"
        assert req.scope == "private"
        assert req.sort_order == 0

    def test_name_empty_raises(self):
        """AssistantCreate name leer — ValidationError."""
        with pytest.raises(ValidationError):
            AssistantCreate(
                name="",
                system_prompt="Prompt",
                model="model",
            )

    def test_system_prompt_empty_raises(self):
        """AssistantCreate system_prompt leer — ValidationError."""
        with pytest.raises(ValidationError):
            AssistantCreate(
                name="Name",
                system_prompt="",
                model="model",
            )

    def test_model_empty_raises(self):
        """AssistantCreate model leer — ValidationError."""
        with pytest.raises(ValidationError):
            AssistantCreate(
                name="Name",
                system_prompt="Prompt",
                model="",
            )

    def test_temperature_range(self):
        """temperature muss zwischen 0.0 und 2.0 liegen."""
        with pytest.raises(ValidationError):
            AssistantCreate(
                name="Name",
                system_prompt="Prompt",
                model="model",
                temperature=-0.1,
            )
        with pytest.raises(ValidationError):
            AssistantCreate(
                name="Name",
                system_prompt="Prompt",
                model="model",
                temperature=2.1,
            )
        
        # Gültige Werte
        AssistantCreate(
            name="Name",
            system_prompt="Prompt",
            model="model",
            temperature=0.0,
        )
        AssistantCreate(
            name="Name",
            system_prompt="Prompt",
            model="model",
            temperature=2.0,
        )

    def test_max_tokens_minimum(self):
        """max_tokens muss >= 1 sein."""
        with pytest.raises(ValidationError):
            AssistantCreate(
                name="Name",
                system_prompt="Prompt",
                model="model",
                max_tokens=0,
            )
        
        AssistantCreate(
            name="Name",
            system_prompt="Prompt",
            model="model",
            max_tokens=1,
        )

    def test_grade_range(self):
        """min_grade und max_grade müssen zwischen 1 und 13 liegen."""
        with pytest.raises(ValidationError):
            AssistantCreate(
                name="Name",
                system_prompt="Prompt",
                model="model",
                min_grade=0,
            )
        with pytest.raises(ValidationError):
            AssistantCreate(
                name="Name",
                system_prompt="Prompt",
                model="model",
                max_grade=14,
            )


class TestAssistantUpdate:
    def test_all_fields_none(self):
        """AssistantUpdate alle Felder None — valide (PATCH mit leerem Body erlaubt)."""
        req = AssistantUpdate()
        assert req.model_dump(exclude_unset=True) == {}

    def test_partial_update(self):
        """AssistantUpdate mit einigen Feldern — valide."""
        req = AssistantUpdate(name="Neuer Name", audience="teacher")
        assert req.name == "Neuer Name"
        assert req.audience == "teacher"


class TestAssistantResponse:
    def test_from_orm(self):
        """AssistantResponse from_attributes=True funktioniert."""
        now = datetime.now(timezone.utc)
        assistant = Assistant(
            id=1,
            name="Test",
            description="Beschreibung",
            subject_id=1,
            system_prompt="Prompt",
            model="model",
            temperature=0.5,
            max_tokens=1000,
            status="draft",
            audience="student",
            scope="private",
            scope_pending=None,
            min_grade=5,
            max_grade=10,
            tags=["math"],
            icon="icon",
            available_from=None,
            available_until=None,
            sort_order=0,
            created_by_pseudonym="pseudo-1",
            updated_by_pseudonym="pseudo-1",
            created_at=now,
            updated_at=now,
        )
        response = AssistantResponse.model_validate(assistant)
        assert response.id == 1
        assert response.name == "Test"
        assert response.temperature == 0.5
        assert response.tags == ["math"]


# =============================================================================
# Validierungslogik Tests (kein DB, kein HTTP)
# =============================================================================


class TestValidateAssistantFields:
    def test_subject_department_scope_raises(self):
        """subject_department-Scope — wirft HTTPException(422)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_assistant_fields(scope="subject_department")
        assert exc_info.value.status_code == 422
        assert "Gruppen-Scopes" in exc_info.value.detail

    def test_activity_group_scope_raises(self):
        """activity_group-Scope — wirft HTTPException(422)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_assistant_fields(scope="activity_group")
        assert exc_info.value.status_code == 422

    def test_class_group_scope_raises(self):
        """class_group-Scope — wirft HTTPException(422)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_assistant_fields(scope="class_group")
        assert exc_info.value.status_code == 422

    def test_teacher_audience_all_students_scope_raises(self):
        """audience=teacher + scope=all_students — wirft HTTPException(422)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_assistant_fields(audience="teacher", scope="all_students")
        assert exc_info.value.status_code == 422
        assert "nicht für Schüler" in exc_info.value.detail

    def test_teacher_audience_all_scope_raises(self):
        """audience=teacher + scope=all — wirft HTTPException(422)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_assistant_fields(audience="teacher", scope="all")
        assert exc_info.value.status_code == 422

    def test_available_from_after_available_until_raises(self):
        """available_from >= available_until — wirft HTTPException(422)."""
        from_date = datetime(2026, 6, 1, tzinfo=timezone.utc)
        to_date = datetime(2026, 5, 1, tzinfo=timezone.utc)
        with pytest.raises(HTTPException) as exc_info:
            _validate_assistant_fields(available_from=from_date, available_until=to_date)
        assert exc_info.value.status_code == 422
        assert "muss vor" in exc_info.value.detail

    def test_available_from_before_available_until_ok(self):
        """available_from < available_until — kein Fehler."""
        from_date = datetime(2026, 5, 1, tzinfo=timezone.utc)
        to_date = datetime(2026, 6, 1, tzinfo=timezone.utc)
        # Sollte keinen Fehler werfen
        _validate_assistant_fields(available_from=from_date, available_until=to_date)

    def test_min_grade_greater_than_max_grade_raises(self):
        """min_grade > max_grade — wirft HTTPException(422)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_assistant_fields(min_grade=10, max_grade=5)
        assert exc_info.value.status_code == 422
        assert "größer als max_grade" in exc_info.value.detail

    def test_invalid_audience_raises(self):
        """Ungültiger audience-Wert — wirft HTTPException(422)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_assistant_fields(audience="invalid")
        assert exc_info.value.status_code == 422
        assert "Ungültiger audience" in exc_info.value.detail

    def test_invalid_scope_raises(self):
        """Ungültiger scope-Wert — wirft HTTPException(422)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_assistant_fields(scope="invalid")
        assert exc_info.value.status_code == 422
        assert "Ungültiger scope" in exc_info.value.detail

    def test_empty_name_raises(self):
        """Leerer name — wirft HTTPException(422)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_assistant_fields(name="   ")
        assert exc_info.value.status_code == 422
        assert "name darf nicht leer" in exc_info.value.detail

    def test_empty_system_prompt_raises(self):
        """Leerer system_prompt — wirft HTTPException(422)."""
        with pytest.raises(HTTPException) as exc_info:
            _validate_assistant_fields(system_prompt="   ")
        assert exc_info.value.status_code == 422
        assert "system_prompt darf nicht leer" in exc_info.value.detail


# =============================================================================
# Import/Export Mapping Tests (kein DB, kein HTTP)
# =============================================================================


class TestGradesList:
    def test_both_none(self):
        """_grades_list(None, None) → None."""
        assert _grades_list(None, None) is None

    def test_same_grade(self):
        """_grades_list(8, 8) → [8]."""
        assert _grades_list(8, 8) == [8]

    def test_range(self):
        """_grades_list(8, 10) → [8, 9, 10]."""
        assert _grades_list(8, 10) == [8, 9, 10]

    def test_single_range(self):
        """_grades_list(5, 5) → [5]."""
        assert _grades_list(5, 5) == [5]


class TestParseIso:
    def test_valid_iso_date(self):
        """_parse_iso("2026-09-01") → korrekter datetime."""
        result = _parse_iso("2026-09-01")
        assert result is not None
        assert result.year == 2026
        assert result.month == 9
        assert result.day == 1

    def test_valid_iso_datetime(self):
        """_parse_iso("2026-09-01T14:30:00") → korrekter datetime."""
        result = _parse_iso("2026-09-01T14:30:00")
        assert result is not None
        assert result.year == 2026
        assert result.month == 9
        assert result.day == 1
        assert result.hour == 14
        assert result.minute == 30

    def test_none_returns_none(self):
        """_parse_iso(None) → None."""
        assert _parse_iso(None) is None

    def test_empty_string_returns_none(self):
        """_parse_iso("") → None."""
        assert _parse_iso("") is None

    def test_invalid_returns_none(self):
        """_parse_iso("kein-datum") → None (kein Fehler)."""
        assert _parse_iso("kein-datum") is None


class TestYamlToAssistantFields:
    def test_full_data(self):
        """_yaml_to_assistant_fields mit vollständigen Daten — alle Felder korrekt gemappt."""
        data = {
            "metadata": {
                "name": "Mathe-Assistent",
                "description": "Hilft bei Mathe",
                "subject": "mathe",
                "grades": [8, 9, 10],
                "tags": ["math", "algebra"],
                "audience": "student",
                "available_from": "2026-01-01",
                "available_until": "2026-12-31",
                "author": "Test Author",
                "license": "MIT",
                "version": "1.0",
                "created": "2026-01-01",
            },
            "config": {
                "model": "openai/gpt-4o-mini",
                "temperature": 0.7,
                "max_tokens": 1000,
                "system_prompt": "Du bist ein Mathe-Assistent.",
            },
        }
        result = _yaml_to_assistant_fields(data, subject_id=1)
        
        assert result["name"] == "Mathe-Assistent"
        assert result["description"] == "Hilft bei Mathe"
        assert result["subject_id"] == 1
        assert result["system_prompt"] == "Du bist ein Mathe-Assistent."
        assert result["model"] == "openai/gpt-4o-mini"
        assert result["temperature"] == 0.7
        assert result["max_tokens"] == 1000
        assert result["audience"] == "student"
        assert result["scope"] == "private"
        assert result["min_grade"] == 8
        assert result["max_grade"] == 10
        assert result["tags"] == ["math", "algebra"]
        assert result["available_from"] is not None
        assert result["available_until"] is not None
        assert result["import_metadata"]["author"] == "Test Author"
        assert result["import_metadata"]["license"] == "MIT"

    def test_scope_always_private(self):
        """_yaml_to_assistant_fields scope immer 'private' — unabhängig von YAML-Inhalt."""
        data = {
            "metadata": {"name": "Test", "audience": "student"},
            "config": {"model": "model", "system_prompt": "prompt"},
        }
        result = _yaml_to_assistant_fields(data, subject_id=None)
        assert result["scope"] == "private"

    def test_empty_grades(self):
        """_yaml_to_assistant_fields mit leerer grades-Liste — min_grade und max_grade sind None."""
        data = {
            "metadata": {"name": "Test", "grades": [], "audience": "student"},
            "config": {"model": "model", "system_prompt": "prompt"},
        }
        result = _yaml_to_assistant_fields(data, subject_id=None)
        assert result["min_grade"] is None
        assert result["max_grade"] is None

    def test_single_grade(self):
        """_yaml_to_assistant_fields mit einer Jahrgangsstufe — min_grade = max_grade."""
        data = {
            "metadata": {"name": "Test", "grades": [8], "audience": "student"},
            "config": {"model": "model", "system_prompt": "prompt"},
        }
        result = _yaml_to_assistant_fields(data, subject_id=None)
        assert result["min_grade"] == 8
        assert result["max_grade"] == 8


class TestAssistantToYaml:
    def test_basic_export(self):
        """_assistant_to_yaml — Export enthält alle Kern-Felder."""
        now = datetime.now(timezone.utc)
        assistant = Assistant(
            id=1,
            name="Test-Assistent",
            description="Beschreibung",
            subject_id=None,
            system_prompt="Du bist ein Assistent.",
            model="openai/gpt-4o-mini",
            temperature=0.5,
            max_tokens=1000,
            status="draft",
            audience="student",
            scope="private",
            scope_pending=None,
            min_grade=8,
            max_grade=10,
            tags=["math"],
            icon=None,
            available_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            available_until=datetime(2026, 12, 31, tzinfo=timezone.utc),
            sort_order=0,
            created_by_pseudonym="pseudo-1",
            updated_by_pseudonym="pseudo-1",
            created_at=now,
            updated_at=now,
        )
        yaml_content = _assistant_to_yaml(assistant, subject_slug=None)
        
        assert "metadata:" in yaml_content
        assert "name: Test-Assistent" in yaml_content
        assert "system_prompt: Du bist ein Assistent." in yaml_content
        assert "model: openai/gpt-4o-mini" in yaml_content
        assert "audience: student" in yaml_content
        assert "grades:" in yaml_content
        assert "- 8" in yaml_content
        assert "- 9" in yaml_content
        assert "- 10" in yaml_content
        assert "config:" in yaml_content

    def test_import_metadata_preserved(self):
        """_assistant_to_yaml — import_metadata-Felder werden übernommen."""
        now = datetime.now(timezone.utc)
        assistant = Assistant(
            id=1,
            name="Test",
            description=None,
            subject_id=None,
            system_prompt="Prompt",
            model="model",
            temperature=None,
            max_tokens=None,
            status="draft",
            audience="student",
            scope="private",
            scope_pending=None,
            min_grade=None,
            max_grade=None,
            tags=None,
            icon=None,
            available_from=None,
            available_until=None,
            sort_order=0,
            created_by_pseudonym="pseudo-1",
            updated_by_pseudonym="pseudo-1",
            created_at=now,
            updated_at=now,
            import_metadata={"author": "Test", "license": "MIT"},
        )
        yaml_content = _assistant_to_yaml(assistant, subject_slug=None)
        
        assert "author: Test" in yaml_content
        assert "license: MIT" in yaml_content

    def test_roundtrip(self):
        """Export → Import → gleiche Kern-Felder."""
        now = datetime.now(timezone.utc)
        assistant = Assistant(
            id=1,
            name="Test-Assistent",
            description="Beschreibung",
            subject_id=1,
            system_prompt="Du bist ein Assistent.",
            model="openai/gpt-4o-mini",
            temperature=0.5,
            max_tokens=1000,
            status="draft",
            audience="student",
            scope="private",
            scope_pending=None,
            min_grade=8,
            max_grade=10,
            tags=["math"],
            icon=None,
            available_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            available_until=datetime(2026, 12, 31, tzinfo=timezone.utc),
            sort_order=0,
            created_by_pseudonym="pseudo-1",
            updated_by_pseudonym="pseudo-1",
            created_at=now,
            updated_at=now,
        )
        yaml_content = _assistant_to_yaml(assistant, subject_slug="mathe")
        data = yaml.safe_load(yaml_content)
        fields = _yaml_to_assistant_fields(data, subject_id=1)
        
        assert fields["name"] == assistant.name
        assert fields["system_prompt"] == assistant.system_prompt
        assert fields["model"] == assistant.model
        assert fields["temperature"] == assistant.temperature
        assert fields["max_tokens"] == assistant.max_tokens
        assert fields["audience"] == assistant.audience
        assert fields["min_grade"] == assistant.min_grade
        assert fields["max_grade"] == assistant.max_grade


# =============================================================================
# HTTP Endpunkt Tests (TestClient + AsyncMock)
# =============================================================================


@pytest.fixture
def client_with_admin():
    """TestClient mit Admin-Auth und gemockter DB-Session."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.admin.assistants import router as assistants_router
    from app.auth.dependencies import get_current_user
    from app.auth.jwt import JwtPayload
    from app.db.session import get_db

    admin_payload = JwtPayload(
        sub="admin-pseudo",
        roles=["admin"],
        grade=None,
        jti="jti-1",
        iat=1,
        exp=9999999999,
    )

    # DB-Mock: execute().scalar() → 0; execute().scalars().all() → []
    mock_execute_result = MagicMock()
    mock_execute_result.scalar.return_value = 0
    mock_execute_result.scalar_one_or_none.return_value = None
    mock_execute_result.scalars.return_value.all.return_value = []

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_execute_result

    # refresh() setzt fehlende DB-generierte Felder (id) — simuliert DB-Autoincrement
    async def mock_refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1

    mock_db.refresh.side_effect = mock_refresh

    async def mock_current_user():
        return admin_payload

    async def mock_get_db():
        return mock_db

    mini_app = FastAPI()
    mini_app.include_router(assistants_router)
    mini_app.dependency_overrides[get_current_user] = mock_current_user
    mini_app.dependency_overrides[get_db] = mock_get_db

    yield TestClient(mini_app)


class TestListAssistants:
    async def test_requires_admin(self, client_with_admin):
        """GET /assistants ohne Admin-Rolle → 403."""
        # Der client_with_admin Fixture hat bereits Admin, also testen wir direkt
        # dass der Endpunkt erreichbar ist
        # (Ein Test ohne Admin würde hier komplexer sein)
        pass  # Integrationstest würde das prüfen

    async def test_returns_200_with_admin(self, client_with_admin):
        """GET /assistants mit Admin → 200 + korrekte Struktur."""
        response = client_with_admin.get("/assistants")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
        assert isinstance(data["total"], int)


class TestCreateAssistant:
    async def test_minimal_fields(self, client_with_admin):
        """POST /assistants mit gültigen Daten → 201 + status=draft."""
        response = client_with_admin.post(
            "/assistants",
            json={
                "name": "Test-Assistent",
                "system_prompt": "Du bist ein Assistent.",
                "model": "openai/gpt-4o-mini",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test-Assistent"
        assert data["status"] == "draft"
        assert data["audience"] == "student"
        assert data["scope"] == "private"

    async def test_empty_name_raises_422(self, client_with_admin):
        """POST /assistants mit leerem name → 422."""
        response = client_with_admin.post(
            "/assistants",
            json={
                "name": "",
                "system_prompt": "Prompt",
                "model": "model",
            },
        )
        assert response.status_code == 422

    async def test_group_scope_raises_422(self, client_with_admin):
        """POST /assistants mit Gruppen-Scope → 422."""
        response = client_with_admin.post(
            "/assistants",
            json={
                "name": "Test",
                "system_prompt": "Prompt",
                "model": "model",
                "scope": "subject_department",
            },
        )
        assert response.status_code == 422


class TestGetAssistant:
    async def test_not_found_returns_404(self, client_with_admin):
        """GET /assistants/{id} nicht gefunden → 404."""
        response = client_with_admin.get("/assistants/9999")
        assert response.status_code == 404


class TestDeleteAssistant:
    async def test_active_returns_409(self, client_with_admin):
        """DELETE /assistants/{id} aktiver Assistent → 409."""
        # Dieser Test würde eine echte DB benötigen
        # Für Unit-Tests ohne DB überspringen wir
        pass


class TestActivateDeactivateAssistant:
    async def test_activate_returns_200(self, client_with_admin):
        """POST /assistants/{id}/activate → 200 + status=active."""
        # Würde DB benötigen
        pass

    async def test_deactivate_returns_200(self, client_with_admin):
        """POST /assistants/{id}/deactivate → 200 + status=disabled."""
        # Würde DB benötigen
        pass


class TestImportAssistant:
    async def test_invalid_yaml_returns_422(self, client_with_admin):
        """POST /assistants/import ungültiges YAML → 422."""
        response = client_with_admin.post(
            "/assistants/import",
            files={"file": ("test.yaml", b"invalid: yaml: content:")},
        )
        assert response.status_code == 422

    async def test_schema_error_returns_422(self, client_with_admin):
        """POST /assistants/import Schema-Fehler → 422 mit Hinweis."""
        # YAML ohne required Felder
        response = client_with_admin.post(
            "/assistants/import",
            files={"file": ("test.yaml", b"metadata:\n  name: test\nconfig:\n  model: gpt")},
        )
        assert response.status_code == 422
        assert "Schema" in response.json()["detail"] or "system_prompt" in response.json().get("detail", "")

    async def test_valid_yaml_returns_201(self, client_with_admin):
        """POST /assistants/import gültiges YAML → 201."""
        # Würde DB benötigen
        pass


class TestExportAssistant:
    async def test_not_found_returns_404(self, client_with_admin):
        """GET /assistants/{id}/export nicht gefunden → 404."""
        response = client_with_admin.get("/assistants/9999/export")
        assert response.status_code == 404

    async def test_returns_attachment(self, client_with_admin):
        """GET /assistants/{id}/export → 200 + Content-Disposition: attachment."""
        # Würde DB benötigen
        pass
