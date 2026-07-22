import base64
import json
from dataclasses import dataclass

from fastapi import UploadFile

from app.core.default_models import (
    get_default_mark_recognition_model,
    get_default_mark_recognition_provider,
)
from app.services.multimodal_service import MultimodalService

SUPPORTED_PROMPT_EXTRACTOR_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}
PROMPT_EXTRACTOR_MAX_BYTES = 10 * 1024 * 1024


@dataclass
class PromptExtractorResult:
    prompt: str
    prompts: dict[str, str]
    language: str
    model: str
    amount_cents: int


def normalize_prompt_extractor_locale(locale: str) -> str:
    normalized = (locale or "").strip().lower()
    if normalized.startswith("zh"):
        return "zh-CN"
    if normalized.startswith("en"):
        return "en-US"
    raise ValueError("Unsupported locale")


def build_prompt_extractor_instruction(locale: str) -> str:
    normalize_prompt_extractor_locale(locale)
    return (
        "Analyze this image and write two complete prompts that can be used to generate a very similar image. "
        'Return exactly one JSON object with string keys "zh-CN" and "en-US". '
        'The "zh-CN" value must be a natural Chinese prompt. '
        'The "en-US" value must be a natural English prompt. '
        "Do not include markdown, code fences, titles, numbering, or explanation."
    )


def extract_prompt_extractor_text(result: dict) -> str:
    choices = result.get("choices") or []
    if not choices:
        raise ValueError("Prompt extraction returned no choices")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        text_parts = [
            part.get("text", "").strip()
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        text = "\n".join(part for part in text_parts if part).strip()
    else:
        text = ""

    if not text:
        raise ValueError("Prompt extraction returned empty content")
    return text


def extract_prompt_extractor_prompts(result: dict) -> dict[str, str]:
    text = extract_prompt_extractor_text(result)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("Prompt extraction returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("Prompt extraction returned invalid prompt payload")

    prompts = {
        "zh-CN": str(payload.get("zh-CN") or "").strip(),
        "en-US": str(payload.get("en-US") or "").strip(),
    }
    if not prompts["zh-CN"] or not prompts["en-US"]:
        raise ValueError("Prompt extraction must include both zh-CN and en-US prompts")
    return prompts


class PromptExtractorService:
    def __init__(self, db):
        self.db = db

    async def _read_image_data(self, image: UploadFile) -> tuple[str, bytes]:
        content_type = (image.content_type or "").strip().lower()
        if content_type not in SUPPORTED_PROMPT_EXTRACTOR_MIME_TYPES:
            raise ValueError("Unsupported image type")

        file_bytes = await image.read()
        if not file_bytes:
            raise ValueError("Image file is empty")
        if len(file_bytes) > PROMPT_EXTRACTOR_MAX_BYTES:
            raise ValueError("Image file is too large")
        return content_type, file_bytes

    async def analyze(
        self,
        *,
        user_id: int,
        locale: str,
        image: UploadFile,
    ) -> PromptExtractorResult:
        normalized_locale = normalize_prompt_extractor_locale(locale)
        mime_type, file_bytes = await self._read_image_data(image)
        image_data = base64.b64encode(file_bytes).decode("ascii")
        image_url = f"data:{mime_type};base64,{image_data}"

        multimodal = MultimodalService(self.db)
        result = await multimodal.chat(
            user_id=user_id,
            model_name=get_default_mark_recognition_model(),
            provider_code=get_default_mark_recognition_provider(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": build_prompt_extractor_instruction(normalized_locale)},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            task_type="prompt_extraction",
            billing_label="billing.labels.prompt_extraction",
        )
        prompts = extract_prompt_extractor_prompts(result)
        return PromptExtractorResult(
            prompt=prompts[normalized_locale],
            prompts=prompts,
            language=normalized_locale,
            model=get_default_mark_recognition_model(),
            amount_cents=int(result.get("_amount_cents") or 0),
        )
