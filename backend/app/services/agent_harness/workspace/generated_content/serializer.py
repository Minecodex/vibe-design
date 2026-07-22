from __future__ import annotations

import json
from typing import Any, Literal

GeneratedContentKind = Literal["json", "jsonl", "text", "js_module"]


def serialize_generated_content(kind: GeneratedContentKind, content: Any, *, export_name: str = "data") -> str:
    if kind == "json":
        return json.dumps(content, ensure_ascii=False, indent=2) + "\n"
    if kind == "jsonl":
        if not isinstance(content, list):
            raise ValueError("jsonl content must be a list of JSON-serializable entries")
        return "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in content)
    if kind == "js_module":
        safe_export_name = _sanitize_js_identifier(export_name)
        return f"module.exports.{safe_export_name} = {json.dumps(content, ensure_ascii=False, indent=2)};\n"
    return str(content)


def _sanitize_js_identifier(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(value or "data"))
    if not text or text[0].isdigit():
        text = f"data_{text}"
    return text
