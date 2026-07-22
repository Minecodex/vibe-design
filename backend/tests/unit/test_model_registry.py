import importlib

from app.db.base import Base


def test_models_package_import_registers_current_metadata_tables():
    importlib.import_module("app.models")

    expected_tables = {
        "generation_tasks",
        "photoshop_edit_jobs",
        "project_assets",
        "project_members",
        "project_user_canvases",
        "projects",
        "provider_credentials",
        "provider_models",
        "license_records",
        "usage_logs",
        "user_asset_favorites",
        "user_providers",
        "users",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())
    assert "redemption_logs" not in Base.metadata.tables
