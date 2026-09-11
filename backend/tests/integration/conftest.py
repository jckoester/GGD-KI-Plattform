"""Fixtures für Integrationstests.

Erwartet eine laufende PostgreSQL-Instanz mit pgvector.
Verbindungs-URL aus TEST_DATABASE_URL (Umgebungsvariable oder .env).

Beispiel:
  TEST_DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/ggd_ki_test
"""

import os
from collections.abc import AsyncIterator

import psycopg2
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

# Inline-Embeddings in Tests global deaktivieren: In der Testumgebung läuft kein
# LiteLLM-Proxy; der Embedding-Aufruf würde fehlschlagen und 'embedding_error' in
# die Knoten-Metadaten schreiben (verfälscht Tests, z. B. Metadaten-Vergleiche).
# Früh genug (Modulimport der conftest), bevor App-Module/Seeds Knoten anlegen.
# Der Batch-Service backfill_embeddings bleibt unberührt (Tests mocken dort gezielt).
from app.config import settings as _settings
_settings.embeddings_enabled = False

# Pseudonyme der Test-Nutzer
TEACHER1_PSEUDO = "teacher1-pseudo"
TEACHER2_PSEUDO = "teacher2-pseudo"
STUDENT_PSEUDO = "student1-pseudo"


def _get_test_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL ist nicht gesetzt. "
            "Bitte in .env oder als Umgebungsvariable setzen:\n"
            "  TEST_DATABASE_URL=postgresql+asyncpg://postgres:pw@localhost:5432/ggd_ki_test"
        )
    return url


@pytest.fixture(scope="session")
def db_url() -> str:
    """Asyncpg-URL der Test-Datenbank (aus TEST_DATABASE_URL)."""
    return _get_test_db_url()


@pytest.fixture(scope="session")
def run_migrations(db_url):
    """Setzt das Schema der Test-DB zurück und spielt alle Migrationen durch.

    Der Schema-Reset (DROP/CREATE) zu Session-Beginn garantiert eine saubere DB pro
    Test-Lauf und verhindert Pollution durch committende, nicht-idempotente Session-
    Seeds (z. B. seed_phase4_data mit festen IDs), die sonst Folgeläufe mit
    Duplicate-Key brechen lassen.
    """
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    # Sicherheitsnetz: niemals eine Nicht-Test-DB zurücksetzen.
    db_name = sync_url.rsplit("/", 1)[-1].split("?", 1)[0].lower()
    if "test" not in db_name:
        raise RuntimeError(
            f"Schema-Reset abgelehnt: TEST_DATABASE_URL zeigt nicht auf eine Test-DB "
            f"('test' im DB-Namen erwartet, gefunden: '{db_name}')."
        )

    engine = create_engine(sync_url)
    with engine.connect() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.commit()
    with engine.connect() as connection:
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")
    engine.dispose()
    return sync_url


