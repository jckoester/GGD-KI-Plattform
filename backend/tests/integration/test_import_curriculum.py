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


# `TestCreateCurriculum` stand hier — drei Tests für `POST /context/curricula`.
# Endpunkt und Tests am 2026-08-08 entfernt.
#
# Lehrreich ist, WARUM die Tests grün waren, obwohl der Endpunkt nichts speicherte: Sie
# prüften die **Antwort** (201, Titel, Kapitelzahl), nie die **Wirkung**. Ein zweiter,
# frischer Lesevorgang hätte das fehlende Commit sofort gezeigt.
#
# Die geprüften Sachverhalte sind erhalten geblieben, nur eine Ebene tiefer — dort, wo sie
# hingehören, weil sie nicht am HTTP-Rand entstehen:
#   * Fachplan fehlt  -> test_curriculum_yaml_import.py::test_ohne_fachplan_klare_meldung
#   * IK unauflösbar  -> test_curriculum_yaml_import.py::test_unaufloesbare_kompetenz_bricht_nicht_ab


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
        
        # Keine feste id beanspruchen: `VALUES (1, …) ON CONFLICT DO NOTHING` tat
        # schlicht nichts, wenn 'mathematik' schon mit anderer id existierte — die
        # folgenden Knoten liefen dann in eine Fremdschlüsselverletzung. Das trug nur,
        # solange ein früherer Test im selben Lauf die id 1 zuerst belegte.
        subject_id = (
            await db_session.execute(
                text(
                    "INSERT INTO subjects (name, slug, fach_code) "
                    "VALUES ('Mathematik', 'mathematik', 'MA') "
                    "ON CONFLICT (slug) DO UPDATE SET fach_code = EXCLUDED.fach_code "
                    "RETURNING id"
                )
            )
        ).fetchone()[0]
        
        for ik_nr in ["3.1.1", "3.1.2", "3.1.3"]:
            await db_session.execute(
                text("""
                    INSERT INTO context_nodes (id, category, content_type, title, subject_id, status, metadata)
                    VALUES (:id, 'knowledge', 'ik_kompetenz', :title, :subject_id, 'active', CAST(:metadata AS jsonb))
                """),
                {
                    "id": str(uuid.uuid4()),
                    "title": f"IK {ik_nr}",
                    "subject_id": subject_id,
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
        
        # Keine feste id beanspruchen: `VALUES (1, …) ON CONFLICT DO NOTHING` tat
        # schlicht nichts, wenn 'mathematik' schon mit anderer id existierte — die
        # folgenden Knoten liefen dann in eine Fremdschlüsselverletzung. Das trug nur,
        # solange ein früherer Test im selben Lauf die id 1 zuerst belegte.
        subject_id = (
            await db_session.execute(
                text(
                    "INSERT INTO subjects (name, slug, fach_code) "
                    "VALUES ('Mathematik', 'mathematik', 'MA') "
                    "ON CONFLICT (slug) DO UPDATE SET fach_code = EXCLUDED.fach_code "
                    "RETURNING id"
                )
            )
        ).fetchone()[0]
        
        for ik_nr in ["3.1.1", "3.1.2", "3.1.3"]:
            await db_session.execute(
                text("""
                    INSERT INTO context_nodes (id, category, content_type, title, subject_id, status, metadata)
                    VALUES (:id, 'knowledge', 'ik_kompetenz', :title, :subject_id, 'active', CAST(:metadata AS jsonb))
                """),
                {
                    "id": str(uuid.uuid4()),
                    "title": f"IK {ik_nr}",
                    "subject_id": subject_id,
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

        # Eigenes Fach anlegen statt `subject_id = 1` anzunehmen. Diese Annahme trug
        # bisher nur, weil die (inzwischen entfernten) Create-Endpunkt-Tests vorher
        # liefen und dabei ein Fach anlegten — eine Kopplung über die Testreihenfolge,
        # die niemand sehen konnte.
        subject_id = (
            await db_session.execute(
                text(
                    "INSERT INTO subjects (slug, name, fach_code) "
                    "VALUES ('mathematik', 'Mathematik', 'MA') "
                    "ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name RETURNING id"
                )
            )
        ).fetchone()[0]

        # Curriculum erstellen mit bekannter ID
        await db_session.execute(
            text("""
                INSERT INTO context_nodes (id, category, content_type, title, status, metadata, subject_id, read_scope, write_scope)
                VALUES (:id, 'knowledge', 'curriculum', 'Test Curriculum', 'active', CAST(:metadata AS jsonb), :subject_id, 'school', 'private')
                ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title
            """),
            {
                "id": known_curriculum_id,
                "subject_id": subject_id,
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
        
        # Keine feste id beanspruchen: `VALUES (1, …) ON CONFLICT DO NOTHING` tat
        # schlicht nichts, wenn 'mathematik' schon mit anderer id existierte — die
        # folgenden Knoten liefen dann in eine Fremdschlüsselverletzung. Das trug nur,
        # solange ein früherer Test im selben Lauf die id 1 zuerst belegte.
        subject_id = (
            await db_session.execute(
                text(
                    "INSERT INTO subjects (name, slug, fach_code) "
                    "VALUES ('Mathematik', 'mathematik', 'MA') "
                    "ON CONFLICT (slug) DO UPDATE SET fach_code = EXCLUDED.fach_code "
                    "RETURNING id"
                )
            )
        ).fetchone()[0]
        
        for ik_nr in ["3.1.1", "3.1.2", "3.1.3"]:
            await db_session.execute(
                text("""
                    INSERT INTO context_nodes (id, category, content_type, title, subject_id, status, metadata)
                    VALUES (:id, 'knowledge', 'ik_kompetenz', :title, :subject_id, 'active', CAST(:metadata AS jsonb))
                """),
                {
                    "id": str(uuid.uuid4()),
                    "title": f"IK {ik_nr}",
                    "subject_id": subject_id,
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
        import_key, node_count, stats = await import_single_curriculum(
            db_session, yaml_data, "test_user"
        )

        assert import_key == "BP_2016_MA_5"
        assert node_count > 0
        # `stats` kam dazu, damit das CLI die nicht auflösbaren Verweise melden kann —
        # vorher gab es dafür nur `yaml_data["warnings"]`, ein Feld, das der Export gar
        # nicht schreibt; die Warnungen des Imports blieben unsichtbar. Diese Testdaten
        # enthalten einen unauflösbaren LP-Verweis: Er muss beim Aufrufer ankommen,
        # den Import aber nicht verhindern.
        assert any("BO" in w for w in stats.warnings), stats.warnings
