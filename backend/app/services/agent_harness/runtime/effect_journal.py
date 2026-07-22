from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings


def record_effect_journal_entry(
    *,
    user_id: int,
    conversation_id: str,
    run_id: str | None,
    tool_call_id: str | None,
    tool_name: str,
    result: str,
    changed_paths: list[dict[str, Any]],
    workspace_root: Path | None = None,
) -> Path:
    root = _journal_root(workspace_root) / _safe_segment(str(user_id)) / _safe_segment(conversation_id)
    root.mkdir(parents=True, exist_ok=True)
    created_at_ns = time.time_ns()
    target = root / f"{created_at_ns}-{uuid.uuid4().hex}.json"
    temp = target.with_suffix(f".{uuid.uuid4().hex}.tmp")
    payload = {
        "schema_version": 1,
        "created_at_ns": created_at_ns,
        "user_id": int(user_id),
        "conversation_id": str(conversation_id),
        "run_id": str(run_id) if run_id else None,
        "tool_call_id": str(tool_call_id) if tool_call_id else None,
        "tool_name": str(tool_name),
        "result": str(result),
        "changed_paths": changed_paths[:500],
    }
    temp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temp.replace(target)
    return target


def _journal_root(workspace_root: Path | None = None) -> Path:
    root = Path(workspace_root or getattr(settings, "HARNESS_WORKSPACE_ROOT", "uploads/harness")).expanduser().resolve()
    return root / ".system" / "effect_journal"


def _safe_segment(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value) or "unknown"
