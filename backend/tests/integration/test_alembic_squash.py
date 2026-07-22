import re
from pathlib import Path

import sqlalchemy as sa

from alembic import command
from alembic.config import Config
from app.core import config as config_module

BACKEND_DIR = Path(__file__).resolve().parents[2]
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"
EXPECTED_TABLES = {
    "users",
    "user_providers",
    "provider_credentials",
    "provider_models",
    "projects",
    "project_members",
    "project_user_canvases",
    "generation_tasks",
    "project_assets",
    "user_asset_favorites",
    "harness_conversations",
    "harness_agent_runs",
    "harness_agent_steps",
    "harness_agent_activities",
    "harness_messages",
    "harness_workspace_files",
    "conversation_events",
    "context_projection_state",
    "context_projection_runs",
    "usage_logs",
    "license_records",
    "photoshop_edit_jobs",
    "reference_taxonomies",
    "reference_images",
}
EXPECTED_REFERENCE_GALLERY_CATEGORIES = {
    "针织毛衣短袖",
    "套装",
    "衬衫",
    "短袖",
    "防晒衣",
    "休闲裤",
    "马甲",
    "背心",
    "短裤",
    "Polo衫",
}
REVISION_RE = re.compile(r"^revision\s*(?::\s*[^=]+)?=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
DOWN_REVISION_RE = re.compile(
    r"^down_revision\s*(?::\s*[^=]+)?=\s*(.+)$",
    re.MULTILINE,
)


def _migration_files() -> list[Path]:
    return sorted(path for path in VERSIONS_DIR.glob("*.py") if path.name != "__init__.py")


def _extract_revision(path: Path) -> str:
    match = REVISION_RE.search(path.read_text(encoding="utf-8"))
    assert match, f"Could not find revision in {path.name}"
    return match.group(1)


def _extract_down_revision(path: Path) -> str | tuple[str, ...] | None:
    match = DOWN_REVISION_RE.search(path.read_text(encoding="utf-8"))
    assert match, f"Could not find down_revision in {path.name}"
    raw_value = match.group(1).strip()
    if raw_value == "None":
        return None
    if raw_value.startswith(("(", "[")):
        return tuple(re.findall(r"['\"]([^'\"]+)['\"]", raw_value))
    single = re.match(r"['\"]([^'\"]+)['\"]", raw_value)
    assert single, f"Could not parse down_revision in {path.name}: {raw_value}"
    return single.group(1)


def test_revision_graph_keeps_legacy_usage_log_revision_available():
    revisions = {_extract_revision(path): _extract_down_revision(path) for path in _migration_files()}

    assert revisions["202603240001"] is None
    assert revisions["202603250001"] == "202603240001"
    assert revisions["202605070001"] == "202603250001"
    assert revisions["202605160001"] == "202605150001"
    assert revisions["202605160002"] == "202605160001"
    assert revisions["202606120002"] == "202606110001"
    assert revisions["202606130001"] == "202606110001"
    assert revisions["202606210001"] == ("202606120002", "202606130001")
    assert revisions["202606250001"] == "202606220001"
    assert revisions["b9dd9fbb39c0"] == "202603240001"
    assert revisions["4f9d8d7b2c10"] == "b9dd9fbb39c0"


def test_alembic_upgrade_heads_bootstraps_schema_and_seed(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic_squash.sqlite3"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.setattr(config_module.settings, "DATABASE_URL", database_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    command.upgrade(config, "heads")

    sync_engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    inspector = sa.inspect(sync_engine)
    table_names = set(inspector.get_table_names())

    assert EXPECTED_TABLES.issubset(table_names)
    assert "redemption_logs" not in table_names

    with sync_engine.connect() as connection:
        seeded_email = connection.execute(
            sa.text("SELECT email FROM users WHERE email = 'admin@admin.com'")
        ).scalar_one()
        rows = connection.execute(
            sa.text(
                """
                SELECT name
                FROM reference_taxonomies
                WHERE kind = 'category'
                """
            )
        ).scalars().all()

    assert seeded_email == "admin@admin.com"
    assert set(rows) == EXPECTED_REFERENCE_GALLERY_CATEGORIES


def test_photoshop_edit_jobs_timestamp_columns_have_database_defaults(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic_photoshop_timestamps.sqlite3"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.setattr(config_module.settings, "DATABASE_URL", database_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    command.upgrade(config, "heads")

    sync_engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    inspector = sa.inspect(sync_engine)
    columns = {column["name"]: column for column in inspector.get_columns("photoshop_edit_jobs")}

    assert columns["created_at"]["default"] is not None
    assert columns["updated_at"]["default"] is not None


def test_generation_tasks_project_id_is_nullable_after_upgrade_heads(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic_generation_tasks_nullable.sqlite3"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.setattr(config_module.settings, "DATABASE_URL", database_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    command.upgrade(config, "heads")

    sync_engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    inspector = sa.inspect(sync_engine)
    columns = {column["name"]: column for column in inspector.get_columns("generation_tasks")}

    assert columns["project_id"]["nullable"] is True


def test_generation_tasks_and_project_assets_include_runtime_hardening_columns(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic_runtime_hardening.sqlite3"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.setattr(config_module.settings, "DATABASE_URL", database_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    command.upgrade(config, "heads")

    sync_engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    inspector = sa.inspect(sync_engine)
    generation_columns = {column["name"]: column for column in inspector.get_columns("generation_tasks")}
    asset_columns = {column["name"]: column for column in inspector.get_columns("project_assets")}

    assert {
        "scheduler_claim_token",
        "scheduler_claimed_at",
        "scheduler_lease_expires_at",
        "scheduler_next_run_at",
        "scheduler_attempt_count",
        "terminalized_at",
        "terminal_side_effects_finalized_at",
        "workflow_stage",
        "last_error_type",
    }.issubset(generation_columns)
    assert not {"poller_claim_token", "poller_claimed_at", "poller_lease_expires_at"} & set(generation_columns)
    assert asset_columns["origin_kind"]["default"] is None


def test_agent_workflow_vnext_downgrade_restores_legacy_runtime_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic_agent_workflow_vnext_downgrade.sqlite3"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.setattr(config_module.settings, "DATABASE_URL", database_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    command.upgrade(config, "202605280001")
    command.downgrade(config, "202605270002")

    sync_engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    inspector = sa.inspect(sync_engine)
    table_names = set(inspector.get_table_names())

    assert "harness_runtime" in table_names
    assert "harness_agent_run_requests" in table_names
    assert "harness_agent_runs" not in table_names
    assert "harness_agent_steps" not in table_names

    runtime_columns = {column["name"] for column in inspector.get_columns("harness_runtime")}
    request_columns = {column["name"] for column in inspector.get_columns("harness_agent_run_requests")}
    assert {"conversation_id", "user_interaction_json", "runtime_state_json"} <= runtime_columns
    assert not {"run_id", "cancel_requested", "parent_usage_log_id"} & runtime_columns
    assert {"run_id", "conversation_id", "payload_json", "claim_expires_at"} <= request_columns


def test_generation_task_artifact_ref_migration_backfills_existing_params(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic_generation_task_artifact_ref.sqlite3"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.setattr(config_module.settings, "DATABASE_URL", database_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    command.upgrade(config, "202605280001")

    sync_engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    with sync_engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO users (id, email, username, hashed_password, role, is_active)
                VALUES (1002, 'artifact-ref@example.test', 'artifact-ref', 'hashed', 'user', 1)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO generation_tasks (
                    id, user_id, project_id, task_type, provider_code, model_name,
                    model_label, prompt, status, params
                )
                VALUES (
                    2002, 1002, NULL, 'text2image', 'builtin', 'seedream',
                    'Seedream', 'blue banana', 'processing',
                    '{"artifact_ref": "artifact_ref:legacy-image"}'
                )
                """
            )
        )

    command.upgrade(config, "heads")

    with sync_engine.connect() as connection:
        artifact_ref = connection.execute(
            sa.text("SELECT artifact_ref FROM generation_tasks WHERE id = 2002")
        ).scalar_one()

    assert artifact_ref == "artifact_ref:legacy-image"


def test_reference_gallery_taxonomy_migration_backfills_existing_image_category(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic_reference_gallery_taxonomy.sqlite3"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.setattr(config_module.settings, "DATABASE_URL", database_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    command.upgrade(config, "202606220001")

    sync_engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    with sync_engine.begin() as connection:
        user_id = connection.execute(
            sa.text("SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1")
        ).scalar_one()
        category_id = connection.execute(
            sa.text("SELECT id FROM reference_categories WHERE name = '衬衫'")
        ).scalar_one()
        subcategory_id = connection.execute(
            sa.text(
                """
                SELECT id FROM reference_subcategories
                WHERE category_id = :category_id
                ORDER BY id LIMIT 1
                """
            ),
            {"category_id": category_id},
        ).scalar_one()
        connection.execute(
            sa.text(
                """
                INSERT INTO reference_images (created_by, subcategory_id, url, name)
                VALUES (:created_by, :subcategory_id, :url, :name)
                """
            ),
            {
                "created_by": user_id,
                "subcategory_id": subcategory_id,
                "url": "/api/v1/uploads/reference-gallery/2026-06/legacy.png",
                "name": "legacy.png",
            },
        )

    command.upgrade(config, "heads")

    inspector = sa.inspect(sync_engine)
    assert "reference_taxonomies" in inspector.get_table_names()
    assert "reference_subcategories" not in inspector.get_table_names()
    image_columns = {column["name"] for column in inspector.get_columns("reference_images")}
    assert "subcategory_id" not in image_columns
    assert {"category_id", "style_id", "classification_id"} <= image_columns

    with sync_engine.connect() as connection:
        row = connection.execute(
            sa.text(
                """
                SELECT i.name, t.name AS category_name, t.kind
                FROM reference_images i
                JOIN reference_taxonomies t ON t.id = i.category_id
                WHERE i.name = 'legacy.png'
                """
            )
        ).mappings().one()

    assert row["category_name"] == "衬衫"
    assert row["kind"] == "category"


def test_generation_task_scheduler_migration_preserves_existing_poller_claim_data(tmp_path, monkeypatch):
    db_path = tmp_path / "alembic_generation_task_claim_rename.sqlite3"
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.setattr(config_module.settings, "DATABASE_URL", database_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

    command.upgrade(config, "202605180003")

    sync_engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    with sync_engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO users (id, email, username, hashed_password, role, is_active)
                VALUES (1001, 'claim-rename@example.test', 'claim-rename', 'hashed', 'user', 1)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO generation_tasks (
                    id, user_id, project_id, task_type, provider_code, model_name,
                    model_label, prompt, status, external_task_id,
                    poller_claim_token, poller_claimed_at, poller_lease_expires_at
                )
                VALUES (
                    2001, 1001, NULL, 'text2image', 'builtin', 'seedream',
                    'Seedream', 'blue banana', 'processing', 'provider-task-1',
                    'legacy-claim-token', '2026-05-18 10:00:00', '2026-05-18 10:01:00'
                )
                """
            )
        )

    command.upgrade(config, "heads")

    with sync_engine.connect() as connection:
        row = connection.execute(
            sa.text(
                """
                SELECT scheduler_claim_token, scheduler_claimed_at, scheduler_lease_expires_at
                FROM generation_tasks
                WHERE id = 2001
                """
            )
        ).mappings().one()

    assert row["scheduler_claim_token"] == "legacy-claim-token"
    assert "2026-05-18 10:00:00" in str(row["scheduler_claimed_at"])
    assert "2026-05-18 10:01:00" in str(row["scheduler_lease_expires_at"])
