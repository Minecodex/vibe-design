from app.services.agent_harness import catalog
from app.services.agent_harness.capabilities.design_systems.resolver_registry import (
    clear_design_system_resolver_registry_cache,
    list_design_system_resolver_metadata,
)


def test_list_design_system_resolver_metadata_reads_design_system_catalog(monkeypatch):
    monkeypatch.setattr(catalog, "_LOCAL_DESIGN_SYSTEM_SNAPSHOT", catalog.build_design_system_summary_snapshot())
    clear_design_system_resolver_registry_cache()

    metadata = list_design_system_resolver_metadata()

    assert metadata
    assert any(item.id == "default" for item in metadata)
