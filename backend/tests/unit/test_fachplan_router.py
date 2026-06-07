"""Unit-Tests für Bildungsplan-Router-Endpoint — band-basiert, mehr-versionsfest."""

import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.context.router import router as context_router
from app.db.models import ContextNode, ContextEdge
from app.db.session import get_db


_NOW = datetime.now(timezone.utc)


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _mock_fachplan_node(fachplan_id: UUID, subject_id: int = 1,
                        bp_version: str = "2016") -> MagicMock:
    node = MagicMock()
    node.id = fachplan_id
    node.title = "Fachplan Mathematik"
    node.category = "knowledge"
    node.content_type = "fachplan"
    node.content = None
    node.metadata_ = {"bp_version": bp_version}
    node.owner_pseudonym = None
    node.read_scope = "school"
    node.write_scope = "school"
    node.read_scope_group_id = None
    node.write_scope_group_id = None
    node.assistant_id = None
    node.subject_id = subject_id
    node.min_grade = None
    node.max_grade = None
    node.niveau = "regulär"
    node.status = "active"
    node.valid_until = None
    node.archived_at = None
    node.schuljahr = None
    node.created_at = _NOW
    node.updated_at = _NOW
    return node


def _mock_leitidee(ld_id: UUID, min_grade: int = 5, max_grade: int = 6,
                   niveau: str = "regulär", content: str | None = None) -> MagicMock:
    node = MagicMock()
    node.id = ld_id
    node.title = f"Leitidee (Kl. {min_grade}–{max_grade})"
    node.content = content
    node.content_type = "leitidee"
    node.status = "active"
    node.metadata_ = {}
    node.min_grade = min_grade
    node.max_grade = max_grade
    node.niveau = niveau
    return node


def _mock_pk_gruppe(pg_id: UUID) -> MagicMock:
    node = MagicMock()
    node.id = pg_id
    node.title = "Argumentieren"
    node.content_type = "pk_gruppe"
    node.status = "active"
    node.metadata_ = {}
    node.min_grade = None
    node.max_grade = None
    node.niveau = "regulär"
    return node


def _mock_ik(ik_id: UUID, min_grade: int = 5, max_grade: int = 6,
             niveau: str = "regulär") -> MagicMock:
    node = MagicMock()
    node.id = ik_id
    node.title = "IK 3.1.1"
    node.content_type = "ik_kompetenz"
    node.status = "active"
    node.metadata_ = {"standard_nr": 1}
    node.min_grade = min_grade
    node.max_grade = max_grade
    node.niveau = niveau
    return node


def _fake_teacher_payload() -> JwtPayload:
    return JwtPayload(sub="test_teacher", roles=["teacher"], grade=None,
                      jti="j-1", iat=1, exp=9999999999)


def _make_app(mock_db) -> FastAPI:
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


