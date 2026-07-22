"""Jimeng (即梦) API client — Python port of the Go reference implementation.

Supports:
- text2image (submit + query)
- text2video (submit + query)

Auth: HMAC-SHA256 signing (volcengine style).
Base URL: https://visual.volcengineapi.com
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import quote

import httpx


class JimengSigner:
    """Volcengine-style HMAC-SHA256 request signer."""

    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        service: str = "cv",
        region: str = "cn-north-1",
        host: str = "visual.volcengineapi.com",
        path: str = "/",
    ):
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.service = service
        self.region = region
        self.host = host
        self.path = path

    def sign(
        self,
        method: str,
        query_params: dict[str, str],
        body: bytes,
        body_type: str = "json",
    ) -> dict[str, str]:
        now = datetime.now(timezone.utc)
        x_date = now.strftime("%Y%m%dT%H%M%SZ")
        short_date = x_date[:8]

        # Body hash
        body_hash = hashlib.sha256(body).hexdigest() if body else hashlib.sha256(b"").hexdigest()

        # Headers
        content_type = (
            "application/json"
            if body_type == "json"
            else "application/x-www-form-urlencoded"
        )
        headers = {
            "host": self.host,
            "x-date": x_date,
            "x-content-sha256": body_hash,
            "content-type": content_type,
        }

        # Canonical request
        canonical_request, signed_headers = self._build_canonical_request(
            method, query_params, headers, body_hash
        )

        # String to sign
        hashed_canonical = hashlib.sha256(canonical_request.encode()).hexdigest()
        credential_scope = f"{short_date}/{self.region}/{self.service}/request"
        string_to_sign = f"HMAC-SHA256\n{x_date}\n{credential_scope}\n{hashed_canonical}"

        # Signing key
        signing_key = self._derive_signing_key(short_date)

        # Signature
        signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

        # Authorization header
        authorization = (
            f"HMAC-SHA256 Credential={self.access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        return {
            "Authorization": authorization,
            "X-Date": x_date,
            "Content-Type": content_type,
            "X-Content-Sha256": body_hash,
        }

    def _build_canonical_request(
        self,
        method: str,
        query_params: dict[str, str],
        headers: dict[str, str],
        body_hash: str,
    ) -> tuple[str, str]:
        # Method
        canonical = method.upper() + "\n"
        # URI
        canonical += self.path + "\n"
        # Query string
        canonical += self._build_canonical_query_string(query_params) + "\n"
        # Headers
        header_keys = sorted(headers.keys())
        for key in header_keys:
            canonical += f"{key}:{headers[key].strip()}\n"
        canonical += "\n"
        # Signed headers
        signed_headers = ";".join(header_keys)
        canonical += signed_headers + "\n"
        # Body hash
        canonical += body_hash
        return canonical, signed_headers

    @staticmethod
    def _build_canonical_query_string(params: dict[str, str]) -> str:
        if not params:
            return ""
        encoded = {}
        for k, v in params.items():
            ek = quote(k, safe="").replace("+", "%20")
            ev = quote(v, safe="").replace("+", "%20")
            encoded[ek] = ev
        return "&".join(f"{k}={encoded[k]}" for k in sorted(encoded))

    def _derive_signing_key(self, date: str) -> bytes:
        k_date = hmac.new(
            self.secret_access_key.encode(), date.encode(), hashlib.sha256
        ).digest()
        k_region = hmac.new(k_date, self.region.encode(), hashlib.sha256).digest()
        k_service = hmac.new(k_region, self.service.encode(), hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b"request", hashlib.sha256).digest()
        return k_signing


class JimengClient:
    BASE_URL = "https://visual.volcengineapi.com"

    def __init__(self, access_key: str, secret_key: str):
        self.ak = access_key
        self.sk = secret_key
        self.signer = JimengSigner(
            access_key_id=access_key,
            secret_access_key=secret_key,
        )

    async def _request(
        self, action: str, body_dict: dict
    ) -> dict:
        body_bytes = json.dumps(body_dict).encode()
        query_params = {"Action": action, "Version": "2022-08-31"}

        sign_headers = self.signer.sign("POST", query_params, body_bytes)
        url = f"{self.BASE_URL}?Action={action}&Version=2022-08-31"

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, content=body_bytes, headers=sign_headers)
            resp.raise_for_status()
            return resp.json()

    # ===================== Image Generation =====================

    async def generate_image(
        self,
        prompt: str,
        req_key: str = "jimeng_t2i_v40",
        width: int = 1024,
        height: int = 1024,
        image_urls: list[str] | None = None,
    ) -> dict:
        body: dict = {
            "req_key": req_key,
            "prompt": prompt,
            "width": width,
            "height": height,
            "return_url": True,
            "logo_info": {"add_logo": False},
        }
        if image_urls:
            body["image_urls"] = image_urls
        return await self._request("CVSync2AsyncSubmitTask", body)

    async def query_image(self, req_key: str, task_id: str) -> dict:
        body = {"req_key": req_key, "task_id": task_id}
        return await self._request("CVSync2AsyncGetResult", body)

    # ===================== Video Generation =====================

    async def generate_video(
        self,
        prompt: str,
        req_key: str = "jimeng_ti2v_v30_pro",
        duration: int = 5,
        aspect_ratio: str = "16:9",
        image_urls: list[str] | None = None,
    ) -> dict:
        frames = duration * 24 + 1
        body: dict = {
            "req_key": req_key,
            "prompt": prompt,
            "frames": frames,
            "aspect_ratio": aspect_ratio,
        }
        if image_urls:
            body["image_urls"] = image_urls
        return await self._request("CVSync2AsyncSubmitTask", body)

    async def query_video(self, req_key: str, task_id: str) -> dict:
        body = {"req_key": req_key, "task_id": task_id}
        return await self._request("CVSync2AsyncGetResult", body)
