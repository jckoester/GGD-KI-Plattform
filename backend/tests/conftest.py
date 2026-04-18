import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from testcontainers.postgresql import PostgresContainer

TEST_SCHOOL_SECRET = "test-secret-not-for-production-000000000000"

# Set env vars at module level so Settings() picks them up on first import
os.environ["SCHOOL_SECRET"] = TEST_SCHOOL_SECRET
os.environ["JWT_SECRET"] = "test-jwt-secret-0000000000000000000000"
os.environ["ENVIRONMENT"] = "test"


@pytest.fixture(scope="session")
def postgres_container():
    container = PostgresContainer("postgres:15", database="test_ggd_ki")
    container.start()
    yield container
    container.stop()


@pytest_asyncio.fixture(scope="session")
async def db_engine(postgres_container):
    sync_url = postgres_container.get_connection_url()
    async_url = sync_url.replace("postgresql+psycopg2", "postgresql+asyncpg")

    # Set DATABASE_URL before app.config is imported for the first time
    os.environ["DATABASE_URL"] = async_url

    engine = create_async_engine(async_url)

    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(alembic_cfg, "head")

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine):
    AsyncTestingSession = async_sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with AsyncTestingSession() as session:
        yield session
        await session.rollback()