def _r_scalar(value) -> MagicMock:
    """Mock für scalar_one_or_none()-Ergebnis."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _r_all(rows) -> MagicMock:
    """Mock für .all()-Ergebnis (versions, bands)."""
    r = MagicMock()
    r.all.return_value = rows
    return r


def _r_scalars_all(nodes) -> MagicMock:
    """Mock für .scalars().all()-Ergebnis (node-Listen)."""
    r = MagicMock()
    r.scalars.return_value.all.return_value = nodes
    return r


def _band_row(min_grade: int, max_grade: int, niveau: str = "regulär") -> MagicMock:
    """Simuliert eine SQLAlchemy-Row mit min_grade/max_grade/niveau-Attributen."""
    row = MagicMock()
    row.min_grade = min_grade
    row.max_grade = max_grade
    row.niveau = niveau
    return row


def _version_row(version: str) -> MagicMock:
    """Simuliert eine SQLAlchemy-Row für bp_version-Distinct-Query (r[0] Zugriff)."""
    row = MagicMock()
    row.__getitem__ = MagicMock(return_value=version)
    return row


# Query-Reihenfolge im Endpoint (pro Fachplan-Aufruf):
# 1. fachplan laden         → _r_scalar(fachplan_node)
# 2. available_versions     → _r_all([version_row, ...])
# 3. bands                  → _r_all([band_row, ...])
# 4. top leitideen          → _r_scalars_all([...])
# pro Leitidee:
#   5. IK-Kinder            → _r_scalars_all([...])
#   6. Unter-Leitideen      → _r_scalars_all([])
# 7. PK-Gruppen             → _r_scalars_all([...])
# pro PK-Gruppe:
#   8. PK-Kompetenz-Kinder  → _r_scalars_all([...])


class TestGetFachplanBySubject:

    def test_fachplan_with_leitideen_and_ik(self):
        """Fachplan mit einer Leitidee und einem IK wird korrekt zurückgegeben."""
        fp_id = uuid4()
        ld_id = uuid4()
        ik_id = uuid4()

        fp = _mock_fachplan_node(fp_id, subject_id=1, bp_version="2016")
        ld = _mock_leitidee(ld_id, 5, 6)
        ik = _mock_ik(ik_id, 5, 6)

        db = _mock_session()
        db.execute.side_effect = [
            _r_scalar(fp),                       # fachplan
            _r_all([_version_row("2016")]),       # available_versions
            _r_all([_band_row(5, 6)]),            # bands
            _r_scalars_all([ld]),                 # top leitideen
            _r_scalars_all([ik]),                 # IK für ld
            _r_scalars_all([]),                   # unter_leitideen für ld
            _r_scalars_all([]),                   # pk_gruppen
        ]

        client = TestClient(_make_app(db))
        resp = client.get("/context/fachplan/by-subject/1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["fachplan"]["id"] == str(fp_id)
        assert len(data["leitideen"]) == 1
        assert data["leitideen"][0]["id"] == str(ld_id)
        assert len(data["leitideen"][0]["ik_kompetenzen"]) == 1
        assert data["leitideen"][0]["ik_kompetenzen"][0]["id"] == str(ik_id)

    def test_no_fachplan_for_subject(self):
        """Kein Fachplan für das Fach → leere Struktur, kein 404."""
        db = _mock_session()
        db.execute.return_value = _r_scalar(None)

        client = TestClient(_make_app(db))
        resp = client.get("/context/fachplan/by-subject/999")

        assert resp.status_code == 200
        data = resp.json()
        assert data["fachplan"] is None
        assert data["leitideen"] == []
        assert data["pk_gruppen"] == []
        assert data["can_edit"] is False

    def test_bands_returned_correctly(self):
        """bands enthält die erwarteten Tripel mit Labels."""
        fp_id = uuid4()
        fp = _mock_fachplan_node(fp_id, subject_id=1, bp_version="2016")

        db = _mock_session()
        db.execute.side_effect = [
            _r_scalar(fp),
            _r_all([_version_row("2016")]),
            _r_all([_band_row(5, 6), _band_row(7, 8), _band_row(11, 12, "basis"), _band_row(11, 12, "leistung")]),
            _r_scalars_all([]),   # top leitideen für default band (5-6)
            _r_scalars_all([]),   # pk_gruppen
        ]

        client = TestClient(_make_app(db))
        resp = client.get("/context/fachplan/by-subject/1")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["bands"]) == 4
        labels = [b["label"] for b in data["bands"]]
        assert "Kl. 5–6" in labels
        assert "Kl. 11–12 · Basis" in labels
        assert "Kl. 11–12 · Leistung" in labels
        # Default-Band ist das erste
        assert data["selected_band"]["min_grade"] == 5

    def test_bp_version_filter_loads_correct_fachplan(self):
        """Mit bp_version='2016.V2' wird der V2-Fachplan geladen."""
        fp_v2_id = uuid4()
        fp_v2 = _mock_fachplan_node(fp_v2_id, subject_id=2, bp_version="2016.V2")

        db = _mock_session()
        db.execute.side_effect = [
            _r_scalar(fp_v2),
            _r_all([_version_row("2016"), _version_row("2016.V2")]),
            _r_all([_band_row(5, 6)]),
            _r_scalars_all([]),
            _r_scalars_all([]),
        ]

        client = TestClient(_make_app(db))
        resp = client.get("/context/fachplan/by-subject/2?bp_version=2016.V2")

        assert resp.status_code == 200
        data = resp.json()
        assert data["fachplan"]["id"] == str(fp_v2_id)
        assert data["bp_version"] == "2016.V2"
        assert len(data["available_versions"]) == 2

    def test_band_filter_selects_correct_leitideen(self):
        """min_grade/max_grade/niveau filtert auf das korrekte Band."""
        fp_id = uuid4()
        ld_basis_id = uuid4()
        ld_leistung_id = uuid4()

        fp = _mock_fachplan_node(fp_id, bp_version="2016")
        ld_basis = _mock_leitidee(ld_basis_id, 11, 12, "basis")

        db = _mock_session()
        db.execute.side_effect = [
            _r_scalar(fp),
            _r_all([_version_row("2016")]),
            _r_all([_band_row(11, 12, "basis"), _band_row(11, 12, "leistung")]),
            _r_scalars_all([ld_basis]),   # nur Basis-Leitidee
            _r_scalars_all([]),           # IK für ld_basis
            _r_scalars_all([]),           # unter_leitideen
            _r_scalars_all([]),           # pk_gruppen
        ]

        client = TestClient(_make_app(db))
        resp = client.get("/context/fachplan/by-subject/1?min_grade=11&max_grade=12&niveau=basis")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["leitideen"]) == 1
        assert data["leitideen"][0]["niveau"] == "basis"
        assert data["selected_band"]["niveau"] == "basis"

    def test_zwei_fachplaene_kein_multiple_results_found(self):
        """Zwei Fachpläne pro Fach werfen kein MultipleResultsFound mehr."""
        fp_id = uuid4()
        fp = _mock_fachplan_node(fp_id, subject_id=2, bp_version="2016")

        db = _mock_session()
        # scalar_one_or_none wird NICHT mehr verwendet (limit(1) + scalar_one_or_none statt
        # scalar_one) — der Mock liefert einfach den ersten Fachplan zurück
        db.execute.side_effect = [
            _r_scalar(fp),
            _r_all([_version_row("2016"), _version_row("2016.V2")]),
            _r_all([_band_row(5, 6)]),
            _r_scalars_all([]),
            _r_scalars_all([]),
        ]

        client = TestClient(_make_app(db))
        resp = client.get("/context/fachplan/by-subject/2")

        assert resp.status_code == 200
        assert len(resp.json()["available_versions"]) == 2

    def test_recursive_unter_leitideen(self):
        """Unter-Leitideen erscheinen in unter_leitideen des Eltern-Knotens."""
        fp_id = uuid4()
        ld_id = uuid4()
        unter_id = uuid4()
        ik_id = uuid4()

        fp = _mock_fachplan_node(fp_id, bp_version="2016")
        ld = _mock_leitidee(ld_id, 5, 6)
        unter = _mock_leitidee(unter_id, 5, 6)
        ik = _mock_ik(ik_id, 5, 6)

        db = _mock_session()
        db.execute.side_effect = [
            _r_scalar(fp),
            _r_all([_version_row("2016")]),
            _r_all([_band_row(5, 6)]),
            _r_scalars_all([ld]),        # top leitideen
            _r_scalars_all([]),          # IK für ld (keine direkt)
            _r_scalars_all([unter]),     # unter_leitideen von ld
            _r_scalars_all([ik]),        # IK für unter
            _r_scalars_all([]),          # unter_leitideen von unter
            _r_scalars_all([]),          # pk_gruppen
        ]

        client = TestClient(_make_app(db))
        resp = client.get("/context/fachplan/by-subject/1")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["leitideen"]) == 1
        top = data["leitideen"][0]
        assert len(top["unter_leitideen"]) == 1
        assert top["unter_leitideen"][0]["id"] == str(unter_id)
        assert len(top["unter_leitideen"][0]["ik_kompetenzen"]) == 1

    def test_pk_gruppen_returned_regardless_of_band(self):
        """PKs mit min_grade=None erscheinen trotz aktivem Band-Filter (Regression)."""
        fp_id = uuid4()
        ld_id = uuid4()
        pg_id = uuid4()

        fp = _mock_fachplan_node(fp_id, bp_version="2016")
        ld = _mock_leitidee(ld_id, 5, 6)
        pg = _mock_pk_gruppe(pg_id)

        db = _mock_session()
        db.execute.side_effect = [
            _r_scalar(fp),                    # fachplan
            _r_all([_version_row("2016")]),   # available_versions
            _r_all([_band_row(5, 6)]),        # bands (default 5–6)
            _r_scalars_all([ld]),             # top leitideen
            _r_scalars_all([]),              # IK für ld
            _r_scalars_all([]),              # unter_leitideen für ld
            _r_scalars_all([pg]),            # pk_gruppen (grade=NULL, soll trotzdem kommen)
            _r_scalars_all([]),              # pk_kompetenzen für pg
        ]

        client = TestClient(_make_app(db))
        resp = client.get("/context/fachplan/by-subject/1")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["pk_gruppen"]) == 1
        assert data["pk_gruppen"][0]["id"] == str(pg_id)

    def test_available_versions_in_response(self):
        """available_versions gibt alle BP-Versionen des Fachs zurück."""
        fp_id = uuid4()
        fp = _mock_fachplan_node(fp_id, bp_version="2016")

        db = _mock_session()
        db.execute.side_effect = [
            _r_scalar(fp),
            _r_all([_version_row("2016"), _version_row("2016.V2")]),
            _r_all([_band_row(5, 6)]),
            _r_scalars_all([]),
            _r_scalars_all([]),
        ]

        client = TestClient(_make_app(db))
        resp = client.get("/context/fachplan/by-subject/1")

        data = resp.json()
        assert data["available_versions"] == ["2016", "2016.V2"]


class TestListNodesBpVersionFilter:
    """Tests für bp_version-Param in GET /context/nodes."""

    def test_bp_version_param_accepted(self):
        """bp_version-Param wird ohne Fehler akzeptiert."""
        db = _mock_session()
        db.execute.return_value = _r_scalars_all([])

        client = TestClient(_make_app(db))
        resp = client.get("/context/nodes?content_type=ik_kompetenz&bp_version=2016.V2")
        assert resp.status_code == 200

    def test_without_bp_version_unchanged(self):
        """Ohne bp_version-Param: unverändertes Verhalten (kein Fehler)."""
        db = _mock_session()
        db.execute.return_value = _r_scalars_all([])

        client = TestClient(_make_app(db))
        resp = client.get("/context/nodes?content_type=ik_kompetenz")
        assert resp.status_code == 200
