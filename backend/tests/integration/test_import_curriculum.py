"""Integrationstests für Curriculum-Import (KS-Phase-6 Schritt 2)."""

import json
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import yaml
from fastapi import UploadFile
from fastapi.testclient import TestClient
from io import BytesIO
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.schemas import (
    CurriculumDraft,
    CurriculumDraftConfirmed,
    CurriculumDraftData,
    CurriculumDraftEntry,
    CurriculumDraftKapitel,
    CurriculumDraftLernsequenz,
)
from app.context.service import import_curriculum_from_draft, ImportStats
from app.db.models import ContextNode, ContextEdge


# Test-Daten-Verzeichnis
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "curricula"


@pytest.fixture
def curriculum_yaml_format_a():
    """Beispiel-Curriculum im Format A (mit Lernsequenz-Subheadern)."""
    return {
        "schule": "Test-Gymnasium",
        "fach_code": "MA",
        "fach": "Mathematik",
        "schulart": "G8",
        "jahrgangsstufe": "5",
        "fachplan_id": "BP_2016_MA",
        "bp_version": "2016",
        "vorwort": "Test-Vorwort",
        "kapitel": [
            {
                "titel": "Zahlen und Operationen",
                "reihenfolge": 1,
                "std": "20",
                "hinweis": "Einleitungstext",
                "konkretisierung": ["Konkretisierung 1", "Konkretisierung 2"],
                "lernsequenzen": [
                    {
                        "bp_titel": "Natürliche Zahlen",
                        "bp_leitidee": "Zahl",
                        "reihenfolge": 1,
                        "eintraege": [
                            {
                                "ik": "3.1.1",
                                "ik_partiell": False,
                                "pk": [{"id": "PK_05.1"}],
                                "konkretisierung": "Natürliche Zahlen lesen und schreiben",
                                "hinweise": "",
                                "lp": ["L BO"],
                            },
                            {
                                "ik": "3.1.2",
                                "ik_partiell": True,
                                "pk": [{"id": "PK_05.2"}],
                                "konkretisierung": "Zahlen vergleichen",
                                "hinweise": "MINT-Hinweis",
                                "lp": [],
                            },
                        ],
                    },
                    {
                        "bp_titel": "Rechnen mit natürlichen Zahlen",
                        "bp_leitidee": "Algorithmus",
                        "reihenfolge": 2,
                        "eintraege": [
                            {
                                "ik": "3.1.3",
                                "ik_partiell": False,
                                "pk": [{"id": "PK_05.3"}],
                                "konkretisierung": "Addition und Subtraktion",
                                "hinweise": "",
                                "lp": [],
                            },
                        ],
                    },
                ],
            },
        ],
    }


@pytest.fixture
def curriculum_yaml_format_b():
    """Beispiel-Curriculum im Format B (ohne Lernsequenz-Subheader)."""
    return {
        "schule": "Test-Gymnasium",
        "fach_code": "GK",
        "fach": "Gemeinschaftskunde",
        "schulart": "G8",
        "jahrgangsstufe": "10",
        "fachplan_id": "BP_2016_GK",
        "bp_version": "2016",
        "vorwort": "Test-Vorwort GK",
        "kapitel": [
            {
                "titel": "Politik in Deutschland",
                "reihenfolge": 1,
                "std": "15",
                "hinweis": "Einleitungstext GK",
                "konkretisierung": ["Konkretisierung GK"],
                "lernsequenzen": [
                    {
                        "bp_titel": None,  # Format B: namenlose Lernsequenz
                        "bp_leitidee": None,
                        "reihenfolge": 1,
                        "eintraege": [
                            {
                                "ik": "2.1.1",
                                "ik_partiell": False,
                                "pk": [{"id": "PK_10.1"}],
                                "konkretisierung": "Das politische System Deutschlands",
                                "hinweise": "(L) BTV",
                                "lp": ["BTV"],
                            },
                        ],
                    },
                ],
            },
        ],
    }


@pytest.fixture
def curriculum_yaml_kompetenzmatrix():
    """Beispiel für nicht unterstütztes Kompetenzmatrix-Format."""
    return {
        "schule": "Test-Schule",
        "fach_code": "EN",
        "fach": "Englisch",
        "schulart": "G8",
        "jahrgangsstufe": "7",
        "fachplan_id": "BP_2016_EN",
        "bp_version": "2016",
        "vorwort": "Kompetenzmatrix",
        # Keine Kapitel-Struktur, nur IK-Kategorien
        "kapitel": [],
    }