@pytest_asyncio.fixture
async def async_engine(db_url, run_migrations):
    """Async-Engine gegen die migrierte Test-DB — neu pro Test."""
    engine = create_async_engine(db_url, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncIterator[AsyncSession]:
    """Transaktionale DB-Session — wird nach jedem Test zurückgerollt."""
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest_asyncio.fixture
async def erklaerplan(db_url, run_migrations):
    """Liefert den EXPLAIN-Plan einer Abfrage — mit abgeschaltetem Seq Scan.

    Gegenstand solcher Prüfungen ist, ob ein Index **benutzbar** ist: ob der Ausdruck der
    Abfrage zeichengenau dem des Index entspricht. Weicht er ab, kann PostgreSQL den Index
    nicht verwenden — still, ohne Fehler, nur langsamer (Migration 0053).

    Ob der Planer ihn dann auch *wählt*, ist eine andere Frage und hängt an der Tabelle:
    Unter rund 40 Zeilen ist der vollständige Durchlauf wirklich billiger, und der Planer
    entscheidet richtig. Genau daran hing dieser Wächter bis 11.09.2026 — er wurde rot,
    wenn Autoanalyze zufällig lief, während wenige Testzeilen in `context_nodes` standen.

    `enable_seqscan = off` trennt beides: Passt der Ausdruck, greift der Index bei jeder
    Tabellengröße. Passt er nicht, bleibt nur der Durchlauf, und die Prüfung wird rot —
    nachgemessen mit `btrim` → `rtrim` bei 0, 5 und 41 Zeilen.
    """
    import sqlalchemy as sa

    engine = create_async_engine(db_url)

    async def plan(abfrage) -> str:
        # `literal_binds`, weil EXPLAIN die Werte braucht: Ein Platzhalter ohne Wert lässt
        # den Planer generisch planen — dann sagt der Plan nichts über den Fall.
        roh = str(abfrage.compile(compile_kwargs={"literal_binds": True}))
        # `begin()`, nicht `connect()`: `SET LOCAL` außerhalb einer Transaktion verpufft
        # mit einer bloßen Warnung — die Prüfung wäre wieder von der Tabellengröße abhängig.
        async with engine.begin() as con:
            await con.execute(sa.text("SET LOCAL enable_seqscan = off"))
            zeilen = (await con.execute(sa.text("EXPLAIN " + roh))).all()
        return "\n".join(r[0] for r in zeilen)

    yield plan
    await engine.dispose()


# ── HTTP-TestClient und Auth-Fixtures ─────────────────────────────────────────

@pytest.fixture(scope="session")
def jwt_service():
    """JWT-Service mit dem konfigurierten App-Secret (gecacht)."""
    from app.auth.dependencies import get_jwt_service
    return get_jwt_service()


@pytest.fixture
def auth_headers(jwt_service):
    """HTTP-Cookie-Header für teacher1-pseudo (Eigentümer von Assistent 1)."""
    token, _ = jwt_service.issue(pseudonym=TEACHER1_PSEUDO, roles=["teacher", "admin"], grade=None)
    return {"Cookie": f"session={token}"}


@pytest.fixture
def auth_headers_teacher2(jwt_service):
    """HTTP-Cookie-Header für teacher2-pseudo (fremde Lehrkraft)."""
    token, _ = jwt_service.issue(pseudonym=TEACHER2_PSEUDO, roles=["teacher"], grade=None)
    return {"Cookie": f"session={token}"}


@pytest.fixture
def auth_headers_student(jwt_service):
    """HTTP-Cookie-Header für student1-pseudo (Schüler:in, Klasse 8).

    Seit 09/2026 sind die Lesepfade des Kontextspeichers rollenoffen (ADR-019 F8);
    was sichtbar ist, entscheidet `read_scope_clause`. Dafür braucht es einen Token
    **ohne** Lehrkraft-Rolle — mit `teacher` liefen die Tests an der Regel vorbei.
    """
    # `grade` ist im JWT eine **Zeichenkette** (`JwtPayload`), nicht eine Zahl —
    # eine 8 statt "8" scheitert erst beim Verifizieren, nicht beim Ausstellen.
    token, _ = jwt_service.issue(pseudonym=STUDENT_PSEUDO, roles=["student"], grade="8")
    return {"Cookie": f"session={token}"}


@pytest.fixture(scope="session")
def seed_test_assistant(db_url, run_migrations):
    """Legt Assistent ID=1 (owned by teacher1-pseudo) einmalig in der Test-DB an."""
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO assistants
              (id, name, system_prompt, model, status, audience, scope,
               created_by, creator_role)
            VALUES
              (1, 'Test-Assistent', 'Du bist ein Testassistent.', 'gpt-4o',
               'active', 'all', 'all', %s, 'teacher')
            ON CONFLICT (id) DO UPDATE SET created_by = EXCLUDED.created_by
        """, (TEACHER1_PSEUDO,))
        # Sequenz nachziehen: Der Seed setzt die ID explizit und laesst die
        # Sequenz sonst auf 1 stehen — ein spaeteres INSERT ohne ID kollidiert
        # dann mit genau diesem Datensatz.
        cur.execute("""
            SELECT setval(pg_get_serial_sequence('assistants', 'id'),
                          (SELECT MAX(id) FROM assistants))
        """)
    conn.commit()
    conn.close()
    return 1


@pytest.fixture(scope="session")
def seed_test_group(db_url, run_migrations):
    """Legt Gruppe ID=1 einmalig in der Test-DB an (für Engagement-Tests)."""
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO groups (id, name, slug, type)
            VALUES (1, 'Test-Gruppe', 'test-gruppe', 'teaching_group')
            ON CONFLICT (id) DO NOTHING
        """)
        cur.execute("""
            SELECT setval(pg_get_serial_sequence('groups', 'id'),
                          (SELECT MAX(id) FROM groups))
        """)
    conn.commit()
    conn.close()
    return 1


@pytest_asyncio.fixture
async def test_client(async_engine, seed_test_assistant):
    """Async HTTP-TestClient für die FastAPI-App gegen die Test-DB."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    from app.db.session import get_db

    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
