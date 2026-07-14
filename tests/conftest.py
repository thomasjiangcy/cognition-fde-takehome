from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from pydantic import PostgresDsn
from sqlalchemy import delete
from testcontainers.postgres import PostgresContainer

from app.automation.models import TriggerEvent, WorkflowRun
from app.config import DatabaseSettings
from app.database import Database

POSTGRES_IMAGE = "postgres:18.4-alpine"


@pytest.fixture(scope="session")
def postgres_database_url() -> Iterator[str]:
    with PostgresContainer(POSTGRES_IMAGE, driver="psycopg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture(scope="session")
def migrated_database_url(postgres_database_url: str) -> str:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_database_url)
    command.upgrade(config, "head")
    return postgres_database_url


@pytest.fixture
async def database(migrated_database_url: str) -> AsyncIterator[Database]:
    database = Database.create(
        DatabaseSettings(database_url=PostgresDsn(migrated_database_url))
    )
    try:
        yield database
    finally:
        async with database.sessions.begin() as session:
            await session.execute(delete(WorkflowRun))
            await session.execute(delete(TriggerEvent))
        await database.close()
