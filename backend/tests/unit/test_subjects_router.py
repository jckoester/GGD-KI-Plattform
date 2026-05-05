"""Unit tests für den Subjects-Endpunkt."""
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.subjects import router as subjects_router


class MockScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


def _make_db_mock(subjects: list) -> MagicMock:
    mock_result = MagicMock()
    mock_result.scalars.return_value = MockScalarResult(subjects)
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


def _make_mini_app(mock_db) -> FastAPI:
    app = FastAPI()
    from app.db.session import get_db

    app.dependency_overrides[get_db] = lambda: mock_db
    app.include_router(subjects_router)
    return app


def _make_subject(**kwargs) -> MagicMock:
    defaults = dict(id=1, slug="mathematik", name="Mathematik",
                    icon="square-radical", color="#3b82f6",
                    min_grade=5, max_grade=13, sort_order=10)
    defaults.update(kwargs)
    s = MagicMock()
    for k, v in defaults.items():
        setattr(s, k, v)
    return s


# =============================================================================
# Tests für GET /subjects
# =============================================================================

def test_get_subjects_returns_empty_list():
    """GET /subjects gibt leere Liste zurück, wenn keine Fächer vorhanden."""
    client = TestClient(_make_mini_app(_make_db_mock([])))
    response = client.get("/subjects")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_get_subjects_returns_subjects_in_db_order():
    """GET /subjects gibt Fächer in der Reihenfolge zurück, die die DB liefert."""
    s1 = _make_subject(id=1, slug="deutsch", sort_order=10)
    s2 = _make_subject(id=2, slug="mathematik", sort_order=20)
    client = TestClient(_make_mini_app(_make_db_mock([s1, s2])))

    response = client.get("/subjects")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert items[0]["slug"] == "deutsch"
    assert items[1]["slug"] == "mathematik"


def test_get_subjects_contains_all_fields():
    """GET /subjects Antwort enthält alle erwarteten Felder."""
    client = TestClient(_make_mini_app(_make_db_mock([_make_subject()])))
    item = client.get("/subjects").json()["items"][0]

    for field in ("id", "slug", "name", "icon", "color", "min_grade", "max_grade", "sort_order"):
        assert field in item, f"Feld '{field}' fehlt in der Antwort"


def test_get_subjects_icon_and_color_can_be_null():
    """Felder icon, color, min_grade, max_grade können null sein."""
    s = _make_subject(icon=None, color=None, min_grade=None, max_grade=None)
    client = TestClient(_make_mini_app(_make_db_mock([s])))
    item = client.get("/subjects").json()["items"][0]

    assert item["icon"] is None
    assert item["color"] is None
    assert item["min_grade"] is None
    assert item["max_grade"] is None
