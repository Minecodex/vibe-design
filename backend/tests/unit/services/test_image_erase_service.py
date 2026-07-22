from app.services.image_erase import build_image_erase_prompt


def test_build_image_erase_prompt_mentions_masked_region_only():
    prompt = build_image_erase_prompt()

    assert "涂抹" in prompt
