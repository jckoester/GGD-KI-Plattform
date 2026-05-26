"""Fixtures für Integrationstests.

Erwartet eine laufende PostgreSQL-Instanz mit pgvector.
Verbindungs-URL aus TEST_DATABASE_URL (Umgebungsvariable oder .env).

Beispiel:
  TEST_DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/ggd_ki_test
"""

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()


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
