"""Testcontainers-Fixtures für Integrationstests.

Startet eine pgvector-Postgres-Instanz für die gesamte Test-Session.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer


POSTGRES_IMAGE = "pgvector/pgvector:pg16"


@pytest.fixture(scope="session")
def postgres_container():
    """Startet den Postgres-Container für die gesamte Test-Session."""
    with PostgresContainer(POSTGRES_IMAGE) as pg:
        yield pg


@pytest.fixture(scope="session")
def db_url(postgres_container) -> str:
    """Asyncpg-URL des Testcontainers."""
    sync_url = postgres_container.get_connection_url()
    # testcontainers liefert psycopg2-URL; für asyncpg das Schema tauschen
    return sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")


@pytest.fixture(scope="session")
def run_migrations(postgres_container):
    """Spielt die Alembic-Migrationen gegen die Test-DB durch."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    sync_url = postgres_container.get_connection_url()
    engine = create_engine(sync_url)
    with engine.connect() as connection:
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")
    engine.dispose()
    return sync_url


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def async_engine(db_url, run_migrations):
    """Async-Engine gegen die migrierte Test-DB."""
    engine = create_async_engine(db_url, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(async_engine) -> AsyncIterator[AsyncSession]:
    """Transaktionale DB-Session — wird nach jedem Test zurückgerollt."""
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()
