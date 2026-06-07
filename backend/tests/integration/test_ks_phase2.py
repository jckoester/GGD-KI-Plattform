"""KS-Phase-2 Integrations-Tests: Import-Skript, Embedding-Batch."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import psycopg2
import psycopg2.extras
import pytest

FIXTURE_DIR = Path(__file__).parent / 'fixtures'
_REPO_SCRIPTS = Path(__file__).parent.parent.parent.parent / 'scripts'


def _import_repo_script(module_name: str):
    """Load a module from GGD-KI-Plattform/scripts/ by absolute path.

    Registers the module under 'scripts.<module_name>' in sys.modules so that
    unittest.mock.patch() can locate it by its dotted name, regardless of what
    'scripts' package may already be cached from backend/scripts/.
    """
    script_path = _REPO_SCRIPTS / f'{module_name}.py'
    full_name = f'scripts.{module_name}'
    spec = importlib.util.spec_from_file_location(full_name, script_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def truncate_context_tables(db_url, run_migrations):
    """Leert context_nodes und context_edges vor jedem Test (psycopg2-Commits isolieren)."""
    conn = psycopg2.connect(get_sync_url(db_url))
    with conn.cursor() as cur:
        cur.execute("TRUNCATE context_edges, context_nodes RESTART IDENTITY CASCADE")
    conn.commit()
    conn.close()
    yield


def get_sync_url(db_url: str) -> str:
    """Konvertiert asyncpg-URL zu psycopg2-URL."""
    return db_url.replace('postgresql+asyncpg://', 'postgresql://')


def run_import(db_url: str, jsonl_path: Path) -> None:
    """Hilfsfunktion: import_bildungsplan.run_import() gegen Test-DB aufrufen."""
    import tempfile
    import yaml
    _run_import = _import_repo_script('import_bildungsplan').run_import

    # Minimale subjects.yaml fuer den Test
    subjects_cfg = {
        'schulart': 'GYM',
        'schuljahr': '2026/27',
        'bildungsplan_default': {'bp_basis': 'BP2016BW', 'suffix': ''},
        'subjects': [],
    }
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.yaml', delete=False, encoding='utf-8'
    ) as f:
        yaml.dump(subjects_cfg, f)
        subjects_path = f.name

    # Temp-Verzeichnis mit nur einer JSONL-Datei
    import tempfile as _tmp
    with _tmp.TemporaryDirectory() as tmpdir:
        import shutil
        dest = Path(tmpdir) / jsonl_path.name
        shutil.copy(jsonl_path, dest)
        _run_import(
            subjects_path=subjects_path,
            input_dir=tmpdir,
            db_url=get_sync_url(db_url),
            dry_run=False,
        )


# -----------------------------------------------------------------------------

class TestMigration0019:
    """Prueft dass Migration 0019 korrekt eingespielt ist."""

    def test_related_to_in_constraint(self, db_url):
        conn = psycopg2.connect(get_sync_url(db_url))
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'check_context_edges_relation'
            """)
            row = cur.fetchone()
        conn.close()
        assert row is not None
        assert 'related_to' in row[0]

    def test_leitperspektive_aspekt_valid_in_taxonomy(self):
        from app.context.taxonomy import validate_content_type
        validate_content_type('knowledge', 'leitperspektive_aspekt')  # darf nicht werfen


# -----------------------------------------------------------------------------

class TestImportIdempotency:
    """Zweimaliger Import derselben JSONL -> zweiter Lauf aendert nichts."""

    def test_second_import_zero_changes(self, db_url):
        jsonl = FIXTURE_DIR / 'bp_import_5nodes.jsonl'
        run_import(db_url, jsonl)

        # Zweiter Lauf
        conn = psycopg2.connect(get_sync_url(db_url))
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM context_nodes WHERE category = 'knowledge'")
            count_before = cur.fetchone()[0]
        conn.close()

        run_import(db_url, jsonl)

        conn = psycopg2.connect(get_sync_url(db_url))
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM context_nodes WHERE category = 'knowledge'")
            count_after = cur.fetchone()[0]
        conn.close()

        assert count_before == count_after

    def test_import_creates_5_nodes(self, db_url):
        run_import(db_url, FIXTURE_DIR / 'bp_import_5nodes.jsonl')
        conn = psycopg2.connect(get_sync_url(db_url))
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM context_nodes WHERE category = 'knowledge' AND status = 'active'"
            )
            count = cur.fetchone()[0]
        conn.close()
        assert count == 5


# -----------------------------------------------------------------------------

