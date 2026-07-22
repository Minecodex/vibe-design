from __future__ import annotations

import json
from typing import Any


def tool_call_name(tool_call: dict[str, Any] | None) -> str:
    if not isinstance(tool_call, dict):
        return ""
    direct_name = str(tool_call.get("name") or "").strip()
    if direct_name:
        return direct_name
    function_payload = tool_call.get("function")
    if isinstance(function_payload, dict):
        return str(function_payload.get("name") or "").strip()
    return ""


def tool_call_arguments(tool_call: dict[str, Any] | None) -> Any:
    if not isinstance(tool_call, dict):
        return None
    if "arguments" in tool_call:
        raw_args = tool_call.get("arguments")
    else:
        function_payload = tool_call.get("function")
        raw_args = function_payload.get("arguments") if isinstance(function_payload, dict) else None
    if isinstance(raw_args, str):
        try:
            return json.loads(raw_args)
        except json.JSONDecodeError:
            return raw_args
    return raw_args
