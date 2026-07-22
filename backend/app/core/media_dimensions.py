from __future__ import annotations

from copy import deepcopy
from typing import Any

DimensionTable = dict[str, dict[str, dict[str, int]]]

DIMENSION_SOURCE_APIMART_DOCS = "apimart_docs"
DIMENSION_SOURCE_ESTIMATED = "estimated"
DIMENSION_POLICY_IMAGE_AREA = "image_area"
DIMENSION_POLICY_VIDEO_SHORT_SIDE = "video_short_side"
DIMENSION_POLICY_OLLAMA_GPT_IMAGE_2 = "ollama_gpt_image_2"

GPT_IMAGE_2_DIMENSION_TABLE: DimensionTable = {
    "1K": {
        "1:1": {"width": 1024, "height": 1024},
        "16:9": {"width": 1536, "height": 864},
        "9:16": {"width": 864, "height": 1536},
        "2:1": {"width": 2048, "height": 1024},
        "1:2": {"width": 1024, "height": 2048},
        "4:3": {"width": 1024, "height": 768},
        "3:4": {"width": 768, "height": 1024},
        "3:2": {"width": 1536, "height": 1024},
        "2:3": {"width": 1024, "height": 1536},
        "5:4": {"width": 1280, "height": 1024},
        "4:5": {"width": 1024, "height": 1280},
        "21:9": {"width": 2016, "height": 864},
        "9:21": {"width": 864, "height": 2016},
        "3:1": {"width": 1536, "height": 512},
        "1:3": {"width": 512, "height": 1536},
    },
    "2K": {
        "1:1": {"width": 2048, "height": 2048},
        "16:9": {"width": 2048, "height": 1152},
        "9:16": {"width": 1152, "height": 2048},
        "2:1": {"width": 2688, "height": 1344},
        "1:2": {"width": 1344, "height": 2688},
        "4:3": {"width": 2048, "height": 1536},
        "3:4": {"width": 1536, "height": 2048},
        "3:2": {"width": 2048, "height": 1360},
        "2:3": {"width": 1360, "height": 2048},
        "5:4": {"width": 2560, "height": 2048},
        "4:5": {"width": 2048, "height": 2560},
        "21:9": {"width": 2688, "height": 1152},
        "9:21": {"width": 1152, "height": 2688},
        "3:1": {"width": 3072, "height": 1024},
        "1:3": {"width": 1024, "height": 3072},
    },
    "4K": {
        "1:1": {"width": 2880, "height": 2880},
        "16:9": {"width": 3840, "height": 2160},
        "9:16": {"width": 2160, "height": 3840},
        "2:1": {"width": 3840, "height": 1920},
        "1:2": {"width": 1920, "height": 3840},
        "4:3": {"width": 3312, "height": 2480},
        "3:4": {"width": 2480, "height": 3312},
        "3:2": {"width": 3520, "height": 2336},
        "2:3": {"width": 2336, "height": 3520},
        "5:4": {"width": 3200, "height": 2560},
        "4:5": {"width": 2560, "height": 3200},
        "21:9": {"width": 3840, "height": 1648},
        "9:21": {"width": 1648, "height": 3840},
        "3:1": {"width": 3840, "height": 1280},
        "1:3": {"width": 1280, "height": 3840},
    },
}

SEEDREAM_5_LITE_DIMENSION_TABLE: DimensionTable = {
    "2K": {
        "1:1": {"width": 2048, "height": 2048},
        "4:3": {"width": 2304, "height": 1728},
        "3:4": {"width": 1728, "height": 2304},
        "16:9": {"width": 2848, "height": 1600},
        "9:16": {"width": 1600, "height": 2848},
        "3:2": {"width": 2496, "height": 1664},
        "2:3": {"width": 1664, "height": 2496},
        "21:9": {"width": 3136, "height": 1344},
    },
    "3K": {
        "1:1": {"width": 3072, "height": 3072},
        "4:3": {"width": 3456, "height": 2592},
        "3:4": {"width": 2592, "height": 3456},
        "16:9": {"width": 4096, "height": 2304},
        "9:16": {"width": 2304, "height": 4096},
        "3:2": {"width": 3744, "height": 2496},
        "2:3": {"width": 2496, "height": 3744},
        "21:9": {"width": 4704, "height": 2016},
    },
    "4K": {
        "1:1": {"width": 4096, "height": 4096},
        "4:3": {"width": 4704, "height": 3520},
        "3:4": {"width": 3520, "height": 4704},
        "16:9": {"width": 5504, "height": 3040},
        "9:16": {"width": 3040, "height": 5504},
        "3:2": {"width": 4992, "height": 3328},
        "2:3": {"width": 3328, "height": 4992},
        "21:9": {"width": 6240, "height": 2656},
    },
}


def exact_dimension_config(table: DimensionTable) -> dict[str, Any]:
    return {
        "dimension_table": deepcopy(table),
        "dimension_source": DIMENSION_SOURCE_APIMART_DOCS,
    }


def estimated_image_dimension_config() -> dict[str, str]:
    return {
        "dimension_policy": DIMENSION_POLICY_IMAGE_AREA,
        "dimension_source": DIMENSION_SOURCE_ESTIMATED,
    }


def video_short_side_dimension_config() -> dict[str, str]:
    return {
        "dimension_policy": DIMENSION_POLICY_VIDEO_SHORT_SIDE,
        "dimension_source": DIMENSION_SOURCE_ESTIMATED,
    }


def ollama_gpt_image_2_dimension_config() -> dict[str, str]:
    return {
        "dimension_policy": DIMENSION_POLICY_OLLAMA_GPT_IMAGE_2,
        "dimension_source": DIMENSION_SOURCE_ESTIMATED,
    }
