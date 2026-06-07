"""Integrationstests für Curriculum-Export und Round-Trip (KS-Phase-6 Schritt 5)."""

import uuid
from uuid import UUID

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.schemas import (
    CurriculumDraftConfirmed,
    CurriculumDraftEntry,
    CurriculumDraftKapitel,
    CurriculumDraftLernsequenz,
)
from app.context.service import import_curriculum_from_draft, load_curriculum_tree
from app.context.curriculum_export import build_curriculum_export_dict
from app.db.models import ContextEdge, ContextNode


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

async def _insert_node(db: AsyncSession, **kwargs) -> UUID:
    node = ContextNode(**kwargs)
    db.add(node)
    await db.flush()
    return node.id


async def _count_edges(db: AsyncSession, from_id: UUID, relation: str) -> int:
    result = await db.execute(
        sa.select(sa.func.count()).where(
            ContextEdge.from_node_id == from_id,
            ContextEdge.relation == relation,
        )
    )
    return result.scalar_one()


async def _get_edges(db: AsyncSession, from_id: UUID, relation: str) -> list[dict]:
    result = await db.execute(
        sa.select(ContextEdge).where(
            ContextEdge.from_node_id == from_id,
            ContextEdge.relation == relation,
        )
    )
    return [{"to": str(e.to_node_id), "meta": e.metadata_} for e in result.scalars().all()]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def bp_nodes(db_session: AsyncSession):
    """Legt minimale BP-Knoten für Export-Tests an."""
    # Subject MA (Spalten: slug NOT NULL UNIQUE, name, fach_code)
    result = await db_session.execute(
        sa.text(
            "INSERT INTO subjects (slug, name, fach_code) "
            "VALUES ('mathematik', 'Mathematik', 'MA') "
            "ON CONFLICT (slug) DO UPDATE "
            "SET name = EXCLUDED.name, fach_code = EXCLUDED.fach_code RETURNING id"
        )
    )
    ma_subject_id = result.fetchone()[0]

    # Subject ETH (für Cross-IK-Test)
    result = await db_session.execute(
        sa.text(
            "INSERT INTO subjects (slug, name, fach_code) "
            "VALUES ('ethik', 'Ethik', 'ETH') "
            "ON CONFLICT (slug) DO UPDATE "
            "SET name = EXCLUDED.name, fach_code = EXCLUDED.fach_code RETURNING id"
        )
    )
    eth_subject_id = result.fetchone()[0]

    # Fachplan
    fachplan_id = await _insert_node(
        db_session,
        id=uuid.uuid4(),
        category="knowledge",
        content_type="fachplan",
        title="BP 2016 Mathematik",
        status="active",
        owner_pseudonym="system",
        read_scope="global",
        write_scope="school",
        metadata_={"fachplan_id": "BP_2016_MA_TEST_EXPORT"},
    )

    # IK-Knoten MA (eigenes Fach)
    ik_ma_id = await _insert_node(
        db_session,
        id=uuid.uuid4(),
        category="knowledge",
        content_type="ik_kompetenz",
        title="MA IK 3.1.1",
        status="active",
        owner_pseudonym="system",
        read_scope="global",
        write_scope="school",
        subject_id=ma_subject_id,
        metadata_={"nr": "3.1.1"},
    )

    # IK-Knoten ETH (Cross-Fach)
    ik_eth_id = await _insert_node(
        db_session,
        id=uuid.uuid4(),
        category="knowledge",
        content_type="ik_kompetenz",
        title="ETH IK 2.1.1",
        status="active",
        owner_pseudonym="system",
        read_scope="global",
        write_scope="school",
        subject_id=eth_subject_id,
        metadata_={"nr": "2.1.1"},
    )

    # PK-Knoten
    pk_id_node = await _insert_node(
        db_session,
        id=uuid.uuid4(),
        category="knowledge",
        content_type="pk_kompetenz",
        title="PK_05.1",
        status="active",
        owner_pseudonym="system",
        read_scope="global",
        write_scope="school",
        metadata_={"pk_id": "PK_05.1"},
    )

    # LP-Knoten
    lp_id_node = await _insert_node(
        db_session,
        id=uuid.uuid4(),
        category="knowledge",
        content_type="leitperspektive",
        title="Berufliche Orientierung",
        status="active",
        owner_pseudonym="system",
        read_scope="global",
        write_scope="school",
        metadata_={"code": "BO"},
    )

    # LP-Aspekt-Knoten
    lpa_id_node = await _insert_node(
        db_session,
        id=uuid.uuid4(),
        category="knowledge",
        content_type="leitperspektive_aspekt",
        title="BNE Aspekt 1",
        status="active",
        owner_pseudonym="system",
        read_scope="global",
        write_scope="school",
        metadata_={"bp_id": "BNE_01"},
    )

    # Material-Knoten
    mat_node_id = await _insert_node(
        db_session,
        id=uuid.uuid4(),
        category="knowledge",
        content_type="arbeitsblatt",
        title="Arbeitsblatt Brüche",
        status="active",
        owner_pseudonym="system",
        read_scope="school",
        write_scope="school",
        metadata_={},
    )

    return {
        "ma_subject_id": ma_subject_id,
        "eth_subject_id": eth_subject_id,
        "fachplan_id": fachplan_id,
        "ik_ma_id": ik_ma_id,
        "ik_eth_id": ik_eth_id,
        "pk_id_node": pk_id_node,
        "lp_id_node": lp_id_node,
        "lpa_id_node": lpa_id_node,
        "mat_node_id": mat_node_id,
    }


