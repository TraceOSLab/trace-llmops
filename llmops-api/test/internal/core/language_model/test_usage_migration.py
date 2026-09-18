"""直接生成 PostgreSQL DDL，不导入会加载真实配置的 migrations/env.py。"""
import importlib.util
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory


def test_usage_migration_has_single_head_and_renders_upgrade_sql():
    migrations = Path(__file__).parents[4] / "internal/migrations"
    script = ScriptDirectory(str(migrations))
    assert script.get_current_head() == "b739fd026a81"
    spec = importlib.util.spec_from_file_location("usage_migration", migrations / "versions/b739fd026a81_agent_usage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = StringIO()
    context = MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        module.upgrade()
    sql = output.getvalue()
    for table in ["message", "message_agent_thought"]:
        assert f"ALTER TABLE {table} ADD COLUMN usage JSONB" in sql
        assert f"ALTER TABLE {table} ALTER COLUMN message_price_unit TYPE NUMERIC(18, 10)" in sql
    assert "DROP" not in sql
