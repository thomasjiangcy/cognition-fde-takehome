from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_history_has_single_head() -> None:
    scripts = ScriptDirectory.from_config(Config("alembic.ini"))

    assert scripts.get_heads() == ["20260714_0001"]