class TestImportHashUpdate:
    """Knoten mit geaendertem Hash -> UPDATE; embedding wird auf NULL zurueckgesetzt."""

    def test_updated_node_has_null_embedding(self, db_url):
        # Erst Basis importieren
        run_import(db_url, FIXTURE_DIR / 'bp_import_5nodes.jsonl')

        # Manuell ein Fake-Embedding setzen (1536 Dimensionen wie text-embedding-3-small)
        fake_vec = '[' + ','.join(['0.1'] * 1536) + ']'
        conn = psycopg2.connect(get_sync_url(db_url))
        psycopg2.extras.register_uuid(conn)
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE context_nodes SET embedding = '{fake_vec}'::vector "
                "WHERE metadata->>'bp_id' = 'BP2016BW_ALLG_GYM_TST_IK_5-6_01_01'"
            )
        conn.commit()
        conn.close()

        # Updated JSONL importieren (geaenderter Hash)
        run_import(db_url, FIXTURE_DIR / 'bp_import_5nodes_updated.jsonl')

        # Embedding muss NULL sein
        conn = psycopg2.connect(get_sync_url(db_url))
        with conn.cursor() as cur:
            cur.execute(
                "SELECT embedding FROM context_nodes "
                "WHERE metadata->>'bp_id' = 'BP2016BW_ALLG_GYM_TST_IK_5-6_01_01'"
            )
            row = cur.fetchone()
        conn.close()
        assert row[0] is None

    def test_updated_node_has_new_content(self, db_url):
        run_import(db_url, FIXTURE_DIR / 'bp_import_5nodes.jsonl')
        run_import(db_url, FIXTURE_DIR / 'bp_import_5nodes_updated.jsonl')

        conn = psycopg2.connect(get_sync_url(db_url))
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM context_nodes "
                "WHERE metadata->>'bp_id' = 'BP2016BW_ALLG_GYM_TST_IK_5-6_01_01'"
            )
            content = cur.fetchone()[0]
        conn.close()
        assert 'erweitertem Kontext' in content


# -----------------------------------------------------------------------------

class TestImportArchiving:
    """Knoten der im zweiten Lauf nicht mehr im JSONL vorkommt -> archived."""

    def test_removed_node_gets_archived(self, db_url):
        # Erst 5 Knoten importieren
        run_import(db_url, FIXTURE_DIR / 'bp_import_5nodes.jsonl')

        # Dann 4 Knoten (IK fehlt)
        run_import(db_url, FIXTURE_DIR / 'bp_import_4nodes.jsonl')

        conn = psycopg2.connect(get_sync_url(db_url))
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM context_nodes "
                "WHERE metadata->>'bp_id' = 'BP2016BW_ALLG_GYM_TST_IK_5-6_01_01'"
            )
            row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 'archived'


# -----------------------------------------------------------------------------

class TestEdgeResolution:
    """Kanten werden korrekt angelegt."""

    def test_part_of_edge_exists(self, db_url):
        run_import(db_url, FIXTURE_DIR / 'bp_import_5nodes.jsonl')

        conn = psycopg2.connect(get_sync_url(db_url))
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.relation
                FROM context_edges e
                JOIN context_nodes src ON src.id = e.from_node_id
                JOIN context_nodes tgt ON tgt.id = e.to_node_id
                WHERE src.metadata->>'bp_id' = 'BP2016BW_ALLG_GYM_TST_IK_5-6_01_01'
                  AND tgt.metadata->>'bp_id' = 'BP2016BW_ALLG_GYM_TST_IK_5-6_01'
            """)
            rows = cur.fetchall()
        conn.close()
        relations = [r[0] for r in rows]
        assert 'part_of' in relations

    def test_references_edge_to_lp_aspekt(self, db_url):
        run_import(db_url, FIXTURE_DIR / 'bp_import_5nodes.jsonl')

        conn = psycopg2.connect(get_sync_url(db_url))
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.relation
                FROM context_edges e
                JOIN context_nodes src ON src.id = e.from_node_id
                JOIN context_nodes tgt ON tgt.id = e.to_node_id
                WHERE src.metadata->>'bp_id' = 'BP2016BW_ALLG_GYM_TST_IK_5-6_01_01'
                  AND tgt.metadata->>'bp_id' = 'TEST_01'
            """)
            rows = cur.fetchall()
        conn.close()
        relations = [r[0] for r in rows]
        assert 'references' in relations

    def test_lp_aspekt_part_of_lp(self, db_url):
        run_import(db_url, FIXTURE_DIR / 'bp_import_5nodes.jsonl')

        conn = psycopg2.connect(get_sync_url(db_url))
        with conn.cursor() as cur:
            cur.execute("""
                SELECT count(*)
                FROM context_edges e
                JOIN context_nodes src ON src.id = e.from_node_id
                JOIN context_nodes tgt ON tgt.id = e.to_node_id
                WHERE src.metadata->>'bp_id' IN ('TEST_01', 'TEST_02')
                  AND tgt.metadata->>'bp_id' = 'BP2016BW_ALLG_LP_TEST'
                  AND e.relation = 'part_of'
            """)
            count = cur.fetchone()[0]
        conn.close()
        assert count == 2


