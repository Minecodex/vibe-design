"""Volcano Ark (火山方舟) API client.

Supports:
- text2image (Doubao-Seedream-5.0-lite) — synchronous
- text2video (Doubao-Seedance-2.0) — asynchronous (create + query)

Auth: Bearer API Key or AK/SK.
Base URL: https://ark.cn-beijing.volces.com/api/v3
"""

import logging

import httpx

logger = logging.getLogger(__name__)

# Aspect-ratio to pixel size mapping for image generation, keyed by resolution tier
VOLCARK_RATIO_TO_SIZE = {
    "2K": {
        "1:1": "2048x2048",
        "4:3": "2304x1728",
        "3:4": "1728x2304",
        "16:9": "2848x1600",
        "9:16": "1600x2848",
        "3:2": "2496x1664",
        "2:3": "1664x2496",
        "21:9": "3136x1344",
    },
    "3K": {
        "1:1": "3072x3072",
        "4:3": "3456x2592",
        "3:4": "2592x3456",
        "16:9": "4096x2304",
        "9:16": "2304x4096",
        "2:3": "2496x3744",
        "3:2": "3744x2496",
        "21:9": "4704x2016",
    },
}


class VolcArkClient:
    BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

    def __init__(self, api_key: str):
        """Initialize with an API key (Bearer token auth)."""
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.BASE_URL}{path}"
        headers = self._headers()

        async with httpx.AsyncClient(timeout=60) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            else:
                resp = await client.post(url, headers=headers, json=body or {})

            if not resp.is_success:
                try:
                    err_data = resp.json()
                    err_msg = (
                        err_data.get("error", {}).get("message")
                        or err_data.get("message")
                        or resp.text
                    )
                except Exception:
                    err_msg = resp.text

                if resp.status_code == 429:
                    raise RuntimeError(
                        f"并发请求受限(429): 当前有生成任务正在进行，请稍后重试。详情: {err_msg}"
                    )
                else:
                    raise RuntimeError(
                        f"Volcano Ark API 请求失败({resp.status_code}): {err_msg}"
                    )

            return resp.json()

    # ===================== Image Generation =====================

    async def generate_image(
        self,
        prompt: str,
        endpoint_id: str,
        aspect_ratio: str = "1:1",
        resolution: str = "2K",
    ) -> dict:
        """Generate image using Seedream model.

        This is a synchronous API — it returns the image URL directly.
        """
        res_map = VOLCARK_RATIO_TO_SIZE.get(resolution, VOLCARK_RATIO_TO_SIZE["2K"])
        size = res_map.get(aspect_ratio, "2048x2048")
        body = {
            "model": endpoint_id,
            "prompt": prompt,
            "size": size,
        }
        return await self._request("POST", "/images/generations", body)

    # ===================== Video Generation =====================

    async def create_video_task(
        self,
        prompt: str,
        endpoint_id: str,
        aspect_ratio: str = "16:9",
        duration: int = 5,
    ) -> dict:
        """Create an asynchronous video generation task."""
        body: dict = {
            "model": endpoint_id,
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                }
            ],
        }
        if aspect_ratio:
            body["ratio"] = aspect_ratio
        if duration:
            body["duration"] = duration
        return await self._request("POST", "/contents/generations/tasks", body)

    async def query_video_task(self, task_id: str) -> dict:
        """Query the status of a video generation task."""
        return await self._request("GET", f"/contents/generations/tasks/{task_id}")
