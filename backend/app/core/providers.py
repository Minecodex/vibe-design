from copy import deepcopy

from app.core.config import settings
from app.core.default_models import (
    get_ollama_image_generation_model,
    is_ollama_image_generation_enabled,
    is_ollama_multimodal_enabled,
)
from app.core.media_dimensions import (
    GPT_IMAGE_2_DIMENSION_TABLE,
    SEEDREAM_5_LITE_DIMENSION_TABLE,
    estimated_image_dimension_config,
    exact_dimension_config,
    video_short_side_dimension_config,
)
from app.core.money import pricing_cents_from_points_map
from app.core.ollama_image_config import get_ollama_image_generation_config


def _multimodal_config(
    *,
    input_price: int | float,
    output_price: int | float,
    max_input_tokens: int,
    max_output_tokens: int,
    supports_fast_mode: bool,
    supports_thinking_mode: bool,
    thinking_variant_of: str | None = None,
) -> dict:
    config = {
        "pricing_mode": "per_token",
        "pricing_cents": pricing_cents_from_points_map({"input": input_price, "output": output_price}),
        "max_input_tokens": max_input_tokens,
        "max_output_tokens": max_output_tokens,
        "supports_fast_mode": supports_fast_mode,
        "supports_thinking_mode": supports_thinking_mode,
    }
    if thinking_variant_of:
        config["thinking_variant_of"] = thinking_variant_of
    return config

