from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

from app.core.config import settings
from app.core.redis_coordination import get_redis_coordinator

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_SKILLS_KIND = "skills"
_DESIGN_SYSTEMS_KIND = "design-systems"
_MANIFEST_KIND = "agent-catalog-manifest"
_LOCAL_SKILL_SNAPSHOT: CatalogSnapshot[SkillSummary] | None = None
_LOCAL_DESIGN_SYSTEM_SNAPSHOT: CatalogSnapshot[DesignSystemSummary] | None = None


class AgentCatalogUnavailableError(RuntimeError):
    """Raised when the shared Redis agent catalog cannot be read."""


class AgentCatalogAssetNotFoundError(FileNotFoundError):
    """Raised when a validated catalog asset is missing on disk."""


@dataclass(slots=True, frozen=True)
class CatalogSnapshot[T]:
    kind: str
    source_digest: str
    generated_at: int
    items: list[T]


@dataclass(slots=True, frozen=True)
class SkillSummary:
    id: str
    name: str
    name_en: str
    name_zh: str | None
    description: str
    description_en: str | None
    description_zh: str | None
    icon: str
    color: str
    triggers: list[str]
    mode: str
    surface: str | None
    platform: str | None
    scenario: str | None
    artifact_mode: str | None
    default_for: list[str]
    featured: int | None
    preview_type: str
    preview_entry: str | None
    primary_output: str | None
    parameters: list[dict[str, Any]]
    outputs_secondary: list[dict[str, Any] | str]
    metadata_health: dict[str, Any]
    protocol_provider: str | None
    protocol_family: str | None
    protocol_metadata: dict[str, Any]
    capabilities: dict[str, Any]
    example_prompt: str | None
    has_example_html: bool

    @property
    def runtime_capabilities(self) -> dict[str, Any]:
        return self.capabilities

    def to_payload(self) -> dict[str, Any]:
        return _dataclass_payload(self)


@dataclass(slots=True, frozen=True)
class DesignSystemSummary:
    id: str
    title: str
    description: str
    category: str | None
    sections: list[str]
    palette: list[str]
    preview: str | None
    featured: int | None
    is_default: bool
    resolver_summary: str
    resolver_tags: list[str]
    preferred_for: list[str]
    avoid_for: list[str]
    tone: str
    density: str
    import_mode: str | None = None
    health: dict[str, Any] | None = None
    source_digest: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return _dataclass_payload(self)

    def to_public_payload(self) -> dict[str, Any]:
        payload = _dataclass_payload(self)
        for field in ("resolver_summary", "resolver_tags", "preferred_for", "avoid_for", "tone", "density", "source_digest"):
            payload.pop(field, None)
        return payload


def _dataclass_payload(item: Any) -> dict[str, Any]:
    return {
        field: getattr(item, field)
        for field in getattr(item, "__dataclass_fields__", {})
        if not field.startswith("_")
    }


def _snapshot_payload(snapshot: CatalogSnapshot[Any]) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "kind": snapshot.kind,
        "source_digest": snapshot.source_digest,
        "generated_at": snapshot.generated_at,
        "items": [item.to_payload() if hasattr(item, "to_payload") else dict(item) for item in snapshot.items],
    }


def _gzip_json_bytes(payload: dict[str, Any]) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw, compresslevel=6)


def _manifest_payload(
    skills: CatalogSnapshot[SkillSummary],
    design_systems: CatalogSnapshot[DesignSystemSummary],
) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "kind": _MANIFEST_KIND,
        "generated_at": int(time.time()),
        "snapshots": {
            _SKILLS_KIND: {
                "source_digest": skills.source_digest,
                "generated_at": skills.generated_at,
            },
            _DESIGN_SYSTEMS_KIND: {
                "source_digest": design_systems.source_digest,
                "generated_at": design_systems.generated_at,
            },
        },
    }


