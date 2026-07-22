from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_billing_migration_module():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "202605120001_billing_amount_cents.py"
    )
    spec = spec_from_file_location("billing_migration_202605120001", migration_path)
    assert spec is not None
    assert spec.loader is not None

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reset_billing_tables_nulls_parent_links_before_deleting_rows(monkeypatch):
    migration = _load_billing_migration_module()
    executed_sql: list[str] = []

    monkeypatch.setattr(migration.op, "execute", executed_sql.append)

    migration._reset_billing_tables()

    assert executed_sql == [
        "UPDATE usage_logs SET parent_id = NULL WHERE parent_id IS NOT NULL",
        "DELETE FROM usage_logs",
        "DELETE FROM redemption_logs",
    ]


def test_plan_column_changes_adds_missing_and_drops_legacy_columns():
    migration = _load_billing_migration_module()

    add, drop = migration._plan_column_changes(
        {"id", "credits", "created_at"},
        add=("balance_cents",),
        drop=("credits",),
    )

    assert add == ["balance_cents"]
    assert drop == ["credits"]


def test_plan_column_changes_skips_columns_already_in_target_shape():
    migration = _load_billing_migration_module()

    add, drop = migration._plan_column_changes(
        {"id", "balance_cents", "created_at"},
        add=("balance_cents",),
        drop=("credits",),
    )

    assert add == []
    assert drop == []
