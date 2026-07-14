import pytest
from alembic import command
from alembic.config import Config
from testcontainers.postgres import PostgresContainer

pytestmark = pytest.mark.database


def test_migrations_upgrade_from_base_and_match_models() -> None:
    with PostgresContainer("postgres:18.4-alpine", driver="psycopg") as postgres:
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", postgres.get_connection_url())

        command.upgrade(config, "head")
        command.check(config)
