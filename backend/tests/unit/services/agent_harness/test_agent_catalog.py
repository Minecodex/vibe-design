from __future__ import annotations

import gzip
import json

import pytest

from app.core.redis_coordination import RedisKeyBuilder
from app.services.agent_harness import catalog
from app.services.agent_harness.catalog import (
    CatalogSnapshot,
    DesignSystemSummary,
    SkillSummary,
)


@pytest.fixture(autouse=True)
def reset_catalog_cache(monkeypatch):
    monkeypatch.setattr(catalog, "_LOCAL_SKILL_SNAPSHOT", None)
    monkeypatch.setattr(catalog, "_LOCAL_DESIGN_SYSTEM_SNAPSHOT", None)


def _skill(skill_id: str = "web") -> SkillSummary:
    return SkillSummary(
        id=skill_id,
        name="Web",
        name_en="Web",
        name_zh="网页",
        description="Build web artifacts.",
        description_en="Build web artifacts.",
        description_zh="构建网页。",
        icon="globe",
        color="blue",
        triggers=["web"],
        mode="prototype",
        surface="web",
        platform=None,
        scenario=None,
        artifact_mode="web",
        default_for=[],
        featured=1,
        preview_type="html",
        preview_entry=None,
        primary_output=None,
        parameters=[],
        outputs_secondary=[],
        metadata_health={},
        protocol_provider="open_design",
        protocol_family="open_design_free_web",
        protocol_metadata={},
        capabilities={"selection_enabled": True, "phase_enabled": True},
        example_prompt=None,
        has_example_html=False,
    )


def _design(system_id: str = "default") -> DesignSystemSummary:
    return DesignSystemSummary(
        id=system_id,
        title="Default",
        description="Balanced default.",
        category="Product & SaaS",
        sections=["Color"],
        palette=["#FFFFFF", "#111827"],
        preview=None,
        featured=1,
        is_default=True,
        resolver_summary="Balanced default design system.",
        resolver_tags=["balanced"],
        preferred_for=["product-page"],
        avoid_for=[],
        tone="professional",
        density="balanced",
    )


class _FakeCoordinator:
    def __init__(self):
        self.keys = RedisKeyBuilder(namespace="test")
        self.blobs: dict[str, bytes] = {}
        self.get_blob_calls: list[str] = []
        self.lease_acquired = True
        self.leases: list[str] = []

    async def health(self):
        return {"status": "healthy", "enabled": True}

    async def set_blob(self, key, value, *, ttl_seconds, max_bytes):
        del ttl_seconds
        assert len(value) <= max_bytes
        self.blobs[str(key)] = bytes(value)

    async def set_blobs(self, values, *, ttl_seconds, max_bytes):
        del ttl_seconds
        payloads = {str(key): bytes(value) for key, value in dict(values).items()}
        assert all(len(value) <= max_bytes for value in payloads.values())
        self.blobs.update(payloads)

    async def get_blob(self, key, *, max_bytes):
        self.get_blob_calls.append(str(key))
        value = self.blobs.get(str(key))
        assert value is None or len(value) <= max_bytes
        return value

    async def delete_key(self, key):
        return int(self.blobs.pop(str(key), None) is not None)

    async def try_acquire_lease(self, key, *, owner, ttl_seconds):
        del key, ttl_seconds
        self.leases.append(owner)
        return {"acquired": self.lease_acquired, "owner": owner if self.lease_acquired else "other"}

    async def release_lease(self, key, *, owner):
        del key, owner
        return True


@pytest.mark.asyncio
async def test_backend_warmup_writes_skill_and_design_summaries(monkeypatch):
    fake = _FakeCoordinator()
    monkeypatch.setattr(catalog, "get_redis_coordinator", lambda: fake)
    monkeypatch.setattr(
        catalog,
        "build_skill_summary_snapshot",
        lambda: CatalogSnapshot(kind="skills", source_digest="skill-digest", generated_at=1, items=[_skill()]),
    )
    monkeypatch.setattr(
        catalog,
        "build_design_system_summary_snapshot",
        lambda: CatalogSnapshot(kind="design-systems", source_digest="design-digest", generated_at=1, items=[_design()]),
    )

    await catalog.warmup_agent_catalog()

    skills = await catalog.read_skill_summaries()
    design_systems = await catalog.read_design_system_summaries()
    assert [skill.id for skill in skills] == ["web"]
    assert [system.id for system in design_systems] == ["default"]
    assert len(fake.blobs) == 3


