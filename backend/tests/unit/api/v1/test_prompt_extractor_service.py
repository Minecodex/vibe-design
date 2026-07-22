from io import BytesIO

import pytest
from starlette.datastructures import UploadFile

from app.services.prompt_extractor import (
    PromptExtractorService,
    build_prompt_extractor_instruction,
    extract_prompt_extractor_prompts,
    extract_prompt_extractor_text,
    normalize_prompt_extractor_locale,
)


def test_normalize_prompt_extractor_locale():
    assert normalize_prompt_extractor_locale("zh-CN") == "zh-CN"
    assert normalize_prompt_extractor_locale("zh-TW") == "zh-CN"
    assert normalize_prompt_extractor_locale("en-US") == "en-US"
    assert normalize_prompt_extractor_locale("en-GB") == "en-US"


def test_build_prompt_extractor_instruction_requests_bilingual_json():
    instruction = build_prompt_extractor_instruction("zh-CN")

    assert "zh-CN" in instruction
    assert "en-US" in instruction
    assert "JSON" in instruction


def test_extract_prompt_extractor_text_supports_string_and_list_payloads():
    assert extract_prompt_extractor_text(
        {
            "choices": [
                {
                    "message": {
                        "content": "prompt one",
                    }
                }
            ]
        }
    ) == "prompt one"

    assert extract_prompt_extractor_text(
        {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "prompt two"},
                        ],
                    }
                }
            ]
        }
    ) == "prompt two"


def test_extract_prompt_extractor_prompts_requires_zh_and_en_json():
    prompts = extract_prompt_extractor_prompts(
        {
            "choices": [
                {
                    "message": {
                        "content": '{"zh-CN":"一只白猫，电影感光影","en-US":"a white cat, cinematic light"}',
                    }
                }
            ]
        }
    )

    assert prompts == {
        "zh-CN": "一只白猫，电影感光影",
        "en-US": "a white cat, cinematic light",
    }


def test_extract_prompt_extractor_prompts_rejects_missing_language():
    with pytest.raises(ValueError, match="both zh-CN and en-US"):
        extract_prompt_extractor_prompts(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"zh-CN":"一只白猫"}',
                        }
                    }
                ]
            }
        )


@pytest.mark.asyncio
async def test_prompt_extractor_service_rejects_invalid_image_type():
    upload = UploadFile(
        filename="demo.txt",
        file=BytesIO(b"bad"),
        headers={"content-type": "text/plain"},
    )
    service = PromptExtractorService(db=object())

    with pytest.raises(ValueError, match="Unsupported image type"):
        await service._read_image_data(upload)