# ---------------------------------------------------------------------------
# Static provider registry - only ?? and ?? are supported for now.
# ---------------------------------------------------------------------------
PROVIDER_REGISTRY: dict[str, dict] = {
    "builtin": {
        "code": "builtin",
        "name": settings.APP_NAME,
        "author": settings.APP_NAME,
        "description": "Built-in model provider for the platform.",
        "logo_url": "/providers/builtin/logo",
        "tags": ["TEXT2IMAGE", "TEXT2VIDEO", "MULTIMODAL"],
        "is_builtin": True,
        "credential_types": [],
        "models": {
            "text2image": [
                {
                    "model_name": "gemini-3.1-flash-image-preview",
                    "label": "NanoBanana2",
                    "config": {
                        "allowed_sizes": ["0.5K", "1K", "2K", "4K"],
                        "allowed_aspect_ratios": [
                            "1:1",
                            "16:9",
                            "9:16",
                            "4:3",
                            "3:4",
                            "3:2",
                            "2:3",
                            "5:4",
                            "4:5",
                            "21:9",
                            "1:4",
                            "4:1",
                            "1:8",
                            "8:1",
                        ],
                        "supports_reference_image": True,
                        "pricing_mode": "per_resolution",
                        "pricing_cents": pricing_cents_from_points_map({"0.5K": 54, "1K": 54, "2K": 80, "4K": 120}),
                        "max_reference_images": 14,
                        **estimated_image_dimension_config(),
                    },
                },
                {
                    "model_name": "gemini-3-pro-image-preview",
                    "label": "Nano Banana Pro",
                    "config": {
                        "allowed_sizes": [ "1K", "2K", "4K"],
                        "allowed_aspect_ratios": [
                            "1:1",
                            "2:3",
                            "3:2",
                            "3:4",
                            "4:3",
                            "4:5",
                            "5:4",
                            "9:16",
                            "16:9",
                            "21:9",
                        ],
                        "supports_reference_image": True,
                        "pricing_mode": "per_resolution",
                        "pricing_cents": pricing_cents_from_points_map({"1K": 107, "2K": 107, "4K": 191.4285}),
                        "max_reference_images": 14,
                        **estimated_image_dimension_config(),
                    },
                },
                {
                    "model_name": "imagen-4.0-apimart",
                    "label": "Imagen 4.0",
                    "config": {
                        "allowed_sizes": ["1K"],
                        "allowed_aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16"],
                        "supports_reference_image": False,
                        "pricing_mode": "flat",
                        "pricing_cents": pricing_cents_from_points_map({"flat": 40}),
                        **estimated_image_dimension_config(),
                    },
                },
                {
                    "model_name": "gpt-image-2",
                    "label": "GPT-Image 2",
                    "config": {
                        "allowed_sizes": ["1K", "2K", "4K"],
                        "allowed_aspect_ratios": [
                            "1:1",
                            "16:9",
                            "9:16",
                            "2:1",
                            "1:2",
                            "4:3",
                            "3:4",
                            "3:2",
                            "2:3",
                            "5:4",
                            "4:5",
                            "21:9",
                            "9:21",
                            "3:1",
                            "1:3",
                        ],
                        "allowed_aspect_ratios_by_size": {
                            "4K": [
                                "1:1",
                                "16:9",
                                "9:16",
                                "2:1",
                                "1:2",
                                "4:3",
                                "3:4",
                                "3:2",
                                "2:3",
                                "5:4",
                                "4:5",
                                "21:9",
                                "9:21",
                                "3:1",
                                "1:3",
                            ],
                        },
                        "supports_reference_image": True,
                        "pricing_mode": "per_resolution",
                        "pricing_cents": pricing_cents_from_points_map({"1K": 5.7, "2K": 11.4285, "4K": 18}),
                        "max_reference_images": 16,
                        **exact_dimension_config(GPT_IMAGE_2_DIMENSION_TABLE),
                    },
                },
                {
                    "model_name": "doubao-seedream-4-5",
                    "label": "Seedream 4.5",
                    "config": {
                        "allowed_sizes": ["2K", "4K"],
                        "allowed_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9", "9:21"],
                        "supports_reference_image": True,
                        "pricing_mode": "per_resolution",
                        "pricing_cents": pricing_cents_from_points_map({"2K": 28, "4K": 28}),
                        "max_reference_images": 10,
                        **estimated_image_dimension_config(),
                    },
                },
                {
                    "model_name": "doubao-seedream-5-0-lite",
                    "label": "Seedream 5.0 Lite",
                    "config": {
                        "allowed_sizes": ["2K", "3K", "4K"],
                        "allowed_aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
                        "supports_reference_image": True,
                        "pricing_mode": "per_resolution",
                        "pricing_cents": pricing_cents_from_points_map({"2K": 28, "3K": 28, "4K": 28}),
                        "max_reference_images": 10,
                        **exact_dimension_config(SEEDREAM_5_LITE_DIMENSION_TABLE),
                    },
                },
            ],
            "text2video": [
                {
                    "model_name": "kling-v2-6",
                    "label": "Kling 2.6",
                    "config": {
                        "allowed_durations": ["5s", "10s"],
                        "allowed_aspect_ratios": ["16:9", "9:16", "1:1"],
                        "allowed_sizes": ["720p", "1080p", "1080p_audio"],
                        "supports_kling_mode": True,
                        "supports_reference_image": True,
                        "supports_first_frame": True,
                        "supports_tail_frame": True,
                        "supports_audio": True,
                        "audio_allowed_sizes": ["1080p_audio"],
                        "tail_frame_allowed_sizes": ["1080p"],
                        "requires_first_frame_for_tail_frame": True,
                        "audio_tail_frame_mutually_exclusive": True,
                        "pricing_mode": "per_second",
                        "pricing_cents": pricing_cents_from_points_map({"720p": 37, "1080p": 62, "1080p_audio": 150}),
                        "max_image_inputs": 2,
                        **video_short_side_dimension_config(),
                    },
                },
                {
                    "model_name": "kling-v3",
                    "label": "Kling 3",
                    "config": {
                        "min_duration": 3,
                        "max_duration": 15,
                        "allowed_aspect_ratios": ["16:9", "9:16", "1:1"],
                        "allowed_sizes": ["720p", "720p_audio", "1080p", "1080p_audio", "4k", "4k_audio"],
                        "supports_kling_mode": True,
                        "supports_reference_image": True,
                        "supports_first_frame": True,
                        "supports_tail_frame": True,
                        "supports_audio": True,
                        "requires_first_frame_for_tail_frame": True,
                        "supports_multi_shot": True,
                        "supports_element_list": True,
                        "pricing_mode": "per_second",
                        "pricing_cents": pricing_cents_from_points_map({
                            "720p": 67,
                            "720p_audio": 101,
                            "1080p": 90,
                            "1080p_audio": 134,
                            "4k": 428,
                            "4k_audio": 428,
                        }),
                        "max_image_inputs": 2,
                        **video_short_side_dimension_config(),
                    },
                },
                {
                    "model_name": "doubao-seedance-1-5-pro",
                    "label": "Seedance 1.5 Pro",
                    "config": {
                        "min_duration": 4,
                        "max_duration": 12,
                        "allowed_aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9"],
                        "allowed_sizes": ["480p", "720p", "1080p"],
                        "supports_reference_image": True,
                        "supports_first_frame": True,
                        "supports_tail_frame": True,
                        "supports_audio": True,
                        "disallow_reference_mode": True,
                        "pricing_mode": "per_second",
                        "pricing_cents": pricing_cents_from_points_map({"480p": 20, "720p": 44, "1080p": 108}),
                        "max_image_inputs": 2,
                        **video_short_side_dimension_config(),
                    },
                },
                {
                    "model_name": "doubao-seedance-2.0",
                    "label": "Seedance 2.0",
                    "config": {
                        "min_duration": 5,
                        "max_duration": 15,
                        "allowed_aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9"],
                        "allowed_sizes": ["480p", "720p", "1080p"],
                        "supports_reference_image": True,
                        "supports_reference_image_list": True,
                        "supports_first_frame": True,
                        "supports_tail_frame": True,
                        "supports_audio": True,
                        "supports_reference_video": False,
                        "supports_reference_audio": False,
                        "supports_return_last_frame": True,
                        "image_modes_conflict": True,
                        "pricing_mode": "per_second",
                        "pricing_cents": pricing_cents_from_points_map({"480p": 72, "720p": 155, "1080p": 351}),
                        "max_image_inputs": 9,
                        "uploaded_video_pricing_cents": pricing_cents_from_points_map({"480p": 40, "720p": 86}),
                        **video_short_side_dimension_config(),
                    },
                },
                {
                    "model_name": "grok-imagine-1.0-video-apimart",
                    "label": "Grok-Imagine-video-1.0",
                    "config": {
                        "min_duration": 6,
                        "max_duration": 30,
                        "allowed_aspect_ratios": ["16:9", "9:16", "1:1", "3:2", "2:3"],
                        "allowed_sizes": ["480p", "720p"],
                        "supports_reference_image": True,
                        "supports_reference_image_list": True,
                        "supports_reference_video": False,
                        "supports_reference_audio": False,
                        "pricing_mode": "per_second",
                        "pricing_cents": pricing_cents_from_points_map({"480p": 7, "720p": 14}),
                        "max_image_inputs": 7,
                        **video_short_side_dimension_config(),
                    },
                },
            ],
            "multimodal": [
                {
                    "model_name": "gemini-3.1-pro-preview",
                    "label": "Gemini 3.1 Pro",
                    "config": _multimodal_config(
                        input_price=1600,
                        output_price=9600,
                        max_input_tokens=1048576,
                        max_output_tokens=65536,
                        supports_fast_mode=True,
                        supports_thinking_mode=False,
                    ),
                },
                {
                    "model_name": "gemini-3-pro-preview-thinking",
                    "label": "Gemini 3.0 Pro Thinking",
                    "config": _multimodal_config(
                        input_price=1600,
                        output_price=9600,
                        max_input_tokens=1048576,
                        max_output_tokens=65536,
                        supports_fast_mode=False,
                        supports_thinking_mode=True,
                        thinking_variant_of="gemini-3.1-pro-preview",
                    ),
                },
                {
                    "model_name": "claude-opus-4-8",
                    "label": "Opus 4.8",
                    "config": _multimodal_config(
                        input_price=4000,
                        output_price=20000,
                        max_input_tokens=1000000,
                        max_output_tokens=128000,
                        supports_fast_mode=True,
                        supports_thinking_mode=False,
                    ),
                },
                {
                    "model_name": "claude-opus-4-6-thinking",
                    "label": "Opus 4.6 Thinking",
                    "config": _multimodal_config(
                        input_price=4000,
                        output_price=20000,
                        max_input_tokens=1000000,
                        max_output_tokens=128000,
                        supports_fast_mode=False,
                        supports_thinking_mode=True,
                        thinking_variant_of="claude-opus-4-8",
                    ),
                },
                {
                    "model_name": "deepseek-v4-pro",
                    "label": "DeepSeek V4 Pro",
                    "config": _multimodal_config(
                        input_price=1371.4285,
                        output_price=2742.8571,
                        max_input_tokens=1048576,
                        max_output_tokens=128000,
                        supports_fast_mode=True,
                        supports_thinking_mode=False,
                    ),
                },
                {
                    "model_name": "glm-5.1",
                    "label": "GLM 5.1",
                    "config": _multimodal_config(
                        input_price=800,
                        output_price=1440,
                        max_input_tokens=204800,
                        max_output_tokens=128000,
                        supports_fast_mode=True,
                        supports_thinking_mode=False,
                    ),
                },
                {
                    "model_name": "kimi-k2.5",
                    "label": "Kimi K2.5",
                    "config": _multimodal_config(
                        input_price=412,
                        output_price=555,
                        max_input_tokens=262144,
                        max_output_tokens=98304,
                        supports_fast_mode=True,
                        supports_thinking_mode=False,
                    ) | {"context_compression": True},
                },
            ],
        },
    },
    "kling": {
        "code": "kling",
        "name": "可灵",
        "author": "Kuaishou",
        "description": "快手开发的新一代AI原生视频生成模型",
        "logo_url": "/providers/kling/logo",
        "tags": ["TEXT2IMAGE", "TEXT2VIDEO"],
        "credential_types": ["ak_sk"],
        "models": {
            "text2image": [
                {"model_name": "kling-v2-1", "label": "图片2.1"},
            ],
            "text2video": [
                {"model_name": "kling-v2-6", "label": "视频2.6"},
            ],
        },
    },
    "jimeng": {
        "code": "jimeng",
        "name": "即梦",
        "author": "ByteDance",
        "description": "字节跳动旗下的AI视频与图像创作平台",
        "logo_url": "/providers/jimeng/logo",
        "tags": ["TEXT2IMAGE", "TEXT2VIDEO"],
        "credential_types": ["ak_sk"],
        "models": {
            "text2image": [
                {"model_name": "jimeng_t2i_v40", "label": "图片生成4.0"},
            ],
            "text2video": [
                {"model_name": "jimeng_ti2v_v30_pro", "label": "视频生成3.0pro"},
            ],
        },
    },
    "volcark": {
        "code": "volcark",
        "name": "火山方舟",
        "author": "ByteDance",
        "description": "火山引擎旗下的大模型服务平台，支持豆包系列模型",
        "logo_url": "/providers/volcark/logo",
        "tags": ["TEXT2IMAGE", "TEXT2VIDEO"],
        "credential_types": ["ak_sk", "api_key"],
        "requires_endpoint": True,
        "models": {
            "text2image": [
                {"model_name": "Doubao-Seedream-5.0-lite", "label": "Seedream 5.0 lite"},
            ],
            "text2video": [
                {"model_name": "Doubao-Seedance-2.0", "label": "Seedance 2.0"},
            ],
        },
    },
}


