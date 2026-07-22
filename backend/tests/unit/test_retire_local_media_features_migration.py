from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa


def _load_migration():
    path = Path(__file__).parents[2] / "alembic" / "versions" / "202607210001_retire_local_media_features.py"
    spec = spec_from_file_location("retire_local_media_features", path)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_retire_local_media_tasks_is_idempotent_and_preserves_terminal_rows():
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    tasks = sa.Table(
        "generation_tasks",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("provider_code", sa.String),
        sa.Column("status", sa.String),
        sa.Column("progress", sa.Integer),
        sa.Column("workflow_stage", sa.String),
        sa.Column("last_error_type", sa.String),
        sa.Column("error_message", sa.Text),
        sa.Column("scheduler_next_run_at", sa.DateTime),
        sa.Column("scheduler_claim_token", sa.String),
        sa.Column("scheduler_claimed_at", sa.DateTime),
        sa.Column("scheduler_lease_expires_at", sa.DateTime),
        sa.Column("terminalized_at", sa.DateTime),
        sa.Column("terminal_side_effects_finalized_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(tasks.insert(), [
            {"id": 1, "provider_code": "local_rembg", "status": "processing", "progress": 10},
            {"id": 2, "provider_code": "local_rembg", "status": "completed", "progress": 100},
            {"id": 3, "provider_code": "builtin", "status": "processing", "progress": 20},
        ])
        migration._retire_tasks(connection)
        migration._retire_tasks(connection)
        rows = {row.id: row for row in connection.execute(sa.select(tasks)).mappings()}

    assert rows[1]["status"] == "failed"
    assert rows[1]["progress"] == 100
    assert rows[1]["last_error_type"] == "feature_removed"
    assert rows[1]["scheduler_claim_token"] is None
    assert rows[2]["status"] == "completed"
    assert rows[3]["status"] == "processing"
