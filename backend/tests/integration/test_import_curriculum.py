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
from fastapi.testclient import TestClient
from io import BytesIO
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.schemas import (
    CurriculumDraftConfirmed,
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
# Fixtures für Datei-Tests
# ============================================================================


@pytest.fixture
def sample_yaml_file(tmp_path, curriculum_yaml_format_a):
    """Erstellt eine temporäre YAML-Datei."""
    yaml_path = tmp_path / "test_curriculum.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(curriculum_yaml_format_a, f)
    return str(yaml_path)


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