def _build_ollama_provider() -> dict:
    model_name = settings.OLLAMA_MULTIMODAL_MODEL.strip()
    max_input_tokens = int(settings.OLLAMA_MAX_INPUT_TOKENS or 0)
    max_output_tokens = int(settings.OLLAMA_MAX_OUTPUT_TOKENS or 0)
    models: dict[str, list[dict]] = {}
    tags: list[str] = []
    if is_ollama_multimodal_enabled():
        tags.append("MULTIMODAL")
        models["multimodal"] = [
            {
                "model_name": model_name,
                "label": f"Ollama ({model_name})",
                "config": {
                    "pricing_mode": "flat",
                    "pricing_cents": {"flat": 0},
                    "max_input_tokens": max_input_tokens,
                    "max_output_tokens": max_output_tokens,
                    "supports_fast_mode": True,
                    "supports_thinking_mode": True,
                },
            }
        ]
    if is_ollama_image_generation_enabled():
        image_model_name = get_ollama_image_generation_model()
        if image_model_name:
            tags.append("TEXT2IMAGE")
            models["text2image"] = [
                {
                    "model_name": image_model_name,
                    "label": f"Ollama Image ({image_model_name})",
                    "config": get_ollama_image_generation_config(),
                }
            ]
    return {
        "code": "ollama",
        "name": "Ollama",
        "author": "Ollama",
        "description": "Local multimodal model served through an OpenAI-compatible Ollama endpoint.",
        "logo_url": "/providers/ollama/logo",
        "tags": tags,
        "is_builtin": True,
        "credential_types": [],
        "models": models,
    }


