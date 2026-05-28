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

# Pseudonyme der Test-Nutzer
TEACHER1_PSEUDO = "teacher1-pseudo"
TEACHER2_PSEUDO = "teacher2-pseudo"


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
    """Spielt die Alembic-Migrationen gegen die Test-DB durch."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(sync_url)
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
