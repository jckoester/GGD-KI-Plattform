"""Integrationstests für embedding_backfill_service (KS-Phase-7 Teil B)."""

import uuid

import httpx
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.context.embedding import EmbeddingStapel
from app.crons.embedding_backfill_service import backfill_embeddings
from app.db.models import ContextNode
from app.config import settings

# Vektorbreite aus der Konfiguration statt als Literal — die Testdaten müssen zur
# tatsächlich migrierten Spalte passen (EMBEDDING_DIMENSIONS).
DIM = settings.embedding_dimensions

# Ziel der Attrappen ist `generate_embeddings` (Plural): Der Backfill bettet im Stapel ein,
# eine Anfrage je Knoten wäre bei ~14.000 Knoten ein mehrstündiger Lauf.
STAPEL = "app.crons.embedding_backfill_service.generate_embeddings"


def _liefert(vektor: list[float]) -> AsyncMock:
    """Stapel-Attrappe: gibt je Eingabetext denselben Vektor zurück.

    Die Länge muss zur Eingabe passen — der Aufrufer ordnet Vektoren den Knoten paarweise
    zu, eine zu kurze Antwort ließe die überzähligen Knoten stillschweigend leer.
    AsyncMock, damit Tests auch prüfen können, dass gar nicht aufgerufen wurde.
    """
    async def _f(texte: list[str]) -> EmbeddingStapel:
        return EmbeddingStapel(vektoren=[list(vektor) for _ in texte], tokens=len(texte) * 10)
    return AsyncMock(side_effect=_f)


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
        with patch(STAPEL, new=_liefert(fake)):
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
        with patch(STAPEL, new=_liefert(fake)):
            async with session_factory() as db:
                await backfill_embeddings(db)

        async with session_factory() as db:
            node = await db.get(ContextNode, seed_nodes["fp_id"])
            assert node.embedding is None

    @pytest.mark.asyncio
    async def test_dry_run_does_not_write(self, session_factory, seed_nodes):
        fake = [0.3] * DIM
        with patch(STAPEL, new=_liefert(fake)):
            async with session_factory() as db:
                stats = await backfill_embeddings(db, dry_run=True)

        assert stats.found == 1
        assert stats.ok == 1  # dry_run zählt trotzdem
        async with session_factory() as db:
            node = await db.get(ContextNode, seed_nodes["ik_id"])
            assert node.embedding is None  # nicht geschrieben

    @pytest.mark.asyncio
    async def test_node_ohne_content_aber_mit_titel_wird_eingebettet(self, session_factory):
        """Der Titel allein genügt — früher fiel so ein Knoten aus der Suche heraus.

        Betraf im Bestand 125 Leitideen mit sprechendem Titel (`3.1.2.2 Malerei`) und
        leerem Inhalt.
        """
        async with session_factory() as db:
            node = ContextNode(
                id=uuid.uuid4(),
                title="3.1.2.2 Malerei",
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

        mock = _liefert([0.5] * DIM)
        with patch(STAPEL, new=mock):
            async with session_factory() as db:
                stats = await backfill_embeddings(db)

        assert stats.ok == 1
        assert stats.skipped == 0
        # Eingebettet wurde der Titel — sonst nichts.
        assert mock.await_args.args[0] == ["3.1.2.2 Malerei"]
        async with session_factory() as db:
            node = await db.get(ContextNode, node_id)
            assert node.embedding is not None

    @pytest.mark.asyncio
    async def test_empty_content_node_is_skipped_not_errored(self, session_factory):
        # Weder Titel noch Inhalt → überspringen statt 400/Fehler.
        async with session_factory() as db:
            node = ContextNode(
                id=uuid.uuid4(),
                title="",
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

        mock = _liefert([0.5] * DIM)
        with patch(STAPEL, new=mock):
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
            STAPEL,
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

        mock = _liefert([0.5] * DIM)
        with patch(STAPEL, new=mock):
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
        with patch(STAPEL, new=_liefert(fake)):
            async with session_factory() as db:
                stats = await backfill_embeddings(db, limit=2)

        assert stats.found == 2
        assert stats.ok == 2


class TestTaktung:
    """`EMBEDDING_TOKENS_PER_SECOND` begrenzt den Durchsatz — nach echtem Verbrauch.

    Vorher rechnete die Pause mit fest verdrahteten 150 Tokens je Knoten. Das lag bei
    langen Knoten um ein Vielfaches daneben (der Inhalt reicht bis EMBEDDING_MAX_CHARS)
    und war zugleich nicht abschaltbar.
    """

    @pytest_asyncio.fixture
    async def zwanzig_knoten(self, session_factory):
        async with session_factory() as db:
            for i in range(20):
                db.add(ContextNode(
                    id=uuid.uuid4(), title=f"IK {i}", content=f"Inhalt {i}",
                    category="knowledge", content_type="ik_kompetenz",
                    status="active", read_scope="global", write_scope="global",
                    metadata_={},
                ))
            await db.commit()

    @pytest_asyncio.fixture(autouse=True)
    def stapel_zu_fuenft(self):
        alt = settings.embedding_batch_size
        settings.embedding_batch_size = 5
        yield
        settings.embedding_batch_size = alt

    async def _lauf(self, session_factory, tempo: float) -> list[float]:
        """Führt den Backfill mit gegebenem Tempo aus, gibt die Wartezeiten zurück."""
        alt = settings.embedding_tokens_per_second
        settings.embedding_tokens_per_second = tempo
        pausen: list[float] = []

        async def _merken(sekunden):
            pausen.append(sekunden)

        try:
            with patch(STAPEL, new=_liefert([0.1] * DIM)), \
                 patch("app.crons.embedding_backfill_service.asyncio.sleep", new=_merken):
                async with session_factory() as db:
                    await backfill_embeddings(db, batch_size=100)
        finally:
            settings.embedding_tokens_per_second = alt
        return pausen

    @pytest.mark.asyncio
    async def test_pause_folgt_dem_verbrauch(self, session_factory, zwanzig_knoten):
        # 20 Knoten / Stapel 5 = 4 Anfragen à 50 Tokens (Attrappe: 10 je Text).
        pausen = await self._lauf(session_factory, tempo=25.0)

        # Drei Pausen, nicht vier: Vor der ERSTEN Anfrage gibt es nichts zu takten, und
        # hinter der letzten wäre Warten reine Verschwendung.
        assert pausen == [2.0, 2.0, 2.0]  # 50 Tokens / 25 pro Sekunde

    @pytest.mark.asyncio
    async def test_null_schaltet_die_drosselung_ab(self, session_factory, zwanzig_knoten):
        assert await self._lauf(session_factory, tempo=0.0) == []


class TestAbbruchBeiFehlerserie:
    """Ein kaputter Modellzugang darf den Lauf nicht stundenlang leerlaufen lassen.

    Realfall: Ein ungueltiger Anbieter-Schluessel beantwortet LiteLLM mit 401; LiteLLM
    nimmt die Deployment daraufhin in den Cooldown, und alle weiteren Anfragen bekommen
    `429 No deployments available`. Jede Anfrage kostet dann ihr volles
    Wiederholungsbudget — bei tausenden Knoten Stunden fuer ein Ergebnis, das nach dem
    dritten Versuch feststand.

    Gezaehlt werden seit der Stapelverarbeitung **Anfragen, nicht Knoten**: Ein Fehlschlag
    betrifft bis zu EMBEDDING_BATCH_SIZE Knoten auf einmal, und die verschwendete Zeit
    haengt an der Zahl der Anfragen.
    """

    @pytest_asyncio.fixture(autouse=True)
    def kleine_stapel(self):
        """Stapelgroesse 5, damit 40 Knoten ueberhaupt mehrere Anfragen ergeben.

        Mit dem Standard (64) waeren alle 40 Knoten eine einzige Anfrage — die
        Abbruchschwelle liesse sich dann gar nicht erreichen.
        """
        alt = settings.embedding_batch_size
        settings.embedding_batch_size = 5
        yield
        settings.embedding_batch_size = alt

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
        from app.crons.embedding_backfill_service import _MAX_STAPEL_FEHLER_IN_FOLGE

        with patch(
            STAPEL,
            new_callable=AsyncMock,
            side_effect=RuntimeError("429 No deployments available"),
        ) as gen:
            async with session_factory() as db:
                stats = await backfill_embeddings(db, batch_size=100)

        assert stats.abgebrochen is True
        # Genau bis zur Schwelle versucht, danach keine Anfrage mehr.
        assert gen.await_count == _MAX_STAPEL_FEHLER_IN_FOLGE
        # Jede gescheiterte Anfrage markiert ihre 5 Knoten.
        assert stats.errors == _MAX_STAPEL_FEHLER_IN_FOLGE * 5
        assert stats.found == 40

    @pytest.mark.asyncio
    async def test_nicht_versuchte_knoten_bleiben_unberuehrt(
        self, session_factory, viele_knoten
    ):
        """Sie behalten `embedding IS NULL` und werden im naechsten Lauf erneut geholt."""
        with patch(
            STAPEL,
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
        assert markiert == 15        # 3 gescheiterte Anfragen à 5 Knoten

    @pytest.mark.asyncio
    async def test_vereinzelte_fehler_brechen_nicht_ab(self, session_factory, viele_knoten):
        """Nur eine *ununterbrochene* Serie zaehlt — ein Erfolg setzt sie zurueck."""
        fake = [0.1] * DIM
        aufrufe = {"n": 0}

        async def _mal_so_mal_so(texte):
            aufrufe["n"] += 1
            if aufrufe["n"] % 2 == 0:
                raise RuntimeError("500 Internal Server Error")
            return EmbeddingStapel(vektoren=[list(fake) for _ in texte], tokens=10)

        with patch(STAPEL, new=_mal_so_mal_so):
            async with session_factory() as db:
                stats = await backfill_embeddings(db, batch_size=100)

        assert stats.abgebrochen is False
        assert stats.ok == 20        # 4 gelungene Anfragen à 5 Knoten
        assert stats.errors == 20    # 4 gescheiterte Anfragen à 5 Knoten

    @pytest.mark.asyncio
    async def test_ein_schlechter_text_reisst_den_stapel_nicht_mit(
        self, session_factory, viele_knoten
    ):
        """400 = Inhaltsfehler → einzeln nachfassen, statt 4 gute Knoten mitzureissen.

        Das ist der reale Fall aus dem IONOS-Umstieg: BGE-M3 lehnt einen leeren Text mit
        400 ab, OpenAI nahm ihn an. Ohne Isolierung bekaeme der ganze Stapel einen
        `embedding_error`.
        """
        fake = [0.1] * DIM

        async def _einer_ist_schlecht(texte):
            if len(texte) > 1 and any("IK 7 " in t or t.endswith("Inhalt 7") for t in texte):
                antwort = httpx.Response(
                    400, request=httpx.Request("POST", "http://x/embeddings")
                )
                raise httpx.HTTPStatusError("bad", request=antwort.request, response=antwort)
            if len(texte) == 1 and ("IK 7 " in texte[0] or texte[0].endswith("Inhalt 7")):
                antwort = httpx.Response(
                    400, request=httpx.Request("POST", "http://x/embeddings")
                )
                raise httpx.HTTPStatusError("bad", request=antwort.request, response=antwort)
            return EmbeddingStapel(vektoren=[list(fake) for _ in texte], tokens=10)

        with patch(STAPEL, new=_einer_ist_schlecht):
            async with session_factory() as db:
                stats = await backfill_embeddings(db, batch_size=100)

        assert stats.abgebrochen is False
        assert stats.errors == 1, "nur der schuldige Text scheitert"
        assert stats.ok == 39, "die uebrigen 39 Knoten bekommen ihren Vektor"
