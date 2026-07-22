import pytest

from app.services.text_redraw import (
    build_text_redraw_prompt,
    parse_text_redraw_segments,
)


def test_parse_text_redraw_segments_reads_json_array():
    payload = '[{"text":"MARSHALL","order":1},{"text":"EST.1962","order":2}]'

    segments = parse_text_redraw_segments(payload)

    assert [segment["text"] for segment in segments] == ["MARSHALL", "EST.1962"]
    assert [segment["id"] for segment in segments] == ["seg-1", "seg-2"]


def test_build_text_redraw_prompt_contains_preserve_rules_and_mapping():
    prompt = build_text_redraw_prompt(
        original_segments=[{"id": "1", "text": "MARSHALL", "order": 1}],
        edited_segments=[{"id": "1", "text": "NEW BRAND", "order": 1}],
    )

    assert "Keep composition" in prompt
    assert '"MARSHALL" -> "NEW BRAND"' in prompt


def test_build_text_redraw_prompt_omits_unchanged_segments():
    prompt = build_text_redraw_prompt(
        original_segments=[
            {"id": "1", "text": "TAX SEVING", "order": 1},
            {"id": "2", "text": "税企", "order": 2},
            {"id": "3", "text": "茶话", "order": 3},
        ],
        edited_segments=[
            {"id": "1", "text": "TAX SEVING", "order": 1},
            {"id": "2", "text": "企业", "order": 2},
            {"id": "3", "text": "茶话", "order": 3},
        ],
    )

    assert '"税企" -> "企业"' in prompt
    assert '"TAX SEVING" -> "TAX SEVING"' not in prompt
    assert '"茶话" -> "茶话"' not in prompt


def test_parse_text_redraw_segments_rejects_empty_results():
    with pytest.raises(ValueError, match="No text segments found"):
        parse_text_redraw_segments("[]")
