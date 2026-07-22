"""Helpers for tracking file snapshots used by editing tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class FileSnapshot:
    mtime_ns: int
    size: int
    sha256: str


def build_snapshot(path: Path) -> FileSnapshot:
    stat = path.stat()
    content = path.read_bytes()
    return FileSnapshot(
        mtime_ns=int(stat.st_mtime_ns),
        size=int(stat.st_size),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def snapshot_to_dict(snapshot: FileSnapshot) -> dict[str, Any]:
    return asdict(snapshot)


def snapshot_from_dict(payload: dict[str, Any] | None) -> FileSnapshot | None:
    if not isinstance(payload, dict):
        return None
    try:
        return FileSnapshot(
            mtime_ns=int(payload["mtime_ns"]),
            size=int(payload["size"]),
            sha256=str(payload["sha256"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def snapshots_equal(left: FileSnapshot | None, right: FileSnapshot | None) -> bool:
    return left == right and left is not None


def load_snapshot_map(path: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        snapshot = snapshot_from_dict(value)
        if snapshot is None:
            continue
        normalized[str(key)] = snapshot_to_dict(snapshot)
    return normalized


def save_snapshot_map(path: Path, snapshots: dict[str, dict[str, Any]]) -> None:
    path.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2), encoding="utf-8")
