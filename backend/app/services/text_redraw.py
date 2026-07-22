from __future__ import annotations

import json
import re
from typing import Any


def build_text_redraw_extraction_prompt() -> str:
    return (
        "Extract all clearly visible text from this image. "
        "Group characters into natural reading segments, preserve reading order, "
        'and return JSON only as an array of objects in the format [{"text":"...", "order":1}]. '
        "Do not include markdown fences or explanations."
    )


def extract_text_redraw_response_text(result: dict[str, Any]) -> str:
    # OpenAI chat completions format
    choices = result.get("choices", [])
    if not choices:
        raise ValueError("No choices returned from multimodal response")

    text = choices[0].get("message", {}).get("content", "")
    if not text or not text.strip():
        raise ValueError("No text payload returned from multimodal response")
    return text.strip()


def parse_text_redraw_segments(payload: str | list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    data: Any = payload
    if isinstance(payload, str):
        matched = re.search(r"\[[\s\S]*\]", payload)
        if not matched:
            raise ValueError("Unable to find JSON array in multimodal response")
        data = json.loads(matched.group(0))
    elif isinstance(payload, dict):
        data = payload.get("segments")

    if not isinstance(data, list):
        raise ValueError("Text redraw segments must be a JSON array")

    normalized: list[dict[str, Any]] = []
    for index, raw_segment in enumerate(data, start=1):
        if not isinstance(raw_segment, dict):
            continue
        text = str(raw_segment.get("text", "")).strip()
        if not text:
            continue
        order = raw_segment.get("order", index)
        try:
            order = int(order)
        except (TypeError, ValueError):
            order = index
        normalized.append(
            {
                "id": str(raw_segment.get("id") or f"seg-{index}"),
                "text": text,
                "order": order,
            }
        )

    normalized.sort(key=lambda segment: (segment["order"], segment["id"]))
    if not normalized:
        raise ValueError("No text segments found")
    return normalized


def build_text_redraw_prompt(
    original_segments: list[dict[str, Any]],
    edited_segments: list[dict[str, Any]],
) -> str:
    edited_by_id = {segment["id"]: segment for segment in edited_segments}
    mappings: list[str] = []
    for original in sorted(original_segments, key=lambda segment: segment["order"]):
        edited = edited_by_id[original["id"]]
        if original["text"] == edited["text"]:
            continue
        mappings.append(f'{len(mappings) + 1}. "{original["text"]}" -> "{edited["text"]}"')

    if not mappings:
        return (
            "No text replacements are required.\n"
            "Return the reference image unchanged.\n"
            "Output one image only."
        )

    mapping_block = "\n".join(mappings)
    return (
        "Keep composition, objects, materials, colors, lighting, spacing, perspective, and overall layout unchanged.\n"
        "Remove all original visible text.\n"
        "Re-render only the text content according to the replacement map below.\n"
        "Keep font style, font weight, alignment, line spacing, letter spacing, curvature, distortion, and print texture as close as possible to the original.\n"
        "If text length changes, adjust size and spacing minimally so the layout still looks natural.\n"
        "Do not add, remove, or move any non-text visual elements.\n"
        "Output one image only.\n\n"
        "Text replacement map:\n"
        f"{mapping_block}"
    )
