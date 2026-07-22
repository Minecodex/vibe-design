from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.persistence_sanitizer import sanitize_persistent_payload


class SidechainArtifactStore:
    """Durable derived artifacts for Sidechain Task diagnostics."""

    def __init__(self, ctx) -> None:
        self.ctx = ctx

    def start_transcript(self, task_id: str, *, metadata: dict[str, Any] | None = None) -> str:
        ref = self.transcript_ref(task_id)
        path = self._resolve_ref(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            self._append_jsonl(
                path,
                {
                    "type": "transcript_started",
                    "task_id": self._safe_task_id(task_id),
                    "metadata": metadata or {},
                    "ts": self._now(),
                },
            )
        return ref

    def append_transcript(self, task_id: str, entry: dict[str, Any]) -> str:
        ref = self.transcript_ref(task_id)
        path = self._resolve_ref(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(entry)
        payload.setdefault("task_id", self._safe_task_id(task_id))
        payload.setdefault("ts", self._now())
        self._append_jsonl(path, payload)
        return ref

    def write_result(
        self,
        task_id: str,
        *,
        status: str,
        summary: str,
        output_refs: list[dict[str, Any]] | None = None,
        failure_details: dict[str, Any] | None = None,
        usage_summary: dict[str, Any] | None = None,
        transcript_ref: str | None = None,
    ) -> str:
        ref = self.result_ref(task_id)
        path = self._resolve_ref(ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "task_id": self._safe_task_id(task_id),
            "status": status,
            "summary": summary,
            "output_refs": list(output_refs or []),
            "failure_details": dict(failure_details or {}),
            "usage_summary": dict(usage_summary or {}),
            "transcript_ref": transcript_ref,
            "ts": self._now(),
        }
        path.write_text(
            json.dumps(sanitize_persistent_payload(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return ref

    def read_result(self, task_id: str) -> dict[str, Any]:
        return json.loads(self._resolve_ref(self.result_ref(task_id)).read_text(encoding="utf-8"))

    def transcript_ref(self, task_id: str) -> str:
        return f".agent/sidechains/{self._safe_task_id(task_id)}/transcript.jsonl"

    def result_ref(self, task_id: str) -> str:
        return f".agent/sidechains/{self._safe_task_id(task_id)}/result.json"

    def _resolve_ref(self, ref: str) -> Path:
        path = (self.ctx.conversation_dir / ref).resolve()
        path.relative_to(self.ctx.agent_dir.resolve())
        return path

    @staticmethod
    def _safe_task_id(task_id: str) -> str:
        raw = str(task_id or "sidechain").replace("\\", "/").strip().strip("/")
        raw = raw.split("/")[-1] if "/" in raw else raw
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip(".-")
        return safe or "sidechain"

    @staticmethod
    def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(sanitize_persistent_payload(payload), ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