LINGYAAI_BUILTIN_MODELS: dict[str, list[dict]] = {
    "text2image": [
        {
            "model_name": "nano-banana-2",
            "label": "NanoBanana2",
            "config": {
                "request_profile": "lingyaai_nano_banana_image",
                "allowed_sizes": ["1K", "2K", "4K"],
                "allowed_aspect_ratios": ["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "4:5", "5:4", "21:9"],
                "supports_reference_image": True,
                "max_reference_images": 14,
            },
        },
        {
            "model_name": "nano-banana-pro",
            "label": "Nano Banana Pro",
            "config": {
                "request_profile": "lingyaai_nano_banana_image",
                "allowed_sizes": ["1K", "2K", "4K"],
                "allowed_aspect_ratios": ["auto", "1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "4:5", "5:4", "21:9"],
                "supports_reference_image": True,
                "max_reference_images": 14,
            },
        },
        {
            "model_name": "gpt-image-2",
            "label": "GPT-Image 2",
            "config": {
                "request_profile": "lingyaai_gpt_image",
                "allowed_sizes": ["1K", "2K", "4K"],
                "allowed_aspect_ratios": ["auto", "1:1", "9:16", "16:9", "4:3", "3:4"],
                "supports_reference_image": True,
                "max_reference_images": 16,
            },
        },
        {
            "model_name": "doubao-seedream-4-5-251128",
            "label": "Seedream 4.5",
            "config": {
                "request_profile": "lingyaai_seedream_image",
                "allowed_sizes": ["2K", "4K"],
                "allowed_aspect_ratios": [],
                "supports_reference_image": True,
                "max_reference_images": 10,
            },
        },
        {
            "model_name": "doubao-seedream-5-0-260128",
            "label": "Seedream 5.0 Lite",
            "config": {
                "request_profile": "lingyaai_seedream_image",
                "allowed_sizes": ["2K"],
                "allowed_aspect_ratios": [],
                "supports_reference_image": True,
                "max_reference_images": 10,
            },
        },
    ],
    "text2video": [
        {
            "model_name": "doubao-seedance-2-0-260128",
            "label": "Seedance 2.0",
            "config": {
                "request_profile": "lingyaai_seedance2_video",
                "min_duration": 4,
                "max_duration": 15,
                "allowed_aspect_ratios": ["adaptive", "16:9", "4:3", "1:1", "3:4", "9:16", "21:9"],
                "allowed_sizes": ["480p", "720p", "1080p"],
                "supports_reference_image": True,
                "supports_reference_image_list": True,
                "supports_first_frame": True,
                "supports_tail_frame": True,
                "supports_audio": True,
                "supports_reference_video": False,
                "supports_reference_audio": False,
                "supports_return_last_frame": True,
                "image_modes_conflict": True,
                "max_image_inputs": 9,
            },
        },
        {
            "model_name": "doubao-seedance-1-5-pro-251215",
            "label": "Seedance 1.5 Pro",
            "config": {
                "request_profile": "lingyaai_seedance15_video",
                "min_duration": 4,
                "max_duration": 12,
                "allowed_aspect_ratios": ["adaptive", "16:9", "9:16", "1:1", "4:3", "3:4", "21:9"],
                "allowed_sizes": ["720p", "1080p"],
                "supports_reference_image": True,
                "supports_first_frame": True,
                "supports_tail_frame": True,
                "supports_audio": False,
                "supports_reference_video": False,
                "supports_reference_audio": False,
                "disallow_reference_mode": True,
                "max_image_inputs": 2,
            },
        },
        {
            "model_name": "kling-v3-video-generation",
            "label": "Kling 3",
            "config": {
                "request_profile": "lingyaai_kling3_video",
                "min_duration": 3,
                "max_duration": 15,
                "allowed_aspect_ratios": ["16:9", "9:16", "1:1"],
                "allowed_sizes": ["720p", "1080p"],
                "supports_kling_mode": True,
                "supports_reference_image": True,
                "supports_first_frame": True,
                "supports_tail_frame": True,
                "supports_audio": True,
                "supports_reference_video": False,
                "supports_reference_audio": False,
                "supports_multi_shot": True,
                "max_image_inputs": 2,
            },
        },
    ],
    "multimodal": [
        {
            "model_name": "gemini-3.1-pro-preview",
            "label": "Gemini 3.1 Pro",
            "config": _multimodal_config(
                input_price=0,
                output_price=0,
                max_input_tokens=1048576,
                max_output_tokens=65536,
                supports_fast_mode=True,
                supports_thinking_mode=False,
            ) | {"request_profile": "lingyaai_chat", "omit_temperature": True},
        },
        {
            "model_name": "gemini-3.1-pro-preview-thinking",
            "label": "Gemini 3.1 Pro Thinking",
            "config": _multimodal_config(
                input_price=0,
                output_price=0,
                max_input_tokens=1048576,
                max_output_tokens=65536,
                supports_fast_mode=False,
                supports_thinking_mode=True,
                thinking_variant_of="gemini-3.1-pro-preview",
            ) | {"request_profile": "lingyaai_chat", "omit_temperature": True},
        },
        {
            "model_name": "claude-opus-4-7",
            "label": "Opus 4.7",
            "config": _multimodal_config(
                input_price=0,
                output_price=0,
                max_input_tokens=1000000,
                max_output_tokens=128000,
                supports_fast_mode=True,
                supports_thinking_mode=False,
            ) | {"request_profile": "lingyaai_chat", "omit_temperature": True},
        },
        {
            "model_name": "claude-opus-4-6-thinking",
            "label": "Opus 4.6 Thinking",
            "config": _multimodal_config(
                input_price=0,
                output_price=0,
                max_input_tokens=1000000,
                max_output_tokens=128000,
                supports_fast_mode=False,
                supports_thinking_mode=True,
                thinking_variant_of="claude-opus-4-7",
            ) | {"request_profile": "lingyaai_chat", "omit_temperature": True},
        },
        {
            "model_name": "deepseek-v4-pro",
            "label": "DeepSeek V4 Pro",
            "config": _multimodal_config(
                input_price=0,
                output_price=0,
                max_input_tokens=1048576,
                max_output_tokens=128000,
                supports_fast_mode=True,
                supports_thinking_mode=False,
            ) | {"request_profile": "lingyaai_chat"},
        },
        {
            "model_name": "glm-5.1",
            "label": "GLM 5.1",
            "config": _multimodal_config(
                input_price=0,
                output_price=0,
                max_input_tokens=204800,
                max_output_tokens=128000,
                supports_fast_mode=True,
                supports_thinking_mode=False,
            ) | {"request_profile": "lingyaai_chat"},
        },
        {
            "model_name": "glm-5-thinking",
            "label": "GLM 5 think",
            "config": _multimodal_config(
                input_price=0,
                output_price=0,
                max_input_tokens=204800,
                max_output_tokens=128000,
                supports_fast_mode=False,
                supports_thinking_mode=True,
                thinking_variant_of="glm-5.1",
            ) | {"request_profile": "lingyaai_chat"},
        },
        {
            "model_name": "kimi-k2.6",
            "label": "Kimi K2.6",
            "config": _multimodal_config(
                input_price=0,
                output_price=0,
                max_input_tokens=262144,
                max_output_tokens=262144,
                supports_fast_mode=True,
                supports_thinking_mode=False,
            ) | {"request_profile": "lingyaai_chat", "context_compression": True},
        },
        {
            "model_name": "kimi-k2.6-thinking",
            "label": "Kimi K2.6 think",
            "config": _multimodal_config(
                input_price=0,
                output_price=0,
                max_input_tokens=262144,
                max_output_tokens=262144,
                supports_fast_mode=False,
                supports_thinking_mode=True,
                thinking_variant_of="kimi-k2.6",
            ) | {"request_profile": "lingyaai_chat"},
        },
    ],
}


BUILTIN_PROVIDER_MODEL_NAME_ALIASES: dict[str, dict[str, dict[str, str]]] = {
    "apimart": {
        "text2image": {
            "nano-banana-2": "gemini-3.1-flash-image-preview",
            "nano-banana-pro": "gemini-3-pro-image-preview",
            "gemini-3.1-flash-image-preview-official": "gemini-3.1-flash-image-preview",
            "gemini-3-pro-image-preview-official": "gemini-3-pro-image-preview",
            "doubao-seedream-4-5-251128": "doubao-seedream-4-5",
            "doubao-seedream-5-0-260128": "doubao-seedream-5-0-lite",
        },
        "text2video": {
            "doubao-seedance-2-0-260128": "doubao-seedance-2.0",
            "doubao-seedance-1-5-pro-251215": "doubao-seedance-1-5-pro",
            "kling-v3-video-generation": "kling-v3",
        },
        "multimodal": {
            "gemini-3.1-pro-preview-thinking": "gemini-3-pro-preview-thinking",
            "kimi-k2.6": "kimi-k2.5",
        },
    },
    "lingyaai": {
        "text2image": {
            "gemini-3.1-flash-image-preview-official": "nano-banana-2",
            "gemini-3-pro-image-preview-official": "nano-banana-pro",
            "gemini-3.1-flash-image-preview": "nano-banana-2",
            "gemini-3-pro-image-preview": "nano-banana-pro",
            "doubao-seedream-4-5": "doubao-seedream-4-5-251128",
            "doubao-seedream-5-0-lite": "doubao-seedream-5-0-260128",
        },
        "text2video": {
            "doubao-seedance-2.0": "doubao-seedance-2-0-260128",
            "doubao-seedance-1-5-pro": "doubao-seedance-1-5-pro-251215",
            "kling-v3": "kling-v3-video-generation",
        },
        "multimodal": {
            "gemini-3-pro-preview-thinking": "gemini-3.1-pro-preview-thinking",
            "kimi-k2.5": "kimi-k2.6",
        },
    },
}


def get_active_builtin_provider_code() -> str:
    # APIMart is the only built-in provider in the per-user-key runtime.
    return "apimart"


def resolve_builtin_model_name_for_provider(
    bucket: str,
    model_name: str,
    *,
    builtin_provider_code: str | None = None,
) -> str:
    provider_code = builtin_provider_code if builtin_provider_code in {"apimart", "lingyaai"} else get_active_builtin_provider_code()
    return BUILTIN_PROVIDER_MODEL_NAME_ALIASES.get(provider_code, {}).get(bucket, {}).get(model_name, model_name)


def build_provider_registry() -> dict[str, dict]:
    registry = deepcopy(PROVIDER_REGISTRY)
    if is_ollama_multimodal_enabled() or is_ollama_image_generation_enabled():
        registry["ollama"] = _build_ollama_provider()
    return registry


def get_builtin_multimodal_models() -> set[str]:
    return {
        entry["model_name"]
        for entry in build_provider_registry()["builtin"]["models"]["multimodal"]
    }


def get_builtin_multimodal_model_entry(model_name: str) -> dict | None:
    for entry in build_provider_registry()["builtin"]["models"]["multimodal"]:
        if entry["model_name"] == model_name:
            return entry
    return None


def get_context_compression_model_entry() -> dict | None:
    for entry in build_provider_registry()["builtin"]["models"]["multimodal"]:
        config = entry.get("config") if isinstance(entry, dict) else None
        if isinstance(config, dict) and config.get("context_compression") is True:
            return entry
    models = build_provider_registry()["builtin"]["models"].get("multimodal") or []
    return models[0] if models else None
