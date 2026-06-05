"""Unit-Tests für Bildungsplan-Router-Endpoint (KS-Navigation-Kontext, AP 3)."""

import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.context.router import router as context_router
from app.db.models import ContextNode, ContextEdge
from app.db.session import get_db


_NOW = datetime.now(timezone.utc)


def _mock_fachplan_node(fachplan_id: UUID, subject_id: int = 1) -> MagicMock:
    """Erstellt ein Mock-ContextNode das alle ContextNodeRead-Pflichtfelder hat."""
    node = MagicMock()
    node.id = fachplan_id
    node.title = "Fachplan Mathematik"
    node.category = "knowledge"
    node.content_type = "fachplan"
    node.content = None
    node.metadata_ = {}
    node.owner_pseudonym = None
    node.read_scope = "school"
    node.write_scope = "school"
    node.read_scope_group_id = None
    node.write_scope_group_id = None
    node.assistant_id = None
    node.subject_id = subject_id
    node.min_grade = None
    node.max_grade = None
    node.status = "active"
    node.valid_until = None
    node.archived_at = None
    node.schuljahr = None
    node.created_at = _NOW
    node.updated_at = _NOW
    return node


def _fake_teacher_payload() -> JwtPayload:
    return JwtPayload(sub="test_teacher", roles=["teacher"], grade=None,
                      jti="j-1", iat=1, exp=9999999999)


def _make_app(mock_db) -> FastAPI:
    """Test-App mit Context-Router und overridden Dependencies."""
    app = FastAPI()
    app.include_router(context_router)

    async def fake_user():
        return _fake_teacher_payload()

    async def fake_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = fake_user
    app.dependency_overrides[get_db] = fake_db
    return app


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    return session


class TestGetFachplanBySubject:
    """Tests für GET /fachplan/by-subject/{subject_id}"""

    def test_fachplan_with_leitideen_and_ik(self):
        """Test: Fachplan mit Leitideen und IK-Kompetenz-Kindern wird korrekt geladen."""
        fachplan_id = UUID("10000000-0000-0000-0000-000000000001")
        leitidee_id = UUID("20000000-0000-0000-0000-000000000001")
        ik_id = UUID("30000000-0000-0000-0000-000000000001")

        mock_fachplan = _mock_fachplan_node(fachplan_id, subject_id=1)

        mock_leitidee = MagicMock()
        mock_leitidee.id = leitidee_id
        mock_leitidee.title = "Leitidee Zahl"
        mock_leitidee.content_type = "leitidee"
        mock_leitidee.status = "active"
        mock_leitidee.metadata_ = {}

        mock_ik = MagicMock()
        mock_ik.id = ik_id
        mock_ik.title = "IK 3.1.1"
        mock_ik.content_type = "ik_kompetenz"
        mock_ik.status = "active"
        mock_ik.metadata_ = {"standard_nr": 1}

        db = _mock_session()

        # Query-Ergebnisse in Reihenfolge: fachplan, leitideen, IK, PK-Gruppen
        r_fachplan = MagicMock()
        r_fachplan.scalar_one_or_none = MagicMock(return_value=mock_fachplan)

        r_leitideen = MagicMock()
        r_leitideen.scalars.return_value.all = MagicMock(return_value=[mock_leitidee])

        r_ik = MagicMock()
        r_ik.scalars.return_value.all = MagicMock(return_value=[mock_ik])

        r_pk_gruppen = MagicMock()
        r_pk_gruppen.scalars.return_value.all = MagicMock(return_value=[])

        db.execute.side_effect = [
            r_fachplan, r_leitideen, r_ik, r_pk_gruppen,
        ]

        client = TestClient(_make_app(db))
        response = client.get("/context/fachplan/by-subject/1")

        assert response.status_code == 200
        data = response.json()
        assert data["fachplan"] is not None
        assert data["fachplan"]["id"] == str(fachplan_id)
        assert len(data["leitideen"]) == 1
        assert data["leitideen"][0]["id"] == str(leitidee_id)
        assert len(data["leitideen"][0]["ik_kompetenzen"]) == 1

    def test_no_fachplan_for_subject(self):
        """Test: Kein Fachplan für das Fach → leere Struktur zurück, kein 404."""
        db = _mock_session()

        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=None)
        db.execute.return_value = r

        client = TestClient(_make_app(db))
        response = client.get("/context/fachplan/by-subject/999")

        assert response.status_code == 200
        data = response.json()
        assert data["fachplan"] is None
        assert data["leitideen"] == []
        assert data["pk_gruppen"] == []
        assert data["can_edit"] is False

    def test_fachplan_with_grade_filter(self):
        """Test: Filterung nach Jahrgangsstufe — nur passende IK-Kompetenz."""
        fachplan_id = UUID("10000000-0000-0000-0000-000000000001")
        leitidee_id = UUID("20000000-0000-0000-0000-000000000001")
        ik_5_6_id = UUID("30000000-0000-0000-0000-000000000001")
        ik_7_8_id = UUID("30000000-0000-0000-0000-000000000002")

        mock_fachplan = _mock_fachplan_node(fachplan_id, subject_id=1)

        mock_leitidee = MagicMock()
        mock_leitidee.id = leitidee_id
        mock_leitidee.title = "Leitidee Zahl"
        mock_leitidee.content_type = "leitidee"
        mock_leitidee.status = "active"
        mock_leitidee.metadata_ = {}

        mock_ik_5_6 = MagicMock()
        mock_ik_5_6.id = ik_5_6_id
        mock_ik_5_6.title = "IK 5/6"
        mock_ik_5_6.content_type = "ik_kompetenz"
        mock_ik_5_6.status = "active"
        mock_ik_5_6.metadata_ = {"grade_band": "5-6"}

        mock_ik_7_8 = MagicMock()
        mock_ik_7_8.id = ik_7_8_id
        mock_ik_7_8.title = "IK 7/8"
        mock_ik_7_8.content_type = "ik_kompetenz"
        mock_ik_7_8.status = "active"
        mock_ik_7_8.metadata_ = {"grade_band": "7-8"}

        db = _mock_session()

        r_fachplan = MagicMock()
        r_fachplan.scalar_one_or_none = MagicMock(return_value=mock_fachplan)

        r_leitideen = MagicMock()
        r_leitideen.scalars.return_value.all = MagicMock(return_value=[mock_leitidee])

        # Endpoint bekommt beide IK, filtert client-seitig nach grade_band
        r_ik = MagicMock()
        r_ik.scalars.return_value.all = MagicMock(return_value=[mock_ik_5_6, mock_ik_7_8])

        r_pk_gruppen = MagicMock()
        r_pk_gruppen.scalars.return_value.all = MagicMock(return_value=[])

        db.execute.side_effect = [r_fachplan, r_leitideen, r_ik, r_pk_gruppen]

        client = TestClient(_make_app(db))
        response = client.get("/context/fachplan/by-subject/1?grade=5")

        assert response.status_code == 200
        data = response.json()
        assert len(data["leitideen"]) == 1
        assert len(data["leitideen"][0]["ik_kompetenzen"]) == 1
        assert data["leitideen"][0]["ik_kompetenzen"][0]["title"] == "IK 5/6"