def _snapshot_json_bytes(snapshot: CatalogSnapshot[Any]) -> bytes:
    return json.dumps(
        [item.to_payload() if hasattr(item, "to_payload") else dict(item) for item in snapshot.items],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _catalog_key(kind: str) -> str:
    coordinator = get_redis_coordinator()
    purpose = "skills-summary-v1" if kind == _SKILLS_KIND else "design-systems-summary-v1"
    return coordinator.keys.build(domain="agent-catalog", purpose=purpose)


def _manifest_key() -> str:
    return get_redis_coordinator().keys.build(domain="agent-catalog", purpose="manifest-v1")


def _lease_key() -> str:
    return get_redis_coordinator().keys.build(domain="agent-catalog", purpose="warmup-lease-v1")


def _skills_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "capabilities" / "skills"


def _design_systems_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "capabilities" / "design_systems"


def _catalog_item_dir(root: Path, item_id: str) -> Path:
    root_path = root.resolve()
    item_path = (root_path / str(item_id or "").strip()).resolve()
    try:
        item_path.relative_to(root_path)
    except ValueError as exc:
        raise AgentCatalogAssetNotFoundError("catalog asset not found") from exc
    if not item_path.is_dir():
        raise AgentCatalogAssetNotFoundError("catalog asset not found")
    return item_path


def _catalog_file_path(root: Path, item_id: str, relative_path: str) -> Path:
    item_path = _catalog_item_dir(root, item_id)
    requested = Path(str(relative_path or "").replace("\\", "/").lstrip("/"))
    if requested.is_absolute():
        raise AgentCatalogAssetNotFoundError("catalog asset not found")
    file_path = (item_path / requested).resolve()
    try:
        file_path.relative_to(item_path)
    except ValueError as exc:
        raise AgentCatalogAssetNotFoundError("catalog asset not found") from exc
    if not file_path.is_file():
        raise AgentCatalogAssetNotFoundError("catalog asset not found")
    return file_path


async def _require_redis_healthy() -> None:
    health = await get_redis_coordinator().health()
    if health.get("status") != "healthy" or health.get("enabled") is not True:
        raise AgentCatalogUnavailableError(f"redis catalog unavailable: {health.get('status') or health.get('reason')}")


async def _write_snapshot(snapshot: CatalogSnapshot[Any]) -> None:
    await _require_redis_healthy()
    await get_redis_coordinator().set_blob(
        _catalog_key(snapshot.kind),
        _gzip_json_bytes(_snapshot_payload(snapshot)),
        ttl_seconds=float(settings.AGENT_CATALOG_CACHE_TTL_SECONDS),
        max_bytes=int(settings.REDIS_CATALOG_MAX_PAYLOAD_BYTES),
    )


async def _write_manifest(
    skills: CatalogSnapshot[SkillSummary],
    design_systems: CatalogSnapshot[DesignSystemSummary],
) -> None:
    await _require_redis_healthy()
    await get_redis_coordinator().set_blob(
        _manifest_key(),
        _gzip_json_bytes(_manifest_payload(skills, design_systems)),
        ttl_seconds=float(settings.AGENT_CATALOG_CACHE_TTL_SECONDS),
        max_bytes=int(settings.REDIS_CATALOG_MAX_PAYLOAD_BYTES),
    )


async def _write_catalog(
    skills: CatalogSnapshot[SkillSummary],
    design_systems: CatalogSnapshot[DesignSystemSummary],
) -> None:
    await _require_redis_healthy()
    await get_redis_coordinator().set_blobs(
        {
            _catalog_key(_SKILLS_KIND): _gzip_json_bytes(_snapshot_payload(skills)),
            _catalog_key(_DESIGN_SYSTEMS_KIND): _gzip_json_bytes(_snapshot_payload(design_systems)),
            _manifest_key(): _gzip_json_bytes(_manifest_payload(skills, design_systems)),
        },
        ttl_seconds=float(settings.AGENT_CATALOG_CACHE_TTL_SECONDS),
        max_bytes=int(settings.REDIS_CATALOG_MAX_PAYLOAD_BYTES),
    )


async def _read_manifest() -> dict[str, Any] | None:
    await _require_redis_healthy()
    compressed = await get_redis_coordinator().get_blob(
        _manifest_key(),
        max_bytes=int(settings.REDIS_CATALOG_MAX_PAYLOAD_BYTES),
    )
    if compressed is None:
        return None
    try:
        payload = json.loads(gzip.decompress(compressed).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AgentCatalogUnavailableError("invalid redis catalog manifest payload") from exc
    if not isinstance(payload, dict):
        raise AgentCatalogUnavailableError("invalid redis catalog manifest envelope")
    if int(payload.get("schema_version") or 0) != _SCHEMA_VERSION:
        return None
    if str(payload.get("kind") or "") != _MANIFEST_KIND:
        raise AgentCatalogUnavailableError("redis catalog manifest kind mismatch")
    if not isinstance(payload.get("snapshots"), dict):
        raise AgentCatalogUnavailableError("invalid redis catalog manifest snapshots")
    return payload


def _expected_manifest_digest(manifest: dict[str, Any], kind: Literal["skills", "design-systems"]) -> str:
    snapshots = manifest.get("snapshots") if isinstance(manifest.get("snapshots"), dict) else {}
    snapshot_meta = snapshots.get(kind) if isinstance(snapshots, dict) else None
    if not isinstance(snapshot_meta, dict):
        raise AgentCatalogUnavailableError(f"redis catalog manifest missing snapshot: {kind}")
    digest = str(snapshot_meta.get("source_digest") or "").strip()
    if not digest:
        raise AgentCatalogUnavailableError(f"redis catalog manifest missing digest: {kind}")
    return digest


async def _read_manifest_required() -> dict[str, Any]:
    manifest = await _read_manifest()
    if manifest is None:
        raise AgentCatalogUnavailableError("agent catalog manifest missing")
    return manifest


async def _read_snapshot(
    kind: Literal["skills", "design-systems"],
    *,
    expected_source_digest: str | None = None,
) -> dict[str, Any] | None:
    await _require_redis_healthy()
    compressed = await get_redis_coordinator().get_blob(
        _catalog_key(kind),
        max_bytes=int(settings.REDIS_CATALOG_MAX_PAYLOAD_BYTES),
    )
    if compressed is None:
        return None
    try:
        payload = json.loads(gzip.decompress(compressed).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AgentCatalogUnavailableError(f"invalid redis catalog payload: {kind}") from exc
    if not isinstance(payload, dict):
        raise AgentCatalogUnavailableError(f"invalid redis catalog envelope: {kind}")
    if int(payload.get("schema_version") or 0) != _SCHEMA_VERSION:
        return None
    if str(payload.get("kind") or "") != kind:
        raise AgentCatalogUnavailableError(f"redis catalog kind mismatch: {kind}")
    source_digest = str(payload.get("source_digest") or "").strip()
    if not source_digest:
        raise AgentCatalogUnavailableError(f"redis catalog source digest missing: {kind}")
    if expected_source_digest is not None and source_digest != str(expected_source_digest):
        raise AgentCatalogUnavailableError(f"redis catalog digest mismatch: {kind}")
    if not isinstance(payload.get("items"), list):
        raise AgentCatalogUnavailableError(f"invalid redis catalog items: {kind}")
    return payload


def _skill_snapshot_from_payload(payload: dict[str, Any]) -> CatalogSnapshot[SkillSummary]:
    return CatalogSnapshot(
        kind=_SKILLS_KIND,
        source_digest=str(payload.get("source_digest") or ""),
        generated_at=int(payload.get("generated_at") or 0),
        items=[SkillSummary(**dict(item)) for item in payload.get("items") or [] if isinstance(item, dict)],
    )


def _design_snapshot_from_payload(payload: dict[str, Any]) -> CatalogSnapshot[DesignSystemSummary]:
    return CatalogSnapshot(
        kind=_DESIGN_SYSTEMS_KIND,
        source_digest=str(payload.get("source_digest") or ""),
        generated_at=int(payload.get("generated_at") or 0),
        items=[
            DesignSystemSummary(**dict(item))
            for item in payload.get("items") or []
            if isinstance(item, dict)
        ],
    )


async def warmup_agent_catalog() -> None:
    """Backend-only producer entrypoint: build summaries and publish them to Redis."""

    started = time.perf_counter()
    logger.debug("Agent catalog warmup begin: pid=%s", os.getpid())
    await _require_redis_healthy()
    logger.debug(
        "Agent catalog warmup redis healthy: pid=%s elapsed_ms=%.3f",
        os.getpid(),
        (time.perf_counter() - started) * 1000,
    )
    owner = f"backend:{uuid.uuid4()}"
    lease_started = time.perf_counter()
    lease = await get_redis_coordinator().try_acquire_lease(
        _lease_key(),
        owner=owner,
        ttl_seconds=max(float(settings.AGENT_CATALOG_READY_WAIT_SECONDS) * 2.0, 30.0),
    )
    logger.debug(
        "Agent catalog warmup lease result: pid=%s acquired=%s elapsed_ms=%.3f total_ms=%.3f",
        os.getpid(),
        bool(lease.get("acquired")),
        (time.perf_counter() - lease_started) * 1000,
        (time.perf_counter() - started) * 1000,
    )
    if not lease.get("acquired"):
        wait_started = time.perf_counter()
        await wait_agent_catalog_ready(timeout_seconds=float(settings.AGENT_CATALOG_READY_WAIT_SECONDS))
        logger.debug(
            "Agent catalog warmup waited for existing snapshot: pid=%s wait_ms=%.3f total_ms=%.3f",
            os.getpid(),
            (time.perf_counter() - wait_started) * 1000,
            (time.perf_counter() - started) * 1000,
        )
        return
    try:
        skill_started = time.perf_counter()
        skill_snapshot = build_skill_summary_snapshot()
        logger.debug(
            "Agent catalog warmup skills built: pid=%s skills=%s elapsed_ms=%.3f total_ms=%.3f",
            os.getpid(),
            len(skill_snapshot.items),
            (time.perf_counter() - skill_started) * 1000,
            (time.perf_counter() - started) * 1000,
        )
        design_started = time.perf_counter()
        design_snapshot = build_design_system_summary_snapshot()
        logger.debug(
            "Agent catalog warmup design systems built: pid=%s design_systems=%s elapsed_ms=%.3f total_ms=%.3f",
            os.getpid(),
            len(design_snapshot.items),
            (time.perf_counter() - design_started) * 1000,
            (time.perf_counter() - started) * 1000,
        )
        write_started = time.perf_counter()
        await _write_catalog(skill_snapshot, design_snapshot)
        logger.debug(
            "Agent catalog warmup redis write completed: pid=%s elapsed_ms=%.3f total_ms=%.3f",
            os.getpid(),
            (time.perf_counter() - write_started) * 1000,
            (time.perf_counter() - started) * 1000,
        )
        _set_local_snapshots(skill_snapshot, design_snapshot)
        logger.debug(
            "Agent catalog warmed: pid=%s skills=%s design_systems=%s total_ms=%.3f",
            os.getpid(),
            len(skill_snapshot.items),
            len(design_snapshot.items),
            (time.perf_counter() - started) * 1000,
        )
    finally:
        release_started = time.perf_counter()
        await get_redis_coordinator().release_lease(_lease_key(), owner=owner)
        logger.debug(
            "Agent catalog warmup lease released: pid=%s elapsed_ms=%.3f total_ms=%.3f",
            os.getpid(),
            (time.perf_counter() - release_started) * 1000,
            (time.perf_counter() - started) * 1000,
        )


async def wait_agent_catalog_ready(*, timeout_seconds: float | None = None) -> None:
    deadline = time.monotonic() + max(
        float(settings.AGENT_CATALOG_READY_WAIT_SECONDS if timeout_seconds is None else timeout_seconds),
        0.001,
    )
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            manifest = await _read_manifest()
            if manifest is None:
                await asyncio.sleep(0.2)
                continue
            skill_payload = await _read_snapshot(
                _SKILLS_KIND,
                expected_source_digest=_expected_manifest_digest(manifest, _SKILLS_KIND),
            )
            design_payload = await _read_snapshot(
                _DESIGN_SYSTEMS_KIND,
                expected_source_digest=_expected_manifest_digest(manifest, _DESIGN_SYSTEMS_KIND),
            )
            if skill_payload is not None and design_payload is not None:
                _set_local_snapshots(
                    _skill_snapshot_from_payload(skill_payload),
                    _design_snapshot_from_payload(design_payload),
                )
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        await asyncio.sleep(0.2)
    if last_error is not None:
        raise AgentCatalogUnavailableError("agent catalog not ready") from last_error
    raise AgentCatalogUnavailableError("agent catalog not ready")


def _set_local_snapshots(
    skills: CatalogSnapshot[SkillSummary],
    design_systems: CatalogSnapshot[DesignSystemSummary],
) -> None:
    global _LOCAL_SKILL_SNAPSHOT, _LOCAL_DESIGN_SYSTEM_SNAPSHOT
    _LOCAL_SKILL_SNAPSHOT = skills
    _LOCAL_DESIGN_SYSTEM_SNAPSHOT = design_systems


async def read_skill_summaries() -> list[SkillSummary]:
    snapshot = await _read_skill_snapshot_from_redis()
    return list(snapshot.items)


async def read_design_system_summaries() -> list[DesignSystemSummary]:
    snapshot = await _read_design_snapshot_from_redis()
    return list(snapshot.items)


async def agent_catalog_health() -> dict[str, Any]:
    try:
        manifest = await _read_manifest_required()
        skill_payload = await _read_snapshot(
            _SKILLS_KIND,
            expected_source_digest=_expected_manifest_digest(manifest, _SKILLS_KIND),
        )
        design_payload = await _read_snapshot(
            _DESIGN_SYSTEMS_KIND,
            expected_source_digest=_expected_manifest_digest(manifest, _DESIGN_SYSTEMS_KIND),
        )
        if skill_payload is None:
            raise AgentCatalogUnavailableError("skill catalog missing")
        if design_payload is None:
            raise AgentCatalogUnavailableError("design system catalog missing")
        return {
            "status": "ready",
            "schema_version": _SCHEMA_VERSION,
            "skills": {
                "source_digest": str(skill_payload.get("source_digest") or ""),
                "item_count": len(skill_payload.get("items") or []),
            },
            "design_systems": {
                "source_digest": str(design_payload.get("source_digest") or ""),
                "item_count": len(design_payload.get("items") or []),
            },
        }
    except AgentCatalogUnavailableError as exc:
        return {"status": "unavailable", "reason": str(exc)}


async def _read_skill_snapshot_from_redis() -> CatalogSnapshot[SkillSummary]:
    global _LOCAL_SKILL_SNAPSHOT
    manifest = await _read_manifest_required()
    payload = await _read_snapshot(
        _SKILLS_KIND,
        expected_source_digest=_expected_manifest_digest(manifest, _SKILLS_KIND),
    )
    if payload is None:
        raise AgentCatalogUnavailableError("skill catalog missing")
    _LOCAL_SKILL_SNAPSHOT = _skill_snapshot_from_payload(payload)
    return _LOCAL_SKILL_SNAPSHOT


async def _read_design_snapshot_from_redis() -> CatalogSnapshot[DesignSystemSummary]:
    global _LOCAL_DESIGN_SYSTEM_SNAPSHOT
    manifest = await _read_manifest_required()
    payload = await _read_snapshot(
        _DESIGN_SYSTEMS_KIND,
        expected_source_digest=_expected_manifest_digest(manifest, _DESIGN_SYSTEMS_KIND),
    )
    if payload is None:
        raise AgentCatalogUnavailableError("design system catalog missing")
    _LOCAL_DESIGN_SYSTEM_SNAPSHOT = _design_snapshot_from_payload(payload)
    return _LOCAL_DESIGN_SYSTEM_SNAPSHOT


def list_skill_summaries_sync() -> list[SkillSummary]:
    if _LOCAL_SKILL_SNAPSHOT is None:
        raise AgentCatalogUnavailableError("skill catalog not loaded")
    return list(_LOCAL_SKILL_SNAPSHOT.items)


def list_design_system_summaries_sync() -> list[DesignSystemSummary]:
    if _LOCAL_DESIGN_SYSTEM_SNAPSHOT is None:
        raise AgentCatalogUnavailableError("design system catalog not loaded")
    return list(_LOCAL_DESIGN_SYSTEM_SNAPSHOT.items)


async def get_skill_summary(skill_id: str | None) -> SkillSummary | None:
    from app.services.agent_harness.capabilities.skills.runtime_profiles import canonical_skill_id

    normalized = canonical_skill_id(skill_id)
    if not normalized:
        return None
    return next((item for item in await read_skill_summaries() if item.id == normalized), None)


def get_skill_summary_sync(skill_id: str | None) -> SkillSummary | None:
    from app.services.agent_harness.capabilities.skills.runtime_profiles import canonical_skill_id

    normalized = canonical_skill_id(skill_id)
    if not normalized:
        return None
    return next((item for item in list_skill_summaries_sync() if item.id == normalized), None)


async def get_design_system_summary(design_system_id: str | None) -> DesignSystemSummary | None:
    normalized = str(design_system_id or "").strip()
    if not normalized:
        return None
    return next((item for item in await read_design_system_summaries() if item.id == normalized), None)


def get_design_system_summary_sync(design_system_id: str | None) -> DesignSystemSummary | None:
    normalized = str(design_system_id or "").strip()
    if not normalized:
        return None
    return next((item for item in list_design_system_summaries_sync() if item.id == normalized), None)


def skill_example_html_path(skill_id: str | None) -> Path:
    summary = get_skill_summary_sync(skill_id)
    if summary is None:
        raise AgentCatalogAssetNotFoundError(f"Unknown harness skill: {skill_id}")
    if not summary.has_example_html:
        raise AgentCatalogAssetNotFoundError(f"No example HTML for harness skill: {summary.id}")
    return _catalog_file_path(_skills_dir(), summary.id, "example.html")


def skill_asset_file_path(skill_id: str | None, file_path: str) -> Path:
    summary = get_skill_summary_sync(skill_id)
    if summary is None:
        raise AgentCatalogAssetNotFoundError(f"Unknown harness skill: {skill_id}")
    return _catalog_file_path(_skills_dir(), summary.id, file_path)


def design_system_preview_html_path(design_system_id: str | None) -> Path:
    summary = get_design_system_summary_sync(design_system_id)
    if summary is None:
        raise AgentCatalogAssetNotFoundError(f"Unknown design system: {design_system_id}")
    return _catalog_file_path(_design_systems_dir(), summary.id, "components.html")


async def skill_catalog_response() -> tuple[bytes, str]:
    snapshot = await _read_skill_snapshot_from_redis()
    return _snapshot_json_bytes(snapshot), snapshot.source_digest


async def design_system_catalog_response() -> tuple[bytes, str]:
    snapshot = await _read_design_snapshot_from_redis()
    return (
        json.dumps(
            [item.to_public_payload() for item in snapshot.items],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"),
        snapshot.source_digest,
    )


async def delete_agent_catalog_cache() -> None:
    global _LOCAL_SKILL_SNAPSHOT, _LOCAL_DESIGN_SYSTEM_SNAPSHOT
    _LOCAL_SKILL_SNAPSHOT = None
    _LOCAL_DESIGN_SYSTEM_SNAPSHOT = None
    await get_redis_coordinator().delete_key(_catalog_key(_SKILLS_KIND))
    await get_redis_coordinator().delete_key(_catalog_key(_DESIGN_SYSTEMS_KIND))
    await get_redis_coordinator().delete_key(_manifest_key())


def invalidate_agent_catalog_cache_sync() -> None:
    global _LOCAL_SKILL_SNAPSHOT, _LOCAL_DESIGN_SYSTEM_SNAPSHOT
    _LOCAL_SKILL_SNAPSHOT = None
    _LOCAL_DESIGN_SYSTEM_SNAPSHOT = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            asyncio.run(warmup_agent_catalog())
        except Exception:
            logger.warning("Failed to refresh Redis agent catalog cache", exc_info=True)
        return
    loop.create_task(warmup_agent_catalog(), name="refresh-agent-catalog-cache")


def build_skill_summary_snapshot() -> CatalogSnapshot[SkillSummary]:
    from app.services.agent_harness.capabilities.skill_protocols.base import ProtocolRuntimeContext
    from app.services.agent_harness.capabilities.skill_protocols.builtin.adapter import (
        BuiltinProtocolAdapter,
    )
    from app.services.agent_harness.capabilities.skill_protocols.open_design.adapter import (
        OpenDesignProtocolAdapter,
    )
    from app.services.agent_harness.capabilities.skill_protocols.open_design.catalog import (
        derive_catalog_metadata,
    )
    from app.services.agent_harness.capabilities.skill_protocols.open_design.design_templates import (
        build_imported_template_metadata,
    )
    from app.services.agent_harness.capabilities.skills import (
        _coerce_list,
        _coerce_seed_assets,
        _detect_direction_definitions,
        _normalize_parameter_contracts,
    )
    from app.services.agent_harness.capabilities.skills.classification_registry import (
        classify_skill,
    )
    from app.services.agent_harness.capabilities.skills.markdown_parser import parse_skill_markdown

    skills_dir = _skills_dir()
    digest = hashlib.sha256()
    summaries: list[SkillSummary] = []
    open_design_adapter = OpenDesignProtocolAdapter()
    builtin_adapter = BuiltinProtocolAdapter()
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue
        try:
            text = skill_file.read_text(encoding="utf-8")
            parsed = parse_skill_markdown(text)
        except Exception:
            logger.warning("Failed to summarize skill %s", skill_dir.name, exc_info=True)
            continue
        digest.update(skill_dir.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(text.encode("utf-8"))

        meta = parsed.meta
        body = parsed.body
        od_meta = meta.get("od") if isinstance(meta.get("od"), dict) else {}
        preview_meta = od_meta.get("preview") if isinstance(od_meta.get("preview"), dict) else {}
        design_system_meta = od_meta.get("design_system") if isinstance(od_meta.get("design_system"), dict) else {}
        craft_meta = od_meta.get("craft") if isinstance(od_meta.get("craft"), dict) else {}
        preview_entry = str(preview_meta.get("entry") or meta.get("preview_entry") or "").strip() or None
        raw_outputs = meta.get("outputs") if isinstance(meta.get("outputs"), dict) else (
            od_meta.get("outputs") if isinstance(od_meta.get("outputs"), dict) else {}
        )
        primary_output = str(
            (raw_outputs.get("primary") if isinstance(raw_outputs, dict) else None)
            or preview_entry
            or ""
        ).strip() or None
        catalog_meta = derive_catalog_metadata(
            skill_id=skill_dir.name,
            skill_dir=skill_dir,
            raw_mode=od_meta.get("mode"),
            raw_surface=od_meta.get("surface"),
            description=str(meta.get("description", "")),
            body=body,
            preview_entry=preview_entry,
            primary_output=primary_output,
        )
        imported_template_meta = build_imported_template_metadata(skill_dir.name, skill_dir, body=body)
        classification = classify_skill(
            skill_id=skill_dir.name,
            artifact_mode=catalog_meta.artifact_mode,
            mode=catalog_meta.mode,
        )
        mode = classification.mode_override or catalog_meta.mode
        artifact_mode = classification.artifact_mode
        execution_strategy = catalog_meta.execution_strategy
        parameters = meta.get("parameters")
        if not isinstance(parameters, list | dict):
            parameters = od_meta.get("parameters")
        outputs = raw_outputs if isinstance(raw_outputs, dict) else {}
        seed_assets = _coerce_seed_assets(
            od_meta.get("seed_assets")
            if od_meta.get("seed_assets") is not None
            else meta.get("seed_assets")
        )
        runtime_capabilities = {
            **dict(catalog_meta.runtime_capabilities),
            **imported_template_meta.to_runtime_capabilities(),
            **classification.to_runtime_capabilities(),
        }
        skill_obj = SimpleNamespace(
            id=skill_dir.name,
            mode=mode,
            surface=str(od_meta.get("surface") or "").strip() or None,
            description=str(meta.get("description", "")),
            system_prompt=body,
            skill_dir=skill_dir.resolve(),
            execution_strategy=execution_strategy,
            runtime_capabilities=runtime_capabilities,
            preview_entry=preview_entry,
            primary_output=primary_output,
            seed_assets=seed_assets,
        )
        context = ProtocolRuntimeContext(artifact_mode=artifact_mode, project_kind=artifact_mode)
        adapter = open_design_adapter if open_design_adapter.can_handle(skill_obj, context) else builtin_adapter
        protocol = adapter.resolve(skill_obj, context)
        output_schema = outputs if isinstance(outputs, dict) else {}
        secondary = output_schema.get("secondary")
        outputs_secondary = list(secondary) if isinstance(secondary, list) else ([] if secondary is None else [secondary])
        protocol_metadata = {
            **dict(protocol.metadata or {}),
            "execution_strategy": execution_strategy,
            "directions": list(_detect_direction_definitions(skill_dir, meta, od_meta) or []),
            "seed_assets": list(seed_assets or []),
            "design_system": {
                "requires": bool(design_system_meta.get("requires", False)),
                "sections": _coerce_list(design_system_meta.get("sections")),
            },
            "craft": {"requires": _coerce_list(craft_meta.get("requires"))},
            "upstream": str(od_meta.get("upstream") or "").strip() or None,
            "template_roots": list(catalog_meta.template_roots),
            "fragment_roots": list(catalog_meta.fragment_roots),
        }
        normalized_parameters = _normalize_parameter_contracts(
            parameters,
            execution_strategy=execution_strategy,
        )
        summaries.append(
            SkillSummary(
                id=skill_dir.name,
                name=str(meta.get("display_name", meta.get("name", skill_dir.name))),
                name_en=str(meta.get("display_name_en", meta.get("name_en", skill_dir.name))),
                name_zh=str(meta.get("display_name_zh", meta.get("name_zh", meta.get("display_name", meta.get("name", skill_dir.name))))),
                description=str(meta.get("description", "")),
                description_en=str(meta.get("description_en", meta.get("description", ""))),
                description_zh=str(meta.get("description_zh", meta.get("description", ""))),
                icon=str(meta.get("icon", "")),
                color=str(meta.get("color", "")),
                triggers=_coerce_list(meta.get("triggers")),
                mode=mode,
                surface=str(od_meta.get("surface") or "").strip() or None,
                platform=str(od_meta.get("platform") or "").strip() or None,
                scenario=str(od_meta.get("scenario") or "").strip() or None,
                artifact_mode=artifact_mode,
                default_for=_coerce_list(od_meta.get("default_for")),
                featured=int(od_meta.get("featured")) if str(od_meta.get("featured") or "").strip().isdigit() else None,
                preview_type=str(preview_meta.get("type") or "html"),
                preview_entry=preview_entry,
                primary_output=primary_output,
                parameters=normalized_parameters,
                outputs_secondary=outputs_secondary,
                metadata_health={"frontmatter_status": parsed.frontmatter_status},
                protocol_provider=protocol.provider,
                protocol_family=protocol.family,
                protocol_metadata=protocol_metadata,
                capabilities={
                    **dict(runtime_capabilities),
                    "parameters": list(normalized_parameters or []),
                    "secondary_outputs": outputs_secondary,
                },
                example_prompt=str(od_meta.get("example_prompt") or meta.get("example_prompt") or "").strip() or None,
                has_example_html=(skill_dir / "example.html").is_file(),
            )
        )
    return CatalogSnapshot(
        kind=_SKILLS_KIND,
        source_digest=digest.hexdigest(),
        generated_at=int(time.time()),
        items=summaries,
    )


def build_design_system_summary_snapshot() -> CatalogSnapshot[DesignSystemSummary]:
    from app.services.agent_harness.capabilities.design_systems import (
        _DESIGN_SYSTEMS_DIR,
        _load_design_system_from_dir,
    )

    digest = hashlib.sha256()
    summaries: list[DesignSystemSummary] = []
    for system_dir in sorted(_DESIGN_SYSTEMS_DIR.iterdir()):
        system = _load_design_system_from_dir(system_dir)
        if system is None:
            continue
        health = system.health.to_payload() if system.health is not None else {"valid": False, "errors": ["missing health"], "warnings": []}
        digest.update(system.id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(system.source_digest.encode("utf-8"))
        if not bool(health.get("valid")):
            continue
        manifest = system.manifest if isinstance(system.manifest, dict) else {}
        resolver = manifest.get("resolver") if isinstance(manifest.get("resolver"), dict) else {}
        metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
        featured = _optional_int(manifest.get("featured") or metadata.get("featured"))
        summaries.append(
            DesignSystemSummary(
                id=system.id,
                title=system.title,
                description=system.description,
                category=system.category,
                sections=list(system.sections),
                palette=list(system.palette),
                preview=None,
                featured=featured,
                is_default=system.is_default,
                resolver_summary=str(
                    resolver.get("summary")
                    or metadata.get("summary")
                    or system.description
                    or system.title
                ),
                resolver_tags=_string_list(resolver.get("tags") or metadata.get("tags") or system.sections),
                preferred_for=_string_list(resolver.get("preferredFor") or resolver.get("preferred_for") or metadata.get("preferredFor")),
                avoid_for=_string_list(resolver.get("avoidFor") or resolver.get("avoid_for") or metadata.get("avoidFor")),
                tone=str(resolver.get("tone") or metadata.get("tone") or system.category or "").strip(),
                density=str(resolver.get("density") or metadata.get("density") or "").strip(),
                import_mode=system.import_mode or "normalized",
                health=health,
                source_digest=system.source_digest,
            )
        )
    return CatalogSnapshot(
        kind=_DESIGN_SYSTEMS_KIND,
        source_digest=digest.hexdigest(),
        generated_at=int(time.time()),
        items=summaries,
    )


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
