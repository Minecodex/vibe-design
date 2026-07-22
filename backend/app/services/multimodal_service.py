"""Multimodal generation service with builtin and Ollama routing."""

import logging
import time
from collections.abc import AsyncGenerator

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing_errors import raise_insufficient_balance
from app.core.config import settings
from app.core.default_models import is_ollama_multimodal_enabled
from app.core.ollama_credentials import get_ollama_multimodal_api_key
from app.core.providers import (
    get_active_builtin_provider_code,
    get_builtin_multimodal_model_entry,
    get_builtin_multimodal_models,
    resolve_builtin_model_name_for_provider,
)
from app.models.user import User
from app.services.apimart_client import ApimartClient
from app.services.billing_service import BillingService
from app.services.builtin_provider import get_active_builtin_provider
from app.services.ollama_client import OllamaClient
from app.services.user_apimart_key_service import UserApimartKeyService

logger = logging.getLogger(__name__)

MULTIMODAL_MODELS = get_builtin_multimodal_models()


def resolve_multimodal_provider(model_name: str, provider_code: str | None = None) -> str:
    if provider_code:
        return provider_code
    if (
        is_ollama_multimodal_enabled()
        and model_name == (settings.OLLAMA_MULTIMODAL_MODEL or "").strip()
    ):
        return "ollama"
    return "builtin"


def is_supported_multimodal_model(model_name: str, provider_code: str | None = None) -> bool:
    resolved_provider = resolve_multimodal_provider(model_name, provider_code)
    if resolved_provider == "ollama":
        return (
            is_ollama_multimodal_enabled()
            and model_name == (settings.OLLAMA_MULTIMODAL_MODEL or "").strip()
        )
    model_name = resolve_builtin_model_name_for_provider("multimodal", model_name)
    return model_name in get_builtin_multimodal_models()


def get_multimodal_model_config(
    model_name: str,
    provider_code: str | None = None,
) -> dict | None:
    resolved_provider = resolve_multimodal_provider(model_name, provider_code)
    if resolved_provider == "ollama":
        return {
            "max_input_tokens": int(settings.OLLAMA_MAX_INPUT_TOKENS or 0),
            "max_output_tokens": int(settings.OLLAMA_MAX_OUTPUT_TOKENS or 0),
            "supports_fast_mode": True,
            "supports_thinking_mode": True,
        }

    model_name = resolve_builtin_model_name_for_provider("multimodal", model_name)
    entry = get_builtin_multimodal_model_entry(model_name)
    if not entry:
        return None
    return entry.get("config", {})


def resolve_effective_max_tokens(
    model_name: str,
    requested_max_tokens: int,
    provider_code: str | None = None,
) -> int:
    config = get_multimodal_model_config(model_name, provider_code)
    if not config:
        logger.warning(
            "No multimodal model config found for %s (provider=%s); leaving max_tokens unchanged",
            model_name,
            provider_code or "auto",
        )
        return requested_max_tokens

    max_output_tokens = int(config.get("max_output_tokens") or 0)
    if max_output_tokens <= 0:
        return requested_max_tokens
    if requested_max_tokens <= 0:
        return max_output_tokens
    return min(requested_max_tokens, max_output_tokens)


