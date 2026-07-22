from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.services.agent_harness.runtime.state.store_core import ensure_harness_meta, utc_now


DEFAULT_TOOL_RESULT_BLOB_THRESHOLD_CHARS = 16_384
PREVIEW_CHARS = 1_200


def blob_artifacts_dir(user_id: int, conversation_id: str, *, meta_dir: Path | None = None) -> Path:
    return (meta_dir or ensure_harness_meta(user_id, conversation_id)) / "tool_blobs"


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")[:80] or uuid.uuid4().hex[:12]


def _preview(text: str) -> str:
    compact = str(text or "")
    if len(compact) <= PREVIEW_CHARS:
        return compact
    return compact[:PREVIEW_CHARS].rstrip() + f"\n[blob artifact truncated {len(compact) - PREVIEW_CHARS} chars]"


def promote_large_tool_result(
    user_id: int,
    conversation_id: str,
    *,
    tool_call_id: str,
    tool_name: str,
    content: str,
    threshold_chars: int = DEFAULT_TOOL_RESULT_BLOB_THRESHOLD_CHARS,
    meta_dir: Path | None = None,
) -> dict[str, Any]:
    text = str(sanitize_persistent_payload(content, field_name="content") or "")
    if len(text) <= max(0, int(threshold_chars)):
        return {
            "promoted": False,
            "content": text,
            "preview": text,
            "artifact": None,
        }

    root = blob_artifacts_dir(user_id, conversation_id, meta_dir=meta_dir)
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    name = f"{_safe_name(tool_name)}-{_safe_name(tool_call_id)}-{digest[:12]}.json"
    path = root / name
    payload = {
        "artifact_id": digest[:24],
        "created_at": utc_now(),
        "kind": "tool_result",
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "sha256": digest,
        "size_chars": len(text),
        "content": text,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    rel = f".meta/tool_blobs/{name}"
    preview = _preview(text)
    artifact = {
        "id": digest[:24],
        "ref": rel,
        "sha256": digest,
        "size_chars": len(text),
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "preview": preview,
    }
    return {
        "promoted": True,
        "content": json.dumps({"blob_ref": rel, "preview": preview}, ensure_ascii=False),
        "preview": preview,
        "artifact": artifact,
    }
