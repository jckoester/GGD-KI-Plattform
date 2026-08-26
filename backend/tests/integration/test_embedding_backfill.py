"""Integrationstests für embedding_backfill_service (KS-Phase-7 Teil B)."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.crons.embedding_backfill_service import backfill_embeddings
from app.db.models import ContextNode
from app.config import settings

# Vektorbreite aus der Konfiguration statt als Literal — die Testdaten müssen zur
# tatsächlich migrierten Spalte passen (EMBEDDING_DIMENSIONS).
DIM = settings.embedding_dimensions


# ── Session-Fixture (committed, kein Rollback-Isolation) ────────────────────

@pytest_asyncio.fixture
async def session_factory(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def cleanup_nodes(async_engine):
    """Garantiert isolierten Knoten-Zustand: vor UND nach jedem Test leeren.

    Vorab-Bereinigung ist nötig, weil andere Integrationstests (z. B. Bildungsplan-
    Import) Knoten committen, die sonst in den `found`-Zähler dieses Tests einfließen.
    """
    factory = async_sessionmaker(async_engine, class_=AsyncSession)
    async with factory() as db:
        await db.execute(sa.delete(ContextNode))
        await db.commit()
    yield
    async with factory() as db:
        await db.execute(sa.delete(ContextNode))
        await db.commit()


@pytest_asyncio.fixture
async def seed_nodes(session_factory):
    """Legt zwei Knoten an: einen embeddable (ik_kompetenz), einen nicht (fachplan)."""
    async with session_factory() as db:
        ik = ContextNode(
            id=uuid.uuid4(),
            title="Test-IK",
            content="Die SuS können etwas.",
            category="knowledge",
            content_type="ik_kompetenz",
            status="active",
            read_scope="global",
            write_scope="global",
            metadata_={},
        )
        fp = ContextNode(
            id=uuid.uuid4(),
            title="Test-Fachplan",
            content="Dieser Knoten bekommt kein Embedding.",
            category="knowledge",
            content_type="fachplan",
            status="active",
            read_scope="global",
            write_scope="global",
            metadata_={},
        )
        db.add(ik)
        db.add(fp)
        await db.commit()
        return {"ik_id": ik.id, "fp_id": fp.id}


# ── Tests ────────────────────────────────────────────────────────────────────

class TestBackfillEmbeddings:
    @pytest.mark.asyncio
    async def test_sets_embedding_for_whitelist_node(self, session_factory, seed_nodes):
        fake = [0.1] * DIM
        with patch(
            "app.crons.embedding_backfill_service.generate_embedding",
            new_callable=AsyncMock,
            return_value=fake,
        ):
            async with session_factory() as db:
                stats = await backfill_embeddings(db, batch_size=10)

        assert stats.found == 1  # nur ik_kompetenz
        assert stats.ok == 1
        assert stats.errors == 0

        async with session_factory() as db:
            node = await db.get(ContextNode, seed_nodes["ik_id"])
            assert node.embedding is not None
            assert len(node.embedding) == DIM

    @pytest.mark.asyncio
    async def test_does_not_embed_non_whitelist_node(self, session_factory, seed_nodes):
        fake = [0.2] * DIM
        with patch(
            "app.crons.embedding_backfill_service.generate_embedding",
            new_callable=AsyncMock,
            return_value=fake,
        ):
            async with session_factory() as db:
                await backfill_embeddings(db)

        async with session_factory() as db:
            node = await db.get(ContextNode, seed_nodes["fp_id"])
            assert node.embedding is None

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write(self, session_factory, seed_nodes):
        fake = [0.3] * DIM
        with patch(
            "app.crons.embedding_backfill_service.generate_embedding",
            new_callable=AsyncMock,
            return_value=fake,
        ):
            async with session_factory() as db:
                stats = await backfill_embeddings(db, dry_run=True)

        assert stats.found == 1
        assert stats.ok == 1  # dry_run zählt trotzdem
        async with session_factory() as db:
            node = await db.get(ContextNode, seed_nodes["ik_id"])
            assert node.embedding is None  # nicht geschrieben

    @pytest.mark.asyncio
    async def test_empty_content_node_is_skipped_not_errored(self, session_factory):
        # Whitelist-Knoten ohne einbettbaren Text → überspringen statt 400/Fehler.
        async with session_factory() as db:
            node = ContextNode(
                id=uuid.uuid4(),
                title="Leerer Knoten",
                content="",
                category="knowledge",
                content_type="ik_kompetenz",
                status="active",
                read_scope="global",
                write_scope="global",
                metadata_={},
            )
            db.add(node)
            await db.commit()
            node_id = node.id

        mock = AsyncMock(return_value=[0.5] * DIM)
        with patch("app.crons.embedding_backfill_service.generate_embedding", mock):
            async with session_factory() as db:
                stats = await backfill_embeddings(db)

        assert stats.found == 1
        assert stats.skipped == 1
        assert stats.ok == 0
        assert stats.errors == 0
        mock.assert_not_awaited()  # leerer Input → kein Embedding-Call
        async with session_factory() as db:
            node = await db.get(ContextNode, node_id)
            assert node.embedding is None

    @pytest.mark.asyncio
    async def test_error_sets_embedding_error_metadata(self, session_factory, seed_nodes):
        with patch(
            "app.crons.embedding_backfill_service.generate_embedding",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LiteLLM nicht erreichbar"),
        ):
            async with session_factory() as db:
                stats = await backfill_embeddings(db)

        assert stats.errors == 1
        assert stats.ok == 0

        async with session_factory() as db:
            node = await db.get(ContextNode, seed_nodes["ik_id"])
            assert node.embedding is None
            assert "embedding_error" in (node.metadata_ or {})

    @pytest.mark.asyncio
    async def test_already_embedded_nodes_skipped(self, session_factory, seed_nodes):
        # Embedding vorab setzen
        async with session_factory() as db:
            await db.execute(
                sa.update(ContextNode)
                .where(ContextNode.id == seed_nodes["ik_id"])
                .values(embedding=[0.9] * DIM)
            )
            await db.commit()

        mock = AsyncMock(return_value=[0.5] * DIM)
        with patch("app.crons.embedding_backfill_service.generate_embedding", mock):
            async with session_factory() as db:
                stats = await backfill_embeddings(db)

        assert stats.found == 0  # kein Knoten ohne Embedding
        mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_limit_respected(self, session_factory, async_engine):
        """Legt 3 embeddable Knoten an; limit=2 → nur 2 werden verarbeitet."""
        async with session_factory() as db:
            for i in range(3):
                db.add(ContextNode(
                    id=uuid.uuid4(),
                    title=f"IK {i}",
                    content=f"Kompetenz {i}",
                    category="knowledge",
                    content_type="ik_kompetenz",
                    status="active",
                    read_scope="global",
                    write_scope="global",
                    metadata_={},
                ))
            await db.commit()

        fake = [0.1] * DIM
        with patch(
            "app.crons.embedding_backfill_service.generate_embedding",
            new_callable=AsyncMock,
            return_value=fake,
        ):
            async with session_factory() as db:
                stats = await backfill_embeddings(db, limit=2)

        assert stats.found == 2
        assert stats.ok == 2


class TestAbbruchBeiFehlerserie:
    """Ein kaputter Modellzugang darf den Lauf nicht stundenlang leerlaufen lassen.

    Realfall: Ein ungueltiger Anbieter-Schluessel beantwortet LiteLLM mit 401; LiteLLM
    nimmt die Deployment daraufhin in den Cooldown, und alle weiteren Anfragen bekommen
    `429 No deployments available`. Jeder Knoten kostet dann sein volles
    Wiederholungsbudget — bei tausenden Knoten Stunden fuer ein Ergebnis, das nach dem
    zehnten feststand.
    """

    @pytest_asyncio.fixture
    async def viele_knoten(self, session_factory):
        """40 einbettbare Knoten — mehr als die Abbruchschwelle."""
        async with session_factory() as db:
            for i in range(40):
                db.add(ContextNode(
                    id=uuid.uuid4(), title=f"IK {i}", content=f"Inhalt {i}",
                    category="knowledge", content_type="ik_kompetenz",
                    status="active", read_scope="global", write_scope="global",
                    metadata_={},
                ))
            await db.commit()

    @pytest.mark.asyncio
    async def test_bricht_nach_fehlerserie_ab(self, session_factory, viele_knoten):
        from app.crons.embedding_backfill_service import _MAX_FEHLER_IN_FOLGE

        with patch(
            "app.crons.embedding_backfill_service.generate_embedding",
            new_callable=AsyncMock,
            side_effect=RuntimeError("429 No deployments available"),
        ) as gen:
            async with session_factory() as db:
                stats = await backfill_embeddings(db, batch_size=100)

        assert stats.abgebrochen is True
        # Genau bis zur Schwelle versucht, danach kein Aufruf mehr.
        assert gen.await_count == _MAX_FEHLER_IN_FOLGE
        assert stats.errors == _MAX_FEHLER_IN_FOLGE
        assert stats.found == 40

    @pytest.mark.asyncio
    async def test_nicht_versuchte_knoten_bleiben_unberuehrt(
        self, session_factory, viele_knoten
    ):
        """Sie behalten `embedding IS NULL` und werden im naechsten Lauf erneut geholt."""
        with patch(
            "app.crons.embedding_backfill_service.generate_embedding",
            new_callable=AsyncMock,
            side_effect=RuntimeError("429 No deployments available"),
        ):
            async with session_factory() as db:
                await backfill_embeddings(db, batch_size=100)

        async with session_factory() as db:
            offen = (await db.execute(
                sa.select(sa.func.count()).select_from(ContextNode)
                .where(ContextNode.embedding.is_(None))
            )).scalar()
            markiert = (await db.execute(
                sa.select(sa.func.count()).select_from(ContextNode)
                .where(ContextNode.metadata_.has_key("embedding_error"))
            )).scalar()
        assert offen == 40           # keiner hat einen Vektor bekommen
        assert markiert == 10        # nur die tatsaechlich versuchten sind markiert

    @pytest.mark.asyncio
    async def test_vereinzelte_fehler_brechen_nicht_ab(self, session_factory, viele_knoten):
        """Nur eine *ununterbrochene* Serie zaehlt — ein Erfolg setzt sie zurueck."""
        fake = [0.1] * DIM
        aufrufe = {"n": 0}

        async def _mal_so_mal_so(_text):
            aufrufe["n"] += 1
            if aufrufe["n"] % 2 == 0:
                raise RuntimeError("400 Bad Request")
            return fake

        with patch(
            "app.crons.embedding_backfill_service.generate_embedding",
            new=_mal_so_mal_so,
        ):
            async with session_factory() as db:
                stats = await backfill_embeddings(db, batch_size=100)

        assert stats.abgebrochen is False
        assert stats.ok == 20
        assert stats.errors == 20