class MultimodalService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.last_stream_usage: dict | None = None
        self.last_stream_amount_cents: int = 0
        self.last_stream_elapsed_ms: int = 0

    @staticmethod
    def _extract_error_message(result: dict) -> str:
        if "_status_code" in result and result.get("_status_code") != 200:
            return (
                result.get("error", {}).get("message")
                or result.get("msg")
                or "Unknown error"
            )
        if "error" in result:
            return result["error"].get("message", "Unknown error")
        return ""

    @staticmethod
    def _extract_payload(result: dict) -> dict:
        return result.get("data", result)

    @staticmethod
    def _build_usage_log_params(
        *,
        temperature: float,
        max_tokens: int,
        input_tokens: int,
        output_tokens: int,
        streaming: bool = False,
    ) -> dict:
        params = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
        if streaming:
            params["streaming"] = True
        return params

    @staticmethod
    def _create_builtin_client(api_key: str) -> ApimartClient:
        return ApimartClient(api_key)

    @staticmethod
    def _create_builtin_provider(api_key: str):
        return get_active_builtin_provider(api_key)

    async def _resolve_builtin_key(self, user_id: int) -> tuple[str, int]:
        user = await self.db.get(User, user_id)
        api_key, _ = await UserApimartKeyService(self.db).resolve_key(
            user_id,
            user_role=getattr(user, "role", None),
        )
        return api_key, _

    @staticmethod
    def _create_ollama_client() -> OllamaClient:
        base_url = (settings.OLLAMA_BASE_URL or "").strip()
        if not base_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ollama base URL is not configured",
            )
        return OllamaClient(base_url=base_url, api_key=get_ollama_multimodal_api_key())

    async def chat(
        self,
        user_id: int,
        model_name: str,
        messages: list[dict],
        temperature: float = 1.0,
        max_tokens: int = 0,
        skip_usage_log: bool = False,
        billing_label: str | None = None,
        task_type: str = "multimodal",
        provider_code: str | None = None,
    ) -> dict:
        resolved_provider = resolve_multimodal_provider(model_name, provider_code)
        if resolved_provider == "builtin":
            model_name = resolve_builtin_model_name_for_provider("multimodal", model_name)
        if not is_supported_multimodal_model(model_name, provider_code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的多模态模型: {model_name}",
            )

        effective_max_tokens = resolve_effective_max_tokens(
            model_name,
            max_tokens,
            resolved_provider,
        )
        billing_svc = BillingService(self.db)

        builtin_provider_code = get_active_builtin_provider_code() if resolved_provider == "builtin" else None
        if resolved_provider == "builtin":
            balance_cents = await billing_svc.get_balance(user_id)
            if balance_cents <= 0:
                raise_insufficient_balance(required_cents=1, balance_cents=balance_cents)
            api_key, _credential_id = await self._resolve_builtin_key(user_id)
            client = self._create_builtin_provider(api_key)
        else:
            client = self._create_ollama_client()

        t0 = time.monotonic()
        try:
            result = await client.chat_completions(
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=effective_max_tokens,
            )
        except Exception as exc:
            logger.exception(
                "Chat completions call failed: model=%s provider=%s effective_max_tokens=%s message_count=%s",
                model_name,
                resolved_provider,
                effective_max_tokens,
                len(messages),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"多模态模型调用失败: {str(exc)}",
            )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        err_msg = self._extract_error_message(result)
        if (
            resolved_provider == "builtin"
            and result.get("_status_code") in {401, 403}
            and "_credential_id" in locals()
        ):
            await UserApimartKeyService(self.db).mark_invalid(_credential_id, user_id)
        if err_msg:
            logger.warning(
                "Multimodal provider returned error: model=%s provider=%s effective_max_tokens=%s elapsed_ms=%s error=%s",
                model_name,
                resolved_provider,
                effective_max_tokens,
                elapsed_ms,
                err_msg,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"多模态模型调用失败: {err_msg}",
            )

        data = self._extract_payload(result)
        usage = data.get("usage", {})
        input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)

        cost = 0
        usage_log_params = self._build_usage_log_params(
            temperature=temperature,
            max_tokens=effective_max_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        if resolved_provider == "builtin" and builtin_provider_code == "lingyaai":
            headers = result.get("_provider_headers") if isinstance(result.get("_provider_headers"), dict) else {}
            oneapi_request_id = headers.get("x_oneapi_request_id")
            request_id = headers.get("x_request_id")
            usage["provider_code"] = "lingyaai"
            usage["oneapi_request_id"] = oneapi_request_id
            usage["request_id"] = request_id
            data["usage"] = usage
            if not skip_usage_log:
                await billing_svc.create_provider_reconcile_usage_log(
                    user_id=user_id,
                    task_id=None,
                    model_name=model_name,
                    task_type=task_type,
                    provider_code="lingyaai",
                    provider_request_id=oneapi_request_id,
                    provider_trace_id=request_id,
                    params=usage_log_params,
                    billing_label=billing_label,
                    elapsed_ms=elapsed_ms,
                )
        elif resolved_provider == "builtin":
            cost = billing_svc.calculate_amount(
                model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            if cost > 0:
                ok = await billing_svc.deduct_balance(user_id, cost)
                if not ok:
                    logger.warning(
                        "User %d could not be charged %d cents for %s",
                        user_id,
                        cost,
                        model_name,
                    )
                    cost = 0
        elif resolved_provider == "ollama" and not skip_usage_log:
            await billing_svc.create_usage_log(
                user_id=user_id,
                task_id=None,
                model_name=model_name,
                task_type=task_type,
                amount_cents=0,
                params=usage_log_params,
                task_status="success",
                billing_label=billing_label,
                elapsed_ms=elapsed_ms,
                provider_code="ollama",
                billing_mode="local_zero_cost",
            )

        data["_amount_cents"] = cost
        data["_elapsed_ms"] = elapsed_ms

        if not skip_usage_log and cost > 0 and not (resolved_provider == "builtin" and builtin_provider_code == "lingyaai"):
            await billing_svc.create_usage_log(
                user_id=user_id,
                task_id=None,
                model_name=model_name,
                task_type=task_type,
                amount_cents=cost,
                params=usage_log_params,
                task_status="success",
                billing_label=billing_label,
                elapsed_ms=elapsed_ms,
                provider_code="apimart" if resolved_provider == "builtin" else resolved_provider,
                billing_mode="local_price" if resolved_provider == "builtin" else None,
            )

        return data

    async def chat_stream(
        self,
        user_id: int,
        model_name: str,
        messages: list[dict],
        temperature: float = 1.0,
        max_tokens: int = 0,
        skip_usage_log: bool = False,
        billing_label: str | None = None,
        task_type: str = "multimodal",
        provider_code: str | None = None,
    ) -> AsyncGenerator[str, None]:
        self.last_stream_usage = None
        self.last_stream_amount_cents = 0
        self.last_stream_elapsed_ms = 0

        resolved_provider = resolve_multimodal_provider(model_name, provider_code)
        if resolved_provider == "builtin":
            model_name = resolve_builtin_model_name_for_provider("multimodal", model_name)
        if not is_supported_multimodal_model(model_name, provider_code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的多模态模型: {model_name}",
            )

        effective_max_tokens = resolve_effective_max_tokens(
            model_name,
            max_tokens,
            resolved_provider,
        )
        billing_svc = BillingService(self.db)

        builtin_provider_code = get_active_builtin_provider_code() if resolved_provider == "builtin" else None
        if resolved_provider == "builtin" and builtin_provider_code == "lingyaai":
            pre_cost = 0
            balance_cents = await billing_svc.get_balance(user_id)
            if balance_cents <= 0:
                raise_insufficient_balance(required_cents=1, balance_cents=balance_cents)
            api_key, _credential_id = await self._resolve_builtin_key(user_id)
            client = self._create_builtin_provider(api_key)
        elif resolved_provider == "builtin":
            pre_cost = 1
            balance_cents = await billing_svc.get_balance(user_id)
            ok = await billing_svc.deduct_balance(user_id, pre_cost)
            if not ok:
                raise_insufficient_balance(required_cents=pre_cost, balance_cents=balance_cents)
            api_key, _credential_id = await self._resolve_builtin_key(user_id)
            client = self._create_builtin_client(api_key)
        else:
            pre_cost = 0
            client = self._create_ollama_client()

        t0 = time.monotonic()
        try:
            async for chunk in client.chat_completions_stream(
                model_name=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=effective_max_tokens,
            ):
                yield chunk
        except Exception as exc:
            if (
                resolved_provider == "builtin"
                and getattr(exc, "status_code", None) in {401, 403}
                and "_credential_id" in locals()
            ):
                await UserApimartKeyService(self.db).mark_invalid(_credential_id, user_id)
            if resolved_provider == "builtin" and pre_cost > 0:
                await billing_svc.refund_balance(user_id, pre_cost)
            logger.exception("Chat completions streaming failed")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"多模态模型流式调用失败: {str(exc)}",
            )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        raw_usage = getattr(client, "last_stream_usage", {}) or {}
        input_tokens = int(raw_usage.get("prompt_tokens") or raw_usage.get("input_tokens") or 0)
        output_tokens = int(raw_usage.get("completion_tokens") or raw_usage.get("output_tokens") or 0)

        cost = 0
        usage_log_params = self._build_usage_log_params(
            temperature=temperature,
            max_tokens=effective_max_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            streaming=True,
        )
        if resolved_provider == "builtin" and builtin_provider_code == "lingyaai":
            headers = getattr(client, "last_stream_provider_headers", {}) or {}
            oneapi_request_id = headers.get("x_oneapi_request_id")
            request_id = headers.get("x_request_id")
            if not skip_usage_log:
                await billing_svc.create_provider_reconcile_usage_log(
                    user_id=user_id,
                    task_id=None,
                    model_name=model_name,
                    task_type=task_type,
                    provider_code="lingyaai",
                    provider_request_id=oneapi_request_id,
                    provider_trace_id=request_id,
                    params=usage_log_params,
                    billing_label=billing_label,
                    elapsed_ms=elapsed_ms,
                )
        elif resolved_provider == "builtin":
            cost = (
                billing_svc.calculate_amount(
                    model_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                if raw_usage
                else pre_cost
            )

            if cost > pre_cost:
                extra_cost = cost - pre_cost
                ok = await billing_svc.deduct_balance(user_id, extra_cost)
                if not ok:
                    logger.warning(
                        "User %d could not be charged extra %d cents for streamed %s",
                        user_id,
                        extra_cost,
                        model_name,
                    )
                    cost = pre_cost
            elif cost < pre_cost:
                await billing_svc.refund_balance(user_id, pre_cost - cost)

        self.last_stream_usage = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
        }
        if resolved_provider == "builtin" and builtin_provider_code == "lingyaai":
            self.last_stream_usage.update({
                "provider_code": "lingyaai",
                "oneapi_request_id": oneapi_request_id,
                "request_id": request_id,
            })
        self.last_stream_amount_cents = cost
        self.last_stream_elapsed_ms = elapsed_ms

        if not skip_usage_log and cost > 0 and not (resolved_provider == "builtin" and builtin_provider_code == "lingyaai"):
            await billing_svc.create_usage_log(
                user_id=user_id,
                task_id=None,
                model_name=model_name,
                task_type=task_type,
                amount_cents=cost,
                params=usage_log_params,
                task_status="success",
                billing_label=billing_label,
                elapsed_ms=elapsed_ms,
                provider_code="apimart" if resolved_provider == "builtin" else resolved_provider,
                billing_mode="local_price" if resolved_provider == "builtin" else None,
            )
