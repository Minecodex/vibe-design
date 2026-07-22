import pytest
from pydantic import ValidationError

from app.schemas.generation import TextRedrawExtractResponse, TextRedrawSubmitRequest


def test_text_redraw_submit_request_requires_matching_segment_ids():
    with pytest.raises(ValidationError, match="segment ids must match"):
        TextRedrawSubmitRequest(
            source_image_url="/img.png",
            original_segments=[{"id": "1", "text": "A", "order": 1}],
            edited_segments=[{"id": "2", "text": "B", "order": 1}],
        )


def test_text_redraw_extract_response_accepts_ordered_segments():
    response = TextRedrawExtractResponse(
        segments=[{"id": "1", "text": "MARSHALL", "order": 1}]
    )

    assert response.segments[0].text == "MARSHALL"
    assert response.segments[0].order == 1