@pytest.mark.asyncio
async def test_read_path_only_reads_redis_and_does_not_build(monkeypatch):
    fake = _FakeCoordinator()
    monkeypatch.setattr(catalog, "get_redis_coordinator", lambda: fake)
    monkeypatch.setattr(
        catalog,
        "build_skill_summary_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("read path must not build")),
    )
    monkeypatch.setattr(
        catalog,
        "build_design_system_summary_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("read path must not build")),
    )
    skill_snapshot = CatalogSnapshot(kind="skills", source_digest="s", generated_at=1, items=[_skill()])
    design_snapshot = CatalogSnapshot(kind="design-systems", source_digest="d", generated_at=1, items=[_design()])
    await catalog._write_snapshot(skill_snapshot)
    await catalog._write_snapshot(design_snapshot)
    await catalog._write_manifest(skill_snapshot, design_snapshot)

    assert [skill.id for skill in await catalog.read_skill_summaries()] == ["web"]
    assert [system.id for system in await catalog.read_design_system_summaries()] == ["default"]


@pytest.mark.asyncio
async def test_read_path_refreshes_stale_local_snapshot_from_redis(monkeypatch):
    fake = _FakeCoordinator()
    monkeypatch.setattr(catalog, "get_redis_coordinator", lambda: fake)
    catalog._LOCAL_SKILL_SNAPSHOT = CatalogSnapshot(
        kind="skills",
        source_digest="stale",
        generated_at=1,
        items=[_skill("stale")],
    )
    skill_snapshot = CatalogSnapshot(kind="skills", source_digest="redis", generated_at=2, items=[_skill("redis")])
    design_snapshot = CatalogSnapshot(kind="design-systems", source_digest="d", generated_at=1, items=[_design()])
    await catalog._write_snapshot(skill_snapshot)
    await catalog._write_manifest(skill_snapshot, design_snapshot)

    skills = await catalog.read_skill_summaries()

    assert [skill.id for skill in skills] == ["redis"]
    assert catalog._LOCAL_SKILL_SNAPSHOT is not None
    assert catalog._LOCAL_SKILL_SNAPSHOT.source_digest == "redis"
    assert fake.get_blob_calls


@pytest.mark.asyncio
async def test_catalog_response_requires_redis_even_with_local_snapshot(monkeypatch):
    fake = _FakeCoordinator()
    monkeypatch.setattr(catalog, "get_redis_coordinator", lambda: fake)
    catalog._LOCAL_SKILL_SNAPSHOT = CatalogSnapshot(
        kind="skills",
        source_digest="stale",
        generated_at=1,
        items=[_skill("stale")],
    )

    with pytest.raises(catalog.AgentCatalogUnavailableError, match="agent catalog manifest missing"):
        await catalog.skill_catalog_response()


@pytest.mark.asyncio
async def test_backend_warmup_waits_when_another_worker_holds_lease(monkeypatch):
    fake = _FakeCoordinator()
    fake.lease_acquired = False
    monkeypatch.setattr(catalog, "get_redis_coordinator", lambda: fake)
    monkeypatch.setattr(
        catalog,
        "build_skill_summary_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("non-lease holder must not build")),
    )
    monkeypatch.setattr(
        catalog,
        "build_design_system_summary_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("non-lease holder must not build")),
    )
    skill_snapshot = CatalogSnapshot(kind="skills", source_digest="s", generated_at=1, items=[_skill()])
    design_snapshot = CatalogSnapshot(kind="design-systems", source_digest="d", generated_at=1, items=[_design()])
    await catalog._write_snapshot(skill_snapshot)
    await catalog._write_snapshot(design_snapshot)
    await catalog._write_manifest(skill_snapshot, design_snapshot)

    await catalog.warmup_agent_catalog()

    assert len(fake.leases) == 1
    assert [skill.id for skill in catalog.list_skill_summaries_sync()] == ["web"]