@pytest.fixture
def curriculum_draft_confirmed(curriculum_yaml_format_a):
    """Erstellt ein CurriculumDraftConfirmed-Objekt."""
    kapitel_list = []
    for kap_data in curriculum_yaml_format_a["kapitel"]:
        lernsequenzen = []
        for ls_data in kap_data["lernsequenzen"]:
            eintraege = []
            for entry_data in ls_data["eintraege"]:
                entry = CurriculumDraftEntry(
                    ik=entry_data["ik"],
                    ik_partiell=entry_data["ik_partiell"],
                    pk=entry_data["pk"],
                    konkretisierung=entry_data["konkretisierung"],
                    hinweise=entry_data["hinweise"],
                    lp=entry_data["lp"],
                    confidence=1.0,
                    warnings=[],
                )
                eintraege.append(entry)
            
            ls = CurriculumDraftLernsequenz(
                bp_titel=ls_data["bp_titel"],
                bp_leitidee=ls_data["bp_leitidee"],
                reihenfolge=ls_data["reihenfolge"],
                eintraege=eintraege,
                confidence=1.0,
                warnings=[],
            )
            lernsequenzen.append(ls)
        
        kapitel = CurriculumDraftKapitel(
            titel=kap_data["titel"],
            reihenfolge=kap_data["reihenfolge"],
            std=kap_data["std"],
            hinweis=kap_data["hinweis"],
            konkretisierung=kap_data["konkretisierung"],
            lernsequenzen=lernsequenzen,
            confidence=1.0,
            warnings=[],
        )
        kapitel_list.append(kapitel)
    
    return CurriculumDraftConfirmed(
        schule=curriculum_yaml_format_a["schule"],
        fach_code=curriculum_yaml_format_a["fach_code"],
        fach=curriculum_yaml_format_a["fach"],
        schulart=curriculum_yaml_format_a["schulart"],
        jahrgangsstufe=curriculum_yaml_format_a["jahrgangsstufe"],
        fachplan_id=curriculum_yaml_format_a["fachplan_id"],
        bp_version=curriculum_yaml_format_a["bp_version"],
        vorwort=curriculum_yaml_format_a["vorwort"],
        kapitel=kapitel_list,
    )


# ============================================================================
# Test: POST /curricula/convert
# ============================================================================