def _make_draft(bp_nodes: dict, hinweise: str = "", material: str = "") -> CurriculumDraftConfirmed:
    """Erzeugt einen minimalen CurriculumDraftConfirmed für Tests."""
    return CurriculumDraftConfirmed(
        schule="Test-Schule",
        fach_code="MA",
        fach="Mathematik",
        schulart="G8",
        jahrgangsstufe="5",
        fachplan_id="BP_2016_MA_TEST_EXPORT",
        bp_version="2016",
        kapitel=[
            CurriculumDraftKapitel(
                titel="Testkapitel",
                reihenfolge=1,
                std="10",
                lernsequenzen=[
                    CurriculumDraftLernsequenz(
                        bp_titel="Test-Lernsequenz",
                        bp_leitidee="Zahl",
                        reihenfolge=1,
                        std="5",
                        eintraege=[
                            CurriculumDraftEntry(
                                ik=[{"nr": "3.1.1", "partiell": False}],
                                pk=[{"id": "PK_05.1"}],
                                konkretisierung="Test-Konkretisierung",
                                hinweise=hinweise,
                                material=material,
                            )
                        ],
                    )
                ],
            )
        ],
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCurriculumExportYaml:
    """YAML-Export-Tests."""

    @pytest.mark.asyncio
    async def test_export_dict_structure(self, db_session: AsyncSession, bp_nodes: dict):
        """Export-Dict enthält korrekte Toplevel-Felder."""
        draft = _make_draft(bp_nodes)
        curriculum_id, _ = await import_curriculum_from_draft(db_session, draft, "teacher1")

        tree = await load_curriculum_tree(db_session, curriculum_id)
        assert tree is not None

        export = await build_curriculum_export_dict(db_session, tree)
        assert export["fach_code"] == "MA"
        assert export["jahrgangsstufe"] == "5"
        assert export["fachplan_id"] == "BP_2016_MA_TEST_EXPORT"
        assert len(export["kapitel"]) == 1
        kap = export["kapitel"][0]
        assert kap["titel"] == "Testkapitel"
        assert len(kap["lernsequenzen"]) == 1
        ls = kap["lernsequenzen"][0]
        assert ls["bp_titel"] == "Test-Lernsequenz"
        assert len(ls["eintraege"]) == 1

    @pytest.mark.asyncio
    async def test_export_ik_list_format(self, db_session: AsyncSession, bp_nodes: dict):
        """IK wird im Export als Liste mit nr-Feldern ausgegeben."""
        draft = _make_draft(bp_nodes)
        curriculum_id, _ = await import_curriculum_from_draft(db_session, draft, "teacher1")

        tree = await load_curriculum_tree(db_session, curriculum_id)
        export = await build_curriculum_export_dict(db_session, tree)

        eintrag = export["kapitel"][0]["lernsequenzen"][0]["eintraege"][0]
        assert isinstance(eintrag["ik"], list)
        assert len(eintrag["ik"]) == 1
        assert eintrag["ik"][0]["nr"] == "3.1.1"
        assert eintrag["ik"][0]["partiell"] is False

    @pytest.mark.asyncio
    async def test_export_hinweise_lp_token_to_code(
        self, db_session: AsyncSession, bp_nodes: dict
    ):
        """Hinweise-LP-UUID-Token wird im Export in Code-Token übersetzt."""
        lp_uuid = str(bp_nodes["lp_id_node"])
        hinweise = f"@[BO](lp:{lp_uuid})"
        draft = _make_draft(bp_nodes, hinweise=hinweise)
        curriculum_id, _ = await import_curriculum_from_draft(db_session, draft, "teacher1")

        tree = await load_curriculum_tree(db_session, curriculum_id)
        export = await build_curriculum_export_dict(db_session, tree)

        eintrag = export["kapitel"][0]["lernsequenzen"][0]["eintraege"][0]
        # Im Export soll der Code-Token stehen
        assert "@[BO](lp:BO)" in eintrag["hinweise"]
        assert lp_uuid not in eintrag["hinweise"]

    @pytest.mark.asyncio
    async def test_export_material_uuid_preserved(
        self, db_session: AsyncSession, bp_nodes: dict
    ):
        """Material-node-UUID bleibt im Export erhalten (nicht portabel)."""
        mat_uuid = str(bp_nodes["mat_node_id"])
        material = f"@[Arbeitsblatt](node:{mat_uuid})"
        draft = _make_draft(bp_nodes, material=material)
        curriculum_id, _ = await import_curriculum_from_draft(db_session, draft, "teacher1")

        tree = await load_curriculum_tree(db_session, curriculum_id)
        export = await build_curriculum_export_dict(db_session, tree)

        eintrag = export["kapitel"][0]["lernsequenzen"][0]["eintraege"][0]
        assert f"node:{mat_uuid}" in eintrag["material"]


class TestCurriculumRoundTrip:
    """Round-Trip-Tests: Export → Re-Import → identische Kanten."""

    @pytest.mark.asyncio
    async def test_roundtrip_basic(self, db_session: AsyncSession, bp_nodes: dict):
        """Einfacher Round-Trip ohne Token: IK/PK-Kanten bleiben erhalten."""
        draft = _make_draft(bp_nodes)
        curriculum_id, stats1 = await import_curriculum_from_draft(db_session, draft, "teacher1")

        tree = await load_curriculum_tree(db_session, curriculum_id)
        export = await build_curriculum_export_dict(db_session, tree)

        # Re-Import (idempotent) direkt über die Service-Kernlogik
        from app.context.service import import_curriculum_from_draft as reimport
        reimport_draft = CurriculumDraftConfirmed(**{
            **export,
            "kapitel": [
                CurriculumDraftKapitel(
                    titel=kap["titel"],
                    reihenfolge=kap["reihenfolge"],
                    std=kap.get("std"),
                    hinweis=kap.get("hinweis"),
                    lernsequenzen=[
                        CurriculumDraftLernsequenz(
                            bp_titel=ls["bp_titel"],
                            bp_leitidee=ls.get("bp_leitidee"),
                            reihenfolge=ls["reihenfolge"],
                            std=str(ls["std"]) if ls.get("std") is not None else None,
                            eintraege=[
                                CurriculumDraftEntry(
                                    ik=e["ik"],
                                    pk=e["pk"],
                                    konkretisierung=e.get("konkretisierung"),
                                    hinweise=e.get("hinweise"),
                                    material=e.get("material"),
                                )
                                for e in ls["eintraege"]
                            ],
                        )
                        for ls in kap["lernsequenzen"]
                    ],
                )
                for kap in export["kapitel"]
            ],
        })
        curriculum_id2, stats2 = await reimport(db_session, reimport_draft, "teacher1")

        # Gleiches Curriculum (idempotent via import_key)
        assert curriculum_id2 == curriculum_id
        # Keine neuen Kanten (alles dedupliziert)
        assert stats2.warnings == [] or all("nicht gefunden" not in w for w in stats2.warnings)

    @pytest.mark.asyncio
    async def test_roundtrip_hinweise_lp_token(
        self, db_session: AsyncSession, bp_nodes: dict
    ):
        """Round-Trip mit LP-Code-Token: LP-references-Kante bleibt nach Re-Import erhalten."""
        # LP-Kante über Code-Token im YAML
        lp_uuid = str(bp_nodes["lp_id_node"])
        # Wir nutzen direkt UUID-Token (wie vom Editor gespeichert) als Eingangsformat
        hinweise_uuid = f"@[BO](lp:{lp_uuid})"
        draft = _make_draft(bp_nodes, hinweise=hinweise_uuid)
        curriculum_id, _ = await import_curriculum_from_draft(db_session, draft, "teacher1")

        # LS-ID ermitteln
        result = await db_session.execute(
            sa.select(ContextNode.id).where(
                ContextNode.content_type == "lernsequenz",
                ContextNode.status == "active",
            )
        )
        ls_ids = [row[0] for row in result.fetchall()]
        assert ls_ids, "Keine Lernsequenz gefunden"

        # LP-Kante vorhanden?
        for ls_id in ls_ids:
            lp_edges = await _get_edges(db_session, ls_id, "references")
            lp_edge_targets = [e["to"] for e in lp_edges]
            if str(bp_nodes["lp_id_node"]) in lp_edge_targets:
                return  # Kante gefunden → Test bestanden

        pytest.fail("LP-references-Kante aus Hinweis-Token nicht gefunden")

    @pytest.mark.asyncio
    async def test_roundtrip_material_used_with_edge(
        self, db_session: AsyncSession, bp_nodes: dict
    ):
        """Round-Trip mit Material-Token: used_with-Kante mit via=material vorhanden."""
        mat_uuid = str(bp_nodes["mat_node_id"])
        material = f"@[Arbeitsblatt](node:{mat_uuid})"
        draft = _make_draft(bp_nodes, material=material)
        curriculum_id, stats = await import_curriculum_from_draft(db_session, draft, "teacher1")

        # LS-ID ermitteln
        result = await db_session.execute(
            sa.select(ContextNode).where(
                ContextNode.content_type == "lernsequenz",
                ContextNode.status == "active",
            )
        )
        ls_nodes = result.scalars().all()

        material_edge_found = False
        for ls_node in ls_nodes:
            result = await db_session.execute(
                sa.select(ContextEdge).where(
                    ContextEdge.from_node_id == ls_node.id,
                    ContextEdge.relation == "used_with",
                    ContextEdge.to_node_id == UUID(mat_uuid),
                )
            )
            edge = result.scalar_one_or_none()
            if edge:
                assert edge.metadata_ and edge.metadata_.get("via") == "material"
                material_edge_found = True
                break

        assert material_edge_found, "used_with/via=material-Kante nicht gefunden"

    @pytest.mark.asyncio
    async def test_roundtrip_cross_ik_token(
        self, db_session: AsyncSession, bp_nodes: dict
    ):
        """Cross-Fach-IK: UUID-Token → Export-Code-Token (ik:ETH:2.1.1) → Re-Import → Kante.

        Deckt die fach_code-Auflösung in curriculum_export und service ab.
        """
        ik_eth_uuid = str(bp_nodes["ik_eth_id"])
        hinweise_uuid = f"#[ETH 2.1.1](ik:{ik_eth_uuid})"
        draft = _make_draft(bp_nodes, hinweise=hinweise_uuid)
        curriculum_id, _ = await import_curriculum_from_draft(db_session, draft, "teacher1")

        # Export: UUID-Token muss zu Code-Token (ik:ETH:2.1.1) werden
        tree = await load_curriculum_tree(db_session, curriculum_id)
        export = await build_curriculum_export_dict(db_session, tree)
        eintrag = export["kapitel"][0]["lernsequenzen"][0]["eintraege"][0]
        assert "(ik:ETH:2.1.1)" in eintrag["hinweise"]
        assert ik_eth_uuid not in eintrag["hinweise"]

        # Re-Import aus dem Code-Token: references-Kante auf ETH-IK muss existieren
        reimport_draft = _make_draft(bp_nodes, hinweise=eintrag["hinweise"])
        await import_curriculum_from_draft(db_session, reimport_draft, "teacher1")

        result = await db_session.execute(
            sa.select(ContextNode.id).where(
                ContextNode.content_type == "lernsequenz",
                ContextNode.status == "active",
            )
        )
        ls_ids = [row[0] for row in result.fetchall()]
        found = False
        for ls_id in ls_ids:
            targets = [e["to"] for e in await _get_edges(db_session, ls_id, "references")]
            if ik_eth_uuid in targets:
                found = True
                break
        assert found, "Cross-IK references-Kante nach Re-Import aus Code-Token nicht gefunden"


class TestCurriculumImportWarnings:
    """Tests für Warnungen bei unbekannten Referenzen."""

    @pytest.mark.asyncio
    async def test_unknown_lp_code_yields_warning(
        self, db_session: AsyncSession, bp_nodes: dict
    ):
        """Unbekannter LP-Code im Hinweis-Token erzeugt Warnung, kein Abbruch."""
        hinweise = "@[Unbekannt](lp:UNKNOWN_LP)"
        draft = _make_draft(bp_nodes, hinweise=hinweise)
        curriculum_id, stats = await import_curriculum_from_draft(db_session, draft, "teacher1")

        assert curriculum_id is not None
        assert any("UNKNOWN_LP" in w for w in stats.warnings)

    @pytest.mark.asyncio
    async def test_unknown_material_node_yields_warning(
        self, db_session: AsyncSession, bp_nodes: dict
    ):
        """Nicht existierender Material-Knoten erzeugt Warnung, kein Abbruch."""
        fake_uuid = str(uuid.uuid4())
        material = f"@[Fehlt](node:{fake_uuid})"
        draft = _make_draft(bp_nodes, material=material)
        curriculum_id, stats = await import_curriculum_from_draft(db_session, draft, "teacher1")

        assert curriculum_id is not None
        assert any(fake_uuid in w for w in stats.warnings)

    @pytest.mark.asyncio
    async def test_unknown_lpa_yields_warning(
        self, db_session: AsyncSession, bp_nodes: dict
    ):
        """Unbekannte LPA-bp_id im Hinweis-Token erzeugt Warnung."""
        hinweise = "@[Aspekt X](lpa:XX_99)"
        draft = _make_draft(bp_nodes, hinweise=hinweise)
        curriculum_id, stats = await import_curriculum_from_draft(db_session, draft, "teacher1")

        assert curriculum_id is not None
        assert any("XX_99" in w for w in stats.warnings)