@pytest.mark.asyncio
async def test_schema_version_miss_fails_without_building(monkeypatch):
    fake = _FakeCoordinator()
    monkeypatch.setattr(catalog, "get_redis_coordinator", lambda: fake)
    monkeypatch.setattr(
        catalog,
        "build_skill_summary_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("read path must not build")),
    )
    await catalog._write_manifest(
        CatalogSnapshot(kind="skills", source_digest="old", generated_at=1, items=[_skill()]),
        CatalogSnapshot(kind="design-systems", source_digest="d", generated_at=1, items=[_design()]),
    )
    fake.blobs[catalog._catalog_key("skills")] = gzip.compress(
        json.dumps(
            {
                "schema_version": 0,
                "kind": "skills",
                "source_digest": "old",
                "generated_at": 1,
                "items": [_skill().to_payload()],
            },
            ensure_ascii=False,
        ).encode("utf-8")
    )

    with pytest.raises(catalog.AgentCatalogUnavailableError, match="skill catalog missing"):
        await catalog.read_skill_summaries()


@pytest.mark.asyncio
async def test_digest_mismatch_fails_without_building(monkeypatch):
    fake = _FakeCoordinator()
    monkeypatch.setattr(catalog, "get_redis_coordinator", lambda: fake)
    monkeypatch.setattr(
        catalog,
        "build_skill_summary_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("read path must not build")),
    )
    actual_skill_snapshot = CatalogSnapshot(
        kind="skills",
        source_digest="actual",
        generated_at=1,
        items=[_skill()],
    )
    manifest_skill_snapshot = CatalogSnapshot(
        kind="skills",
        source_digest="expected",
        generated_at=1,
        items=[_skill()],
    )
    design_snapshot = CatalogSnapshot(kind="design-systems", source_digest="d", generated_at=1, items=[_design()])
    await catalog._write_snapshot(actual_skill_snapshot)
    await catalog._write_manifest(manifest_skill_snapshot, design_snapshot)

    with pytest.raises(catalog.AgentCatalogUnavailableError, match="digest mismatch"):
        await catalog.read_skill_summaries()


@pytest.mark.asyncio
async def test_design_system_public_response_omits_resolver_fields(monkeypatch):
    fake = _FakeCoordinator()
    monkeypatch.setattr(catalog, "get_redis_coordinator", lambda: fake)
    skill_snapshot = CatalogSnapshot(kind="skills", source_digest="s", generated_at=1, items=[_skill()])
    design_snapshot = CatalogSnapshot(kind="design-systems", source_digest="d", generated_at=1, items=[_design()])
    await catalog._write_snapshot(design_snapshot)
    await catalog._write_manifest(skill_snapshot, design_snapshot)

    body, etag = await catalog.design_system_catalog_response()

    assert etag == "d"
    payload = json.loads(body.decode("utf-8"))
    assert payload[0]["id"] == "default"
    assert "resolver_summary" not in payload[0]
    assert "preferred_for" not in payload[0]


@pytest.mark.asyncio
async def test_wait_catalog_ready_fails_on_redis_miss(monkeypatch):
    fake = _FakeCoordinator()
    monkeypatch.setattr(catalog, "get_redis_coordinator", lambda: fake)

    with pytest.raises(catalog.AgentCatalogUnavailableError):
        await catalog.wait_agent_catalog_ready(timeout_seconds=0.01)


def test_invalidate_agent_catalog_cache_refreshes_without_deleting(monkeypatch):
    calls: list[str] = []
    catalog._LOCAL_SKILL_SNAPSHOT = CatalogSnapshot(
        kind="skills",
        source_digest="stale",
        generated_at=1,
        items=[_skill()],
    )

    async def _warmup():
        calls.append("warmup")

    monkeypatch.setattr(catalog, "warmup_agent_catalog", _warmup)

    catalog.invalidate_agent_catalog_cache_sync()

    assert calls == ["warmup"]
    assert catalog._LOCAL_SKILL_SNAPSHOT is None


def test_summary_builders_do_not_load_full_catalogs():
    import app.services.agent_harness.capabilities.design_systems as design_systems_pkg
    import app.services.agent_harness.capabilities.skills as skills_pkg

    skills_pkg.SKILLS = None
    design_systems_pkg.DESIGN_SYSTEMS = None

    skill_snapshot = catalog.build_skill_summary_snapshot()
    design_snapshot = catalog.build_design_system_summary_snapshot()

    assert skills_pkg.SKILLS is None
    assert design_systems_pkg.DESIGN_SYSTEMS is None
    assert skill_snapshot.items
    assert design_snapshot.items
    assert all("system_prompt" not in item.to_payload() for item in skill_snapshot.items)
    assert all("body" not in item.to_payload() for item in design_snapshot.items)
