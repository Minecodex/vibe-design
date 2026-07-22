"""KlingAI API client — Python port of the Go reference implementation.

Supports:
- text2image (submit + query)
- text2video (submit + query)
- image2video (submit + query)

Auth: JWT (HS256) with ak/sk.
Base URL: https://api-beijing.klingai.com
"""

import time
import httpx
import jwt

DEFAULT_KLING_IMAGE_MODEL = "kling-v2-1"
DEFAULT_KLING_VIDEO_MODEL = "kling-v2-6"


class KlingAIClient:
    BASE_URL = "https://api-beijing.klingai.com"

    def __init__(self, access_key: str, secret_key: str):
        self.ak = access_key
        self.sk = secret_key

    def _encode_jwt_token(self) -> str:
        now = int(time.time())
        payload = {
            "iss": self.ak,
            "exp": now + 1800,
            "nbf": now - 5,
        }
        token = jwt.encode(payload, self.sk, algorithm="HS256", headers={"typ": "JWT"})
        return token

    async def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        token = self._encode_jwt_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        url = f"{self.BASE_URL}{path}"
        async with httpx.AsyncClient(timeout=30) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            else:
                resp = await client.post(url, headers=headers, json=body or {})
            
            if not resp.is_success:
                try:
                    err_data = resp.json()
                    err_msg = err_data.get("message") or err_data.get("msg") or resp.text
                except Exception:
                    err_msg = resp.text
                    
                if resp.status_code == 429:
                    raise RuntimeError(f"并发请求受限(429): 当前有生成任务正在进行，请稍后重试。详情: {err_msg}")
                else:
                    raise RuntimeError(f"Kling API 请求失败({resp.status_code}): {err_msg}")
                    
            return resp.json()

    # ===================== Image Generation =====================

    async def generate_image(
        self,
        prompt: str,
        model_name: str = DEFAULT_KLING_IMAGE_MODEL,
        aspect_ratio: str = "1:1",
        n: int = 1,
        image: str | None = None,
        image_reference: str | None = None,
    ) -> dict:
        body: dict = {
            "model_name": model_name,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "n": n,
        }
        if image:
            body["image"] = image
            body["image_reference"] = image_reference or "subject"
        return await self._request("POST", "/v1/images/generations", body)

    async def query_image(self, task_id: str) -> dict:
        return await self._request("GET", f"/v1/images/generations/{task_id}")

    # ===================== Video Generation (text2video) =====================

    async def generate_video(
        self,
        prompt: str,
        model_name: str = DEFAULT_KLING_VIDEO_MODEL,
        aspect_ratio: str = "16:9",
        duration: int = 5,
        mode: str = "pro",
    ) -> dict:
        body = {
            "model_name": model_name,
            "prompt": prompt,
            "mode": mode,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
        }
        return await self._request("POST", "/v1/videos/text2video", body)

    async def query_video(self, task_id: str) -> dict:
        return await self._request("GET", f"/v1/videos/text2video/{task_id}")

    # ===================== Video Generation (image2video) =====================

    async def image_to_video(
        self,
        prompt: str,
        image: str,
        model_name: str = DEFAULT_KLING_VIDEO_MODEL,
        duration: int = 5,
        mode: str = "pro",
        image_tail: str | None = None,
    ) -> dict:
        body: dict = {
            "model_name": model_name,
            "prompt": prompt,
            "image": image,
            "mode": mode,
            "duration": duration,
        }
        if image_tail:
            body["image_tail"] = image_tail
        return await self._request("POST", "/v1/videos/image2video", body)

    async def query_image_to_video(self, task_id: str) -> dict:
        return await self._request("GET", f"/v1/videos/image2video/{task_id}")
