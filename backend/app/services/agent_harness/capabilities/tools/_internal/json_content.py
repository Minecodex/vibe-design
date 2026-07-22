from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


class JsonContentError(ValueError):
    """Raised when a structured JSON tool payload is ambiguous or invalid."""


@dataclass(frozen=True, slots=True)
class NormalizedJsonContent:
    text: str
    metadata: dict[str, Any]


def normalize_json_content(content: Any, *, allow_json_scalar: bool = False) -> NormalizedJsonContent:
    """Serialize JSON mode content without accidentally double-encoding documents."""

    value = content
    metadata: dict[str, Any] = {"json_normalization": "structured_value"}
    if isinstance(content, str):
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise JsonContentError(
                "kind=json expects a JSON value, preferably a valid JSON object or array. "
                "Pass plain text with kind=text, or pass a structured object/array instead."
            ) from exc
        metadata["json_normalization"] = "parsed_json_string"

    if isinstance(value, dict):
        metadata["json_content_shape"] = "object"
    elif isinstance(value, list):
        metadata["json_content_shape"] = "array"
    else:
        if not allow_json_scalar:
            raise JsonContentError(
                "JSON scalar content is ambiguous in kind=json. Pass an object/array, "
                "use kind=text for plain strings, or set allow_json_scalar=true intentionally."
            )
        metadata["json_content_shape"] = "scalar"

    return NormalizedJsonContent(
        text=json.dumps(value, ensure_ascii=False, indent=2),
        metadata=metadata,
    )


def serialize_jsonl_content(content: Any) -> str:
    if not isinstance(content, list):
        raise JsonContentError("jsonl content must be a list of JSON values")
    return "\n".join(json.dumps(item, ensure_ascii=False) for item in content)
