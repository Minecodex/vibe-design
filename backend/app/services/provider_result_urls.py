from __future__ import annotations

from typing import Any


def extract_task_result_urls(task_result: dict[str, Any]) -> list[str]:
    result = task_result.get("result", task_result)
    urls: list[str] = []

    for bucket in ("images", "videos"):
        for item in result.get(bucket, []) or []:
            raw_urls = item.get("url", [])
            if isinstance(raw_urls, str):
                raw_urls = [raw_urls]
            urls.extend(url for url in raw_urls if isinstance(url, str) and url)
    return urls