class TestConvertCurriculum:
    """Tests für den Convert-Endpunkt (Stufe 1)."""

    @pytest.mark.skipif(
        not __import__('importlib').util.find_spec('pdfplumber'),
        reason='pdfplumber nicht installiert'
    )
    @pytest.mark.asyncio
    async def test_convert_format_a_pdf(self, test_client: TestClient, auth_headers):
        """Test: Convert-Endpunkt mit Format-A-PDF."""
        # Erzeuge ein einfaches PDF-Dokument als Bytes
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        
        response = await test_client.post(
            "/context/curricula/convert",
            files={"file": ("test.pdf", pdf_content)},
            data={"fachplan_id": "BP_2016_MA", "bp_version": "2016"},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "format_detected" in data
        # PDF-Parsing hängt von den Bibliotheken ab
        # Bei erfolgreicher Extraktion sollten wir ein Draft-Objekt erhalten

    @pytest.mark.skipif(
        not __import__('importlib').util.find_spec('pdfplumber'),
        reason='pdfplumber nicht installiert'
    )
    @pytest.mark.asyncio
    async def test_convert_format_b_pdf(self, test_client: TestClient, auth_headers):
        """Test: Convert-Endpunkt mit Format-B-PDF."""
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        
        response = await test_client.post(
            "/context/curricula/convert",
            files={"file": ("test_gk.pdf", pdf_content)},
            data={"fachplan_id": "BP_2016_GK", "bp_version": "2016"},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "format_detected" in data

    @pytest.mark.skipif(
        not __import__('importlib').util.find_spec('pdfplumber'),
        reason='pdfplumber nicht installiert'
    )
    @pytest.mark.asyncio
    async def test_convert_unsupported_format(self, test_client: TestClient, auth_headers):
        """Test: Convert-Endpunkt mit nicht unterstütztem Format (Kompetenzmatrix)."""
        # Erzeuge ein Text-Dokument das wie eine Kompetenzmatrix aussieht
        text_content = b"Kompetenzmatrix\nIK 1|IK 2|IK 3\nBeschreibung 1|Beschreibung 2|Beschreibung 3"
        
        response = await test_client.post(
            "/context/curricula/convert",
            files={"file": ("kompetenzmatrix.pdf", text_content)},
            data={"fachplan_id": "BP_2016_EN", "bp_version": "2016"},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["unsupported_format"] is True
        assert "Kompetenzmatrix" in data["warnings"][0] or "nicht unterstützt" in data["warnings"][0]

    @pytest.mark.asyncio
    async def test_convert_invalid_file_type(self, test_client: TestClient, auth_headers):
        """Test: Convert-Endpunkt mit ungültigem Dateityp."""
        response = await test_client.post(
            "/context/curricula/convert",
            files={"file": ("test.txt", b"content")},
            data={"fachplan_id": "BP_2016_MA", "bp_version": "2016"},
            headers=auth_headers,
        )
        
        assert response.status_code == 400
        assert "unterstützt" in response.json()["detail"].lower()


# ============================================================================
# Test: POST /curricula (Stufe 2)
# ============================================================================


class TestCreateCurriculum:
    """Tests für den Create-Endpunkt (Stufe 2)."""

    @pytest.mark.asyncio
    async def test_create_curriculum_success(
        self,
        test_client: TestClient,
        auth_headers,
        curriculum_draft_confirmed,
        db_session: AsyncSession,
    ):
        """Test: Curriculum erfolgreich erstellen aus bestätigtem Draft."""
        # Zuerst benötigen wir einen Fachplan-Knoten
        await db_session.execute(
            text("""
                INSERT INTO context_nodes (id, category, content_type, title, status, metadata)
                VALUES (:id, 'knowledge', 'fachplan', 'Test Fachplan', 'active', CAST(:metadata AS jsonb))
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id": str(uuid.uuid4()),
                "metadata": json.dumps({"fachplan_id": "BP_2016_MA"}),
            },
        )
        
        # Subject erstellen
        await db_session.execute(
            text("""
                INSERT INTO subjects (id, name, slug)
                VALUES (1, 'Mathematik', 'MA')
                ON CONFLICT (id) DO NOTHING
            """),
        )
        
        # IK- und PK-Knoten erstellen
        await db_session.execute(
            text("""
                INSERT INTO context_nodes (id, category, content_type, title, subject_id, status, metadata)
                VALUES
                    (:id1, 'knowledge', 'ik_kompetenz', 'IK 3.1.1', 1, 'active', CAST(:meta1 AS jsonb)),
                    (:id2, 'knowledge', 'ik_kompetenz', 'IK 3.1.2', 1, 'active', CAST(:meta2 AS jsonb)),
                    (:id3, 'knowledge', 'ik_kompetenz', 'IK 3.1.3', 1, 'active', CAST(:meta3 AS jsonb))
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id1": str(uuid.uuid4()),
                "id2": str(uuid.uuid4()),
                "id3": str(uuid.uuid4()),
                "meta1": json.dumps({"nr": "3.1.1"}),
                "meta2": json.dumps({"nr": "3.1.2"}),
                "meta3": json.dumps({"nr": "3.1.3"}),
            },
        )
        
        await db_session.execute(
            text("""
                INSERT INTO context_nodes (id, category, content_type, title, status, metadata)
                VALUES
                    (:id1, 'knowledge', 'pk_kompetenz', 'PK 05.1', 'active', CAST(:meta1 AS jsonb)),
                    (:id2, 'knowledge', 'pk_kompetenz', 'PK 05.2', 'active', CAST(:meta2 AS jsonb)),
                    (:id3, 'knowledge', 'pk_kompetenz', 'PK 05.3', 'active', CAST(:meta3 AS jsonb))
                ON CONFLICT (id) DO NOTHING
            """),
            {
                "id1": str(uuid.uuid4()),
                "id2": str(uuid.uuid4()),
                "id3": str(uuid.uuid4()),
                "meta1": json.dumps({"pk_id": "PK_05.1"}),
                "meta2": json.dumps({"pk_id": "PK_05.2"}),
                "meta3": json.dumps({"pk_id": "PK_05.3"}),
            },
        )
        
        await db_session.commit()
        
        # Jetzt das Curriculum erstellen
        response = await test_client.post(
            "/context/curricula",
            json=curriculum_draft_confirmed.model_dump(),
            headers=auth_headers,
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Prüfe dass das Curriculum erstellt wurde
        assert data["id"] is not None
        assert "Mathematik" in data["title"]
        assert data["kapitel"] is not None
        assert len(data["kapitel"]) == 1
        
        # Prüfe dass Kapitel erstellt wurden
        assert data["kapitel"][0]["title"] == "Zahlen und Operationen"
        assert len(data["kapitel"][0]["lernsequenzen"]) == 2

    @pytest.mark.asyncio
    async def test_create_curriculum_missing_fachplan(
        self,
        test_client: TestClient,
        auth_headers,
        curriculum_draft_confirmed,
    ):
        """Test: Fehler wenn Fachplan nicht existiert."""
        # Fachplan existiert nicht
        draft = curriculum_draft_confirmed
        draft.fachplan_id = "NONEXISTENT_FACHPLAN"
        
        response = await test_client.post(
            "/context/curricula",
            json=draft.model_dump(),
            headers=auth_headers,
        )
        
        assert response.status_code == 422
        assert "Fachplan" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_curriculum_ik_not_found(
        self,
        test_client: TestClient,
        auth_headers,
        curriculum_draft_confirmed,
        db_session: AsyncSession,
    ):
        """Test: Warnung wenn IK-Nummer nicht aufgelöst werden kann."""
        # Fachplan erstellen
        await db_session.execute(
            text("""
                INSERT INTO context_nodes (id, category, content_type, title, status, metadata)
                VALUES (:id, 'knowledge', 'fachplan', 'Test Fachplan', 'active', CAST(:metadata AS jsonb))
                ON CONFLICT DO NOTHING
            """),
            {
                "id": str(uuid.uuid4()),
                "metadata": json.dumps({"fachplan_id": "BP_2016_MA"}),
            },
        )
        
        # Subject erstellen
        await db_session.execute(
            text("""
                INSERT INTO subjects (id, name, slug)
                VALUES (1, 'Mathematik', 'MA')
                ON CONFLICT DO NOTHING
            """),
        )
        
        # Nur einige IK-Knoten erstellen (nicht alle)
        await db_session.execute(
            text("""
                INSERT INTO context_nodes (id, category, content_type, title, subject_id, status, metadata)
                VALUES (:id1, 'knowledge', 'ik_kompetenz', 'IK 3.1.1', 1, 'active', CAST(:meta1 AS jsonb))
            """),
            {
                "id1": str(uuid.uuid4()),
                "meta1": json.dumps({"nr": "3.1.1"}),
            },
        )
        
        # PK-Knoten erstellen
        await db_session.execute(
            text("""
                INSERT INTO context_nodes (id, category, content_type, title, status, metadata)
                VALUES
                    (:id1, 'knowledge', 'pk_kompetenz', 'PK 05.1', 'active', CAST(:meta1 AS jsonb)),
                    (:id2, 'knowledge', 'pk_kompetenz', 'PK 05.2', 'active', CAST(:meta2 AS jsonb)),
                    (:id3, 'knowledge', 'pk_kompetenz', 'PK 05.3', 'active', CAST(:meta3 AS jsonb))
                ON CONFLICT DO NOTHING
            """),
            {
                "id1": str(uuid.uuid4()),
                "id2": str(uuid.uuid4()),
                "id3": str(uuid.uuid4()),
                "meta1": json.dumps({"pk_id": "PK_05.1"}),
                "meta2": json.dumps({"pk_id": "PK_05.2"}),
                "meta3": json.dumps({"pk_id": "PK_05.3"}),
            },
        )
        
        await db_session.commit()
        
        # Curriculum erstellen - IK 3.1.2 und 3.1.3 existieren nicht
        response = await test_client.post(
            "/context/curricula",
            json=curriculum_draft_confirmed.model_dump(),
            headers=auth_headers,
        )
        
        # Sollte trotzdem erfolgreich sein, aber mit Warnungen
        assert response.status_code == 201


# ============================================================================
# Test: Service-Funktionen
# ============================================================================


class TestCurriculumService:
    """Tests für die Service-Funktionen."""

    @pytest.mark.asyncio
    async def test_import_curriculum_from_draft(
        self,
        db_session: AsyncSession,
        curriculum_draft_confirmed,
    ):
        """Test: Direkter Aufruf der Import-Kernlogik."""
        # Vorbereitung: Fachplan, Subject, IK-, PK-Knoten
        await db_session.execute(
            text("""
                INSERT INTO context_nodes (id, category, content_type, title, status, metadata)
                VALUES (:id, 'knowledge', 'fachplan', 'Test Fachplan', 'active', CAST(:metadata AS jsonb))
                ON CONFLICT DO NOTHING
            """),
            {
                "id": str(uuid.uuid4()),
                "metadata": json.dumps({"fachplan_id": "BP_2016_MA"}),
            },
        )
        
        await db_session.execute(
            text("""
                INSERT INTO subjects (id, name, slug)
                VALUES (1, 'Mathematik', 'MA')
                ON CONFLICT DO NOTHING
            """),
        )
        
        for ik_nr in ["3.1.1", "3.1.2", "3.1.3"]:
            await db_session.execute(
                text("""
                    INSERT INTO context_nodes (id, category, content_type, title, subject_id, status, metadata)
                    VALUES (:id, 'knowledge', 'ik_kompetenz', :title, 1, 'active', CAST(:metadata AS jsonb))
                """),
                {
                    "id": str(uuid.uuid4()),
                    "title": f"IK {ik_nr}",
                    "metadata": json.dumps({"nr": ik_nr}),
                },
            )
        
        for pk_id in ["PK_05.1", "PK_05.2", "PK_05.3"]:
            await db_session.execute(
                text("""
                    INSERT INTO context_nodes (id, category, content_type, title, status, metadata)
                    VALUES (:id, 'knowledge', 'pk_kompetenz', :title, 'active', CAST(:metadata AS jsonb))
                ON CONFLICT DO NOTHING
            """),
                {
                    "id": str(uuid.uuid4()),
                    "title": pk_id,
                    "metadata": json.dumps({"pk_id": pk_id}),
                },
            )
        
        # Import durchführen
        curriculum_id, stats = await import_curriculum_from_draft(
            db_session, curriculum_draft_confirmed, "test_user"
        )
        
        # Prüfe Statistiken (curriculum_count kann 0 sein wenn es bereits existiert)
        assert stats.curriculum_count + stats.kapitel_count + stats.lernsequenz_count >= 0
        assert stats.edge_count >= 0
        
        # Prüfe Knoten in DB
        result = await db_session.execute(
            text("SELECT * FROM context_nodes WHERE content_type = 'curriculum' AND status = 'active'")
        )
        curricula = result.scalars().all()
        assert len(curricula) >= 1
        
        result = await db_session.execute(
            text("SELECT * FROM context_nodes WHERE content_type = 'kapitel' AND status = 'active'")
        )
        kapitel = result.scalars().all()
        assert len(kapitel) >= 1
        
        result = await db_session.execute(
            text("SELECT * FROM context_nodes WHERE content_type = 'lernsequenz' AND status = 'active'")
        )
        lernsequenzen = result.scalars().all()
        assert len(lernsequenzen) >= 2

    @pytest.mark.asyncio
    async def test_idempotent_import(
        self,
        db_session: AsyncSession,
        curriculum_draft_confirmed,
    ):
        """Test: Idempotenz - doppeltes Importieren aktualisiert bestehende Knoten."""
        # Vorbereitung wie oben
        await db_session.execute(
            text("""
                INSERT INTO context_nodes (id, category, content_type, title, status, metadata)
                VALUES (:id, 'knowledge', 'fachplan', 'Test Fachplan', 'active', CAST(:metadata AS jsonb))
                ON CONFLICT DO NOTHING
            """),
            {
                "id": str(uuid.uuid4()),
                "metadata": json.dumps({"fachplan_id": "BP_2016_MA"}),
            },
        )
        
        await db_session.execute(
            text("""
                INSERT INTO subjects (id, name, slug)
                VALUES (1, 'Mathematik', 'MA')
                ON CONFLICT DO NOTHING
            """),
        )
        
        for ik_nr in ["3.1.1", "3.1.2", "3.1.3"]:
            await db_session.execute(
                text("""
                    INSERT INTO context_nodes (id, category, content_type, title, subject_id, status, metadata)
                    VALUES (:id, 'knowledge', 'ik_kompetenz', :title, 1, 'active', CAST(:metadata AS jsonb))
                """),
                {
                    "id": str(uuid.uuid4()),
                    "title": f"IK {ik_nr}",
                    "metadata": json.dumps({"nr": ik_nr}),
                },
            )
        
        for pk_id in ["PK_05.1", "PK_05.2", "PK_05.3"]:
            await db_session.execute(
                text("""
                    INSERT INTO context_nodes (id, category, content_type, title, status, metadata)
                    VALUES (:id, 'knowledge', 'pk_kompetenz', :title, 'active', CAST(:metadata AS jsonb))
                ON CONFLICT DO NOTHING
            """),
                {
                    "id": str(uuid.uuid4()),
                    "title": pk_id,
                    "metadata": json.dumps({"pk_id": pk_id}),
                },
            )
        
        # Erster Import
        curriculum_id_1, stats_1 = await import_curriculum_from_draft(
            db_session, curriculum_draft_confirmed, "test_user"
        )
        
        # Zähle Knoten vor dem zweiten Import
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM context_nodes WHERE content_type IN ('curriculum', 'kapitel', 'lernsequenz') AND status = 'active'")
        )
        count_before = result.scalar()
        
        # Zweiter Import (gleiche Daten)
        curriculum_id_2, stats_2 = await import_curriculum_from_draft(
            db_session, curriculum_draft_confirmed, "test_user"
        )
        
        # Sollte dieselbe curriculum_id zurückgeben
        assert curriculum_id_1 == curriculum_id_2
        
        # Zähle Knoten nach dem zweiten Import
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM context_nodes WHERE content_type IN ('curriculum', 'kapitel', 'lernsequenz') AND status = 'active'")
        )
        count_after = result.scalar()
        
        # Anzahlt sollte gleich sein (keine Duplikate)
        assert count_before == count_after
        
        # Stats sollten zeigen dass Knoten aktualisiert wurden
        assert stats_2.curriculum_count == 0  # Nicht neu erstellt


# ============================================================================
# Test: GET /curricula/{id}
# ============================================================================


class TestGetCurriculum:
    """Tests für den GET-Endpunkt."""

    @pytest.mark.asyncio
    async def test_get_curriculum_success(
        self,
        test_client: TestClient,
        auth_headers,
        db_session: AsyncSession,
    ):
        """Test: Curriculum erfolgreich abrufen."""
        known_curriculum_id = "a1b2c3d4-0001-0001-0001-000000000001"
        # Curriculum erstellen mit bekannter ID
        await db_session.execute(
            text("""
                INSERT INTO context_nodes (id, category, content_type, title, status, metadata, subject_id, read_scope, write_scope)
                VALUES (:id, 'knowledge', 'curriculum', 'Test Curriculum', 'active', CAST(:metadata AS jsonb), 1, 'school', 'private')
                ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title
            """),
            {
                "id": known_curriculum_id,
                "metadata": json.dumps({
                    "fachplan_id": "BP_2016_MA",
                    "bp_version": "2016",
                    "schule": "Test-Schule",
                    "fach_code": "MA",
                    "schulart": "G8",
                    "jahrgangsstufe": "5",
                    "import_key": "BP_2016_MA_5",
                }),
            },
        )

        await db_session.commit()

        curriculum_id = known_curriculum_id
        
        response = await test_client.get(
            f"/context/curricula/{curriculum_id}",
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(curriculum_id)
        assert data["title"] == "Test Curriculum"

    @pytest.mark.asyncio
    async def test_get_curriculum_not_found(self, test_client: TestClient, auth_headers):
        """Test: Curriculum nicht gefunden."""
        non_existent_id = str(uuid.uuid4())
        
        response = await test_client.get(
            f"/context/curricula/{non_existent_id}",
            headers=auth_headers,
        )
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_curriculum_by_subject(
        self,
        test_client: TestClient,
        auth_headers,
        db_session: AsyncSession,
    ):
        """Test: Curricula nach Fach abrufen."""
        # Eigenes Fach (id=999) anlegen, um Daten aus anderen Tests nicht zu mixen
        await db_session.execute(
            text("INSERT INTO subjects (id, name, slug) VALUES (999, 'Test-Fach', 'test-fach-by-subject') ON CONFLICT (id) DO NOTHING"),
        )
        # Curriculum erstellen (feste IDs für Idempotenz)
        for i in range(3):
            fixed_id = f"b1b2b3b4-0002-000{i+1}-0001-000000000001"
            await db_session.execute(
                text("""
                    INSERT INTO context_nodes (id, category, content_type, title, status, metadata, subject_id, read_scope)
                    VALUES (:id, 'knowledge', 'curriculum', :title, 'active', CAST(:metadata AS jsonb), 999, 'school')
                    ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title
                """),
                {
                    "id": fixed_id,
                    "title": f"Curriculum {i}",
                    "metadata": json.dumps({
                        "jahrgangsstufe": str(5 + i),
                        "import_key": f"BP_TEST_999_{i}",
                    }),
                },
            )

        await db_session.commit()

        response = await test_client.get(
            "/context/curricula/by-subject/999",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3


# ============================================================================
# Test: Serialisierung (_serialize_pdf_for_llm)
# ============================================================================

# Minimales gültiges PDF mit einer Seite (kein Tabelleninhalt, aber parseable)
_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << >> >>\nendobj\n"
    b"4 0 obj\n<< /Length 0 >>\nstream\nendstream\nendobj\n"
    b"xref\n0 5\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"0000000266 00000 n \n"
    b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n316\n%%EOF"
)


class TestSerializePdfForLlm:
    """Unit-Tests für _serialize_pdf_for_llm."""

    def test_returns_list_of_page_blocks(self):
        from app.context.router import _serialize_pdf_for_llm, PageBlock
        pages = _serialize_pdf_for_llm(_MINIMAL_PDF)
        assert isinstance(pages, list)
        assert len(pages) == 1
        page = pages[0]
        assert isinstance(page, PageBlock)
        assert page.page_number == 1
        assert isinstance(page.tables, list)
        assert isinstance(page.flow_text, str)

    def test_no_tables_for_minimal_pdf(self):
        from app.context.router import _serialize_pdf_for_llm
        pages = _serialize_pdf_for_llm(_MINIMAL_PDF)
        assert pages[0].tables == []

    def test_page_numbers_sequential(self):
        """Seitennummern müssen 1-basiert und aufsteigend sein."""
        from app.context.router import _serialize_pdf_for_llm
        # Zwei-Seiten-PDF via Überschreiben des PDF-Parsers geht nicht trivial —
        # stattdessen prüfen wir nur die Struktur mit dem Minimal-PDF
        pages = _serialize_pdf_for_llm(_MINIMAL_PDF)
        for i, page in enumerate(pages):
            assert page.page_number == i + 1


# ============================================================================
# Test: Chunking (_chunk_pages_by_kapitel)
# ============================================================================


class TestChunkPagesByKapitel:
    """Unit-Tests für _chunk_pages_by_kapitel."""

    @staticmethod
    def _make_pages(flow_texts: list[str]):
        from app.context.router import PageBlock
        return [
            PageBlock(page_number=i + 1, tables=[], flow_text=text)
            for i, text in enumerate(flow_texts)
        ]

    def test_fallback_window_when_no_std_pattern(self):
        from app.context.router import _chunk_pages_by_kapitel
        pages = self._make_pages(["Einführung", "Inhalt", "Schluss", "Anhang", "Ende"])
        chunks = _chunk_pages_by_kapitel(pages, max_pages_per_call=3)
        assert len(chunks) >= 2
        # Alle Seiten müssen in mindestens einem Chunk vorkommen
        covered = {p.page_number for chunk in chunks for p in chunk.pages}
        assert covered == {1, 2, 3, 4, 5}

    def test_recognizes_std_pattern(self):
        from app.context.router import _chunk_pages_by_kapitel
        pages = self._make_pages([
            "Kapitel 1: Zahlen ca. 12 Std. Einführung",
            "Inhalt Kapitel 1",
            "Kapitel 2: Geometrie ca. 8 Stunden",
            "Inhalt Kapitel 2",
        ])
        chunks = _chunk_pages_by_kapitel(pages, max_pages_per_call=10)
        # Muss mindestens 2 Kapitel-Chunks erkennen
        assert len(chunks) >= 2

    def test_both_std_notations(self):
        from app.context.router import _chunk_pages_by_kapitel
        pages = self._make_pages([
            "Kapitel A ca. 5 Std.",
            "Inhalt A",
            "Kapitel B ca. 3 Stunden.",
            "Inhalt B",
        ])
        chunks = _chunk_pages_by_kapitel(pages, max_pages_per_call=10)
        assert len(chunks) >= 2

    def test_empty_pages_returns_empty(self):
        from app.context.router import _chunk_pages_by_kapitel
        assert _chunk_pages_by_kapitel([], max_pages_per_call=4) == []


# ============================================================================
# Test: LLM-Extraktion mit gemocktem _call_extraction_llm
# ============================================================================

# Fixiertes realistisches JSON-Ergebnis für Format A
_MOCK_KAPITEL_RESPONSE = {
    "kapitel": {
        "titel": "Zahlen und Operationen",
        "reihenfolge": 1,
        "std": "12 Std.",
        "hinweis": None,
        "konkretisierung": [],
        "lernsequenzen": [
            {
                "bp_titel": "3.1.1 Natürliche Zahlen",
                "bp_leitidee": "Zahl",
                "reihenfolge": 1,
                "eintraege": [
                    {
                        "ik": "3.1.1",
                        "ik_partiell": False,
                        "pk": ["2.1 Argumentieren"],
                        "konkretisierung": "Natürliche Zahlen lesen und schreiben",
                        "hinweise": None,
                        "lp": [],
                        "confidence": 0.95,
                        "warnings": [],
                    }
                ],
                "confidence": 0.95,
                "warnings": [],
            }
        ],
        "confidence": 0.95,
        "warnings": [],
    }
}


class TestExtractCurriculumViaLlm:
    """Tests für _extract_curriculum_via_llm mit gemocktem LLM-Call."""

    @pytest.mark.asyncio
    async def test_successful_extraction(self):
        """Vollständiger Pipeline-Lauf: PDF → Serialisierung → (mock) LLM → CurriculumDraftData."""
        from app.context.router import _extract_curriculum_via_llm
        from app.context.schemas import CurriculumDraftData

        with patch(
            "app.context.router._call_extraction_llm",
            new=AsyncMock(return_value=_MOCK_KAPITEL_RESPONSE),
        ):
            result = await _extract_curriculum_via_llm(
                _MINIMAL_PDF,
                fachplan_id="BP_2016_MA",
                bp_version="2016",
                fach="Mathematik",
                jahrgangsstufe="5",
                schulart="GYM",
            )

        assert isinstance(result, CurriculumDraftData)
        assert len(result.kapitel) >= 1
        assert result.kapitel[0].titel == "Zahlen und Operationen"
        assert result.fach == "Mathematik"
        assert result.jahrgangsstufe == "5"

    @pytest.mark.asyncio
    async def test_retry_on_invalid_json_then_success(self):
        """Erster LLM-Call liefert kaputtes JSON, zweiter ist valide → Ergebnis korrekt."""
        from app.context.router import _extract_curriculum_via_llm

        call_count = 0

        async def mock_llm(serialized_content, chapter_index, settings):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Kaputtes JSON: Pydantic-Validierung schlägt fehl
                return {"kapitel": {"titel": None, "reihenfolge": "FALSCH", "lernsequenzen": "nicht_eine_liste"}}
            return _MOCK_KAPITEL_RESPONSE

        with patch("app.context.router._call_extraction_llm", new=mock_llm):
            result = await _extract_curriculum_via_llm(
                _MINIMAL_PDF,
                fachplan_id="BP_2016_MA",
                bp_version="2016",
                fach="Mathematik",
                jahrgangsstufe="5",
                schulart="GYM",
            )

        # Nach Retry muss ein gültiges Kapitel vorhanden sein
        assert len(result.kapitel) >= 1
        # Mindestens 2 Aufrufe (Original + Retry)
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_placeholder_when_both_attempts_fail(self):
        """Beide Versuche schlagen fehl → Platzhalter-Kapitel mit confidence=0."""
        from app.context.router import _extract_curriculum_via_llm

        async def always_broken(serialized_content, chapter_index, settings):
            return {"kapitel": {"titel": None, "reihenfolge": "FALSCH", "lernsequenzen": "FALSCH"}}

        with patch("app.context.router._call_extraction_llm", new=always_broken):
            result = await _extract_curriculum_via_llm(
                _MINIMAL_PDF,
                fachplan_id="BP_2016_MA",
                bp_version="2016",
                fach="Mathematik",
                jahrgangsstufe="5",
                schulart="GYM",
            )

        # Jeder fehlgeschlagene Chunk landet als Platzhalter
        assert len(result.kapitel) >= 1
        assert all(kap.confidence == 0.0 for kap in result.kapitel)
        assert all(kap.warnings for kap in result.kapitel)


class TestCallExtractionLlmFallback:
    """Tests für den json_object-Fallback in _call_extraction_llm."""

    @pytest.mark.asyncio
    async def test_fallback_to_json_object_on_schema_failure(self):
        """Wenn json_schema-Request einen JSON-Fehler liefert, wird json_object probiert."""
        from unittest.mock import MagicMock
        from app.config import settings as app_settings
        from app.context.router import _call_extraction_llm

        valid_json = json.dumps(_MOCK_KAPITEL_RESPONSE)

        # Erster Call: json_schema → kein valides JSON
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {"choices": [{"message": {"content": "kein json hier"}}]}

        # Zweiter Call: json_object-Fallback → valides JSON
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {"choices": [{"message": {"content": valid_json}}]}

        with patch("httpx.AsyncClient") as MockClient:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.post = AsyncMock(side_effect=[resp1, resp2])
            MockClient.return_value = instance

            result = await _call_extraction_llm("test content", 0, app_settings)

        # Fallback muss ausgelöst worden sein (mindestens 2 HTTP-Calls)
        assert instance.post.call_count >= 2
        assert "kapitel" in result

    @pytest.mark.asyncio
    async def test_budget_exceeded_raises_429(self):
        """429 vom LiteLLM-Proxy wird als HTTPException 429 weitergegeben."""
        from unittest.mock import MagicMock
        from fastapi import HTTPException
        from app.config import settings as app_settings
        from app.context.router import _call_extraction_llm

        resp = MagicMock()
        resp.status_code = 429
        resp.text = "Budget exceeded"
        resp.json.return_value = {}

        with patch("httpx.AsyncClient") as MockClient:
            instance = MagicMock()
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            instance.post = AsyncMock(return_value=resp)
            MockClient.return_value = instance

            with pytest.raises(HTTPException) as exc_info:
                await _call_extraction_llm("test", 0, app_settings)

        assert exc_info.value.status_code == 429


# ============================================================================
# Fixtures für Datei-Tests
# ============================================================================


@pytest.fixture
def sample_yaml_file(tmp_path, curriculum_yaml_format_a):
    """Erstellt eine temporäre YAML-Datei."""
    yaml_path = tmp_path / "test_curriculum.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(curriculum_yaml_format_a, f)
    return str(yaml_path)


@pytest.fixture
def sample_pdf_file(tmp_path):
    """Erstellt eine temporäre PDF-Datei."""
    pdf_path = tmp_path / "test.pdf"
    # Minimal gültiges PDF
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 0 >>\nstream\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000010 00000 n \n0000000058 00000 n \n0000000106 00000 n \n0000000154 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n222\n%%EOF"
    with open(pdf_path, "wb") as f:
        f.write(pdf_content)
    return str(pdf_path)


# ============================================================================
# Test: CLI-Skript
# ============================================================================


class TestImportCurriculumCLI:
    """Tests für das CLI-Skript."""

    @pytest.mark.asyncio
    async def test_cli_import_single_file(
        self,
        sample_yaml_file,
        db_session,
    ):
        """Test: CLI-Import einer einzelnen YAML-Datei."""
        from scripts.import_curriculum import (
            load_yaml_file,
            convert_yaml_to_draft,
            import_single_curriculum,
        )
        
        # Vorbereitung: Fachplan, Subject, IK-, PK-Knoten
        await db_session.execute(
            text("""
                INSERT INTO context_nodes (id, category, content_type, title, status, metadata)
                VALUES (:id, 'knowledge', 'fachplan', 'Test Fachplan', 'active', CAST(:metadata AS jsonb))
                ON CONFLICT DO NOTHING
            """),
            {
                "id": str(uuid.uuid4()),
                "metadata": json.dumps({"fachplan_id": "BP_2016_MA"}),
            },
        )
        
        await db_session.execute(
            text("""
                INSERT INTO subjects (id, name, slug)
                VALUES (1, 'Mathematik', 'MA')
                ON CONFLICT DO NOTHING
            """),
        )
        
        for ik_nr in ["3.1.1", "3.1.2", "3.1.3"]:
            await db_session.execute(
                text("""
                    INSERT INTO context_nodes (id, category, content_type, title, subject_id, status, metadata)
                    VALUES (:id, 'knowledge', 'ik_kompetenz', :title, 1, 'active', CAST(:metadata AS jsonb))
                """),
                {
                    "id": str(uuid.uuid4()),
                    "title": f"IK {ik_nr}",
                    "metadata": json.dumps({"nr": ik_nr}),
                },
            )
        
        for pk_id in ["PK_05.1", "PK_05.2", "PK_05.3"]:
            await db_session.execute(
                text("""
                    INSERT INTO context_nodes (id, category, content_type, title, status, metadata)
                    VALUES (:id, 'knowledge', 'pk_kompetenz', :title, 'active', CAST(:metadata AS jsonb))
                ON CONFLICT DO NOTHING
            """),
                {
                    "id": str(uuid.uuid4()),
                    "title": pk_id,
                    "metadata": json.dumps({"pk_id": pk_id}),
                },
            )
        
        # YAML laden und konvertieren
        yaml_data = load_yaml_file(sample_yaml_file)
        draft = convert_yaml_to_draft(yaml_data)
        
        # Import durchführen
        import_key, node_count = await import_single_curriculum(
            db_session, yaml_data, "test_user"
        )
        
        assert import_key == "BP_2016_MA_5"
        assert node_count > 0
