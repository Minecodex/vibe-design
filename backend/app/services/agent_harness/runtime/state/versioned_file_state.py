from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class HarnessFileVersion:
    version_id: str
    label: str
    file_path: str
    mirror_path: str | None
    size: int
    sha256: str
    created_at: str
    created_by: str = "agent"
    run_id: str | None = None
    parent_version_id: str | None = None
    parent_input_asset_ids: list[str] = field(default_factory=list)
    referenced_asset_ids: list[str] = field(default_factory=list)
    note: str | None = None
    artifact_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HarnessVersionedFile:
    file_id: str
    name: str
    type: str
    current_version_id: str
    created_at: str
    updated_at: str
    versions: list[HarnessFileVersion] = field(default_factory=list)


def file_version_to_dict(version: HarnessFileVersion) -> dict[str, Any]:
    return asdict(version)


def versioned_file_to_dict(file: HarnessVersionedFile) -> dict[str, Any]:
    payload = asdict(file)
    payload["versions"] = [file_version_to_dict(version) for version in file.versions]
    return payload


def file_version_from_dict(payload: dict[str, Any]) -> HarnessFileVersion:
    return HarnessFileVersion(
        version_id=str(payload.get("version_id") or ""),
        label=str(payload.get("label") or ""),
        file_path=str(payload.get("file_path") or ""),
        mirror_path=str(payload.get("mirror_path") or "") or None,
        size=int(payload.get("size") or 0),
        sha256=str(payload.get("sha256") or ""),
        created_at=str(payload.get("created_at") or ""),
        created_by=str(payload.get("created_by") or "agent"),
        run_id=str(payload.get("run_id") or "") or None,
        parent_version_id=str(payload.get("parent_version_id") or "") or None,
        parent_input_asset_ids=[
            str(item) for item in payload.get("parent_input_asset_ids") or []
        ],
        referenced_asset_ids=[
            str(item) for item in payload.get("referenced_asset_ids") or []
        ],
        note=str(payload.get("note") or "") or None,
        artifact_metadata=dict(payload.get("artifact_metadata") or {}),
    )


def versioned_file_from_dict(payload: dict[str, Any]) -> HarnessVersionedFile:
    versions = [
        file_version_from_dict(item)
        for item in payload.get("versions") or []
        if isinstance(item, dict)
    ]
    return HarnessVersionedFile(
        file_id=str(payload.get("file_id") or ""),
        name=str(payload.get("name") or ""),
        type=str(payload.get("type") or "other"),
        current_version_id=str(payload.get("current_version_id") or ""),
        created_at=str(payload.get("created_at") or ""),
        updated_at=str(payload.get("updated_at") or ""),
        versions=versions,
    )
