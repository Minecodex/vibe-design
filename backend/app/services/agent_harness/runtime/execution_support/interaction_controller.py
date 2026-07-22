from __future__ import annotations

from typing import Any


class InteractionController:
    @staticmethod
    def ask_user_pending(call_id: str, result_metadata: dict[str, Any] | None, output: str) -> dict[str, Any]:
        metadata = result_metadata or {}
        pending = {
            key: value
            for key, value in metadata.items()
            if key not in {"type", "request_id", "tool_call_id"}
        }
        pending.update({
            "request_id": call_id,
            "tool_call_id": call_id,
            "kind": "ask_user",
            "question": metadata.get("question") or output,
            "options": metadata.get("options") or [],
        })
        return pending