# -----------------------------------------------------------------------------

class TestUnresolvableEdge:
    """Kante auf nicht-existente bp_id -> ueberspringen, kein Fehler."""

    def test_import_succeeds_with_missing_target(self, db_url, tmp_path):
        # JSONL mit Relation auf nicht-existente bp_id
        bad_jsonl = tmp_path / 'bad.jsonl'
        node = {
            'bp_id': 'TEST_ORPHAN_IK',
            'type': 'knowledge',
            'content_type': 'ik_kompetenz',
            'title': 'Waise',
            'content': 'Waise ohne Eltern',
            'content_hash': 'sha256:orphan001',
            'parent_bp_id': 'DOES_NOT_EXIST',
            'relations': [{'type': 'develops', 'target_bp_id': 'ALSO_DOES_NOT_EXIST'}],
            'metadata': {
                'bp_id': 'TEST_ORPHAN_IK',
                'breadcrumb': ['Test'],
                'source_url': 'https://example.com',
                'scraped_at': '2026-05-26T10:00:00Z',
                'content_hash': 'sha256:orphan001',
            },
            'visibility': 'global',
        }
        bad_jsonl.write_text(json.dumps(node, ensure_ascii=False) + '\n')

        # Darf nicht werfen
        import tempfile
        import yaml
        _run_import = _import_repo_script('import_bildungsplan').run_import
        subjects_cfg = {
            'schulart': 'GYM', 'schuljahr': '2026/27',
            'bildungsplan_default': {'bp_basis': 'BP2016BW', 'suffix': ''},
            'subjects': [],
        }
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.yaml', delete=False, encoding='utf-8'
        ) as f:
            yaml.dump(subjects_cfg, f)
            subjects_path = f.name

        _run_import(subjects_path, str(tmp_path), get_sync_url(db_url), dry_run=False)

        # Knoten wurde trotzdem angelegt
        conn = psycopg2.connect(get_sync_url(db_url))
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM context_nodes WHERE metadata->>'bp_id' = 'TEST_ORPHAN_IK'"
            )
            count = cur.fetchone()[0]
        conn.close()
        assert count == 1


# -----------------------------------------------------------------------------

class TestEmbeddingBatch:
    """Embedding-Batch verarbeitet Whitelist-Knoten, ignoriert andere."""

    @pytest.mark.asyncio
    async def test_batch_writes_embeddings_for_whitelist(self, async_engine, db_url):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from app.context.embedding import EMBEDDING_CONTENT_TYPES
        from app.crons.embedding_backfill_service import backfill_embeddings

        # Knoten importieren (psycopg2, committed)
        run_import(db_url, FIXTURE_DIR / 'bp_import_5nodes.jsonl')

        fake_embedding = [0.1] * 1536

        factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        with patch(
            'app.crons.embedding_backfill_service.generate_embedding',
            new_callable=AsyncMock,
            return_value=fake_embedding,
        ):
            async with factory() as db:
                await backfill_embeddings(db, batch_size=10, dry_run=False)

        conn = psycopg2.connect(get_sync_url(db_url))
        with conn.cursor() as cur:
            cur.execute("""
                SELECT content_type, count(*) FILTER (WHERE embedding IS NULL) as ohne
                FROM context_nodes
                WHERE content_type IN %s AND status = 'active'
                GROUP BY content_type
            """, (tuple(EMBEDDING_CONTENT_TYPES),))
            rows = cur.fetchall()
        conn.close()
        for content_type, ohne in rows:
            assert ohne == 0, f"{content_type}: noch {ohne} Knoten ohne Embedding"

    def test_fachplan_gets_no_embedding(self, db_url):
        from app.context.embedding import EMBEDDING_CONTENT_TYPES
        assert 'fachplan' not in EMBEDDING_CONTENT_TYPES
        assert 'leitperspektive' not in EMBEDDING_CONTENT_TYPES
