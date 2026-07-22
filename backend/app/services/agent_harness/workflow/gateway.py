from __future__ import annotations

import uuid
import time
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import asyncio

from app.db.session import AsyncSessionLocal
from app.services.billing_service import BillingService
from app.services.agent_harness.runtime.blob_artifacts import promote_large_tool_result
from app.services.agent_harness.runtime.eventing.event_log import append_event_async
from app.services.agent_harness.runtime.eventing.conversation_event_fanout import publish_runtime_notification
from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event_async
from app.services.agent_harness.workspace.session_v2.service import (
    append_message_async,
    get_conversation_async,
    get_latest_assistant_message_async,
    get_message_async,
    normalize_message_id,
    update_message_async,
    update_conversation_async,
    upsert_workspace_file,
)
from .contracts import BillingSpec, BlobSpec, EventSpec, MessageSpec, NotificationSpec, StepSpec, WorkspaceFileSpec
from .diagnostics import log_activity_slow, log_event_fanout_slow
from .repositories import (
    complete_step_async,
    enqueue_step_async,
    get_run_parent_usage_log_id_async,
    record_activity_async,
    update_step_checkpoint_async,
)

class SystemPublishStepCollision(RuntimeError):
    pass


class DirectDisplayMessageNotAllowed(RuntimeError):
    pass


class AgentRuntimeGateway:
    def __init__(self, *, user_id: int, conversation_id: str, run_id: str, step_id: str) -> None:
        self.user_id = int(user_id)
        self.conversation_id = str(conversation_id)
        self.run_id = str(run_id)
        self.step_id = str(step_id)

    async def append_event(self, spec: EventSpec) -> dict[str, Any]:
        key = spec.idempotency_key or f"run:{self.run_id}:step:{self.step_id}:event:{spec.event_type}:{uuid.uuid4().hex[:8]}"
        started = time.perf_counter()
        if str(spec.lane or "user") == "user":
            event = await publish_user_event_async(
                self.user_id,
                self.conversation_id,
                run_id=self.run_id,
                event_type=spec.event_type,
                data=deepcopy(spec.payload),
                lane=spec.lane,
                block_id=spec.block_id,
                tool_call_id=spec.tool_call_id,
                artifact_id=spec.artifact_id,
                parent_block_id=spec.parent_block_id,
                idempotency_key=key,
            )
        else:
            event = await append_event_async(
                self.user_id,
                self.conversation_id,
                run_id=self.run_id,
                event_type=spec.event_type,
                payload=deepcopy(spec.payload),
                lane=spec.lane,
                block_id=spec.block_id,
                tool_call_id=spec.tool_call_id,
                artifact_id=spec.artifact_id,
                parent_block_id=spec.parent_block_id,
                idempotency_key=key,
            )
        log_event_fanout_slow(
            event_type=spec.event_type,
            sequence=event.get("sequence") if isinstance(event, dict) else None,
            publish_elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )
        return event

    async def append_message(self, spec: MessageSpec) -> dict[str, Any]:
        message_id = normalize_message_id(spec.idempotency_key or uuid.uuid4().hex[:8])
        existing = await get_message_async(self.user_id, self.conversation_id, message_id)
        if existing is not None:
            return existing
        if not _is_v2_direct_message_allowed(spec):
            raise DirectDisplayMessageNotAllowed(
                "user-visible messages must be projected from presentation events"
            )
        message = {
            "id": message_id,
            "role": spec.role,
            "content": spec.content,
            "blocks": deepcopy(spec.blocks),
            "tool_calls": deepcopy(spec.tool_calls),
            "attachments": deepcopy(spec.attachments),
            "created_at": spec.created_at,
            "streaming": bool(spec.streaming),
            "metadata": deepcopy(spec.metadata or {}),
        }
        if message["blocks"] is None:
            message.pop("blocks")
        if message["tool_calls"] is None:
            message.pop("tool_calls")
        if message["attachments"] is None:
            message.pop("attachments")
        if message["created_at"] is None:
            message.pop("created_at")
        return await append_message_async(self.user_id, self.conversation_id, message)

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        normalized_id = normalize_message_id(message_id)
        if not normalized_id:
            return None
        return await get_message_async(self.user_id, self.conversation_id, normalized_id)

    async def get_latest_assistant_message(self) -> dict[str, Any] | None:
        return await get_latest_assistant_message_async(self.user_id, self.conversation_id)

    async def update_message(
        self,
        *,
        message_id: str,
        content: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        streaming: bool | None = None,
    ) -> dict[str, Any] | None:
        kwargs: dict[str, Any] = {}
        if content is not None:
            kwargs["content"] = content
        if blocks is not None:
            kwargs["blocks"] = deepcopy(blocks)
        if tool_calls is not None:
            kwargs["tool_calls"] = deepcopy(tool_calls)
        if metadata is not None:
            kwargs["metadata"] = deepcopy(metadata)
        if streaming is not None:
            kwargs["streaming"] = bool(streaming)
        if not kwargs:
            return None
        return await update_message_async(
            self.user_id,
            self.conversation_id,
            message_id=normalize_message_id(message_id),
            **kwargs,
        )

    async def update_runtime_snapshot(self, runtime_patch: dict[str, Any]) -> None:
        if runtime_patch:
            conversation = await get_conversation_async(self.user_id, self.conversation_id) or {}
            existing_snapshot = conversation.get("runtime_snapshot")
            if not isinstance(existing_snapshot, dict):
                existing_snapshot = conversation.get("runtime_snapshot_json")
            if not isinstance(existing_snapshot, dict):
                runtime_state = conversation.get("runtime_state")
                existing_snapshot = {"runtime_state": runtime_state} if isinstance(runtime_state, dict) else {}
            merged_snapshot = _merge_snapshot(
                deepcopy(existing_snapshot) if isinstance(existing_snapshot, dict) else {},
                deepcopy(runtime_patch),
            )
            merged_snapshot = _sync_runtime_contract_into_state(merged_snapshot)
            updates = {
                key: value for key, value in merged_snapshot.items() if key in {
                    "phase",
                    "runtime_status",
                    "run_state",
                    "turn_status",
                    "activity",
                    "last_error_summary",
                    "user_interaction",
                    "plan_state",
                    "outline_runtime",
                    "failure",
                    "design_system_id",
                }
            }
            updates["runtime_snapshot_json"] = merged_snapshot
            await update_conversation_async(
                self.user_id,
                self.conversation_id,
                updates,
            )
            try:
                from app.services.agent_harness.workspace.session_v2.db_store import invalidate_active_run_state_cache

                invalidate_active_run_state_cache(self.conversation_id)
            except Exception:
                pass

    async def enqueue_step(self, spec: StepSpec):
        step = await enqueue_step_async(
            run_id=self.run_id,
            user_id=self.user_id,
            conversation_id=self.conversation_id,
            spec=spec,
        )
        expected_key = f"run:{self.run_id}:system-publish-output:execute"
        if spec.idempotency_key == expected_key:
            tool_calls = list((step.input or {}).get("tool_calls") or [])
            tool_call = dict(tool_calls[0] or {}) if tool_calls else {}
            if str(tool_call.get("id") or "") != f"system_publish:{self.run_id}":
                raise SystemPublishStepCollision(
                    "System publish step idempotency key resolved to a non-system publish step."
                )
        return step

    async def complete_step(self, step_id: str, *, claim_token: str, status: str, **kwargs: Any):
        return await complete_step_async(step_id, claim_token=claim_token, status=status, **kwargs)

    async def update_step_checkpoint(self, *, claim_token: str, patch: dict[str, Any]):
        return await update_step_checkpoint_async(self.step_id, claim_token=claim_token, patch=patch)

    async def record_activity(self, **kwargs: Any) -> None:
        await record_activity_async(
            run_id=self.run_id,
            step_id=self.step_id,
            conversation_id=self.conversation_id,
            **kwargs,
        )
        log_activity_slow(
            activity_type=str(kwargs.get("activity_type") or ""),
            activity_id=str(kwargs.get("activity_id") or ""),
            step_id=self.step_id,
            elapsed_ms=kwargs.get("elapsed_ms"),
        )

    async def record_billing(self, spec: BillingSpec) -> dict[str, Any]:
        parent_id = spec.parent_id
        if parent_id is None:
            parent_id = await get_run_parent_usage_log_id_async(self.run_id)
        async with AsyncSessionLocal() as db:
            log = await BillingService(db).create_usage_log(
                user_id=self.user_id,
                task_id=None,
                model_name=spec.model_name,
                model_label=spec.model_label,
                task_type=spec.task_type,
                amount_cents=int(spec.amount_cents or 0),
                parent_id=parent_id,
                billing_key=spec.billing_key,
                params={
                    **deepcopy(spec.params or {}),
                    "agent_run_id": self.run_id,
                    "workflow_step_id": self.step_id,
                },
                task_status=spec.task_status,
                billing_label=spec.billing_label,
                elapsed_ms=spec.elapsed_ms,
                provider_code=spec.provider_code,
                provider_request_id=spec.provider_request_id,
                provider_trace_id=spec.provider_trace_id,
                provider_task_id=spec.provider_task_id,
                billing_mode=spec.billing_mode,
                return_created=False,
            )
            return {"id": getattr(log, "id", None), "status": getattr(log, "status", None)}

    async def refresh_parent_usage_log(self, *, status: str = "success") -> None:
        parent_id = await get_run_parent_usage_log_id_async(self.run_id)
        if parent_id is None:
            return
        async with AsyncSessionLocal() as db:
            await BillingService(db).refresh_parent_usage_log(
                int(parent_id),
                status_override=str(status or "success"),
                finished_at=datetime.now(UTC),
            )

    async def publish_notification(self, spec: NotificationSpec | None = None) -> None:
        _spec = spec or NotificationSpec()
        if _spec.kind == "runtime":
            await publish_runtime_notification(self.user_id, self.conversation_id)

    async def write_blob(self, spec: BlobSpec) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if spec.threshold_chars is not None:
            kwargs["threshold_chars"] = int(spec.threshold_chars)
        return await asyncio.to_thread(
            promote_large_tool_result,
            self.user_id,
            self.conversation_id,
            tool_call_id=spec.tool_call_id,
            tool_name=spec.tool_name,
            content=spec.content,
            **kwargs,
        )

    async def update_workspace_file(self, spec: WorkspaceFileSpec) -> None:
        await asyncio.to_thread(
            upsert_workspace_file,
            self.user_id,
            self.conversation_id,
            deepcopy(spec.file),
        )


def _merge_snapshot(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_snapshot(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _sync_runtime_contract_into_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    runtime_contract = snapshot.get("runtime_contract")
    if not isinstance(runtime_contract, dict):
        return snapshot
    merged = dict(snapshot)
    runtime_state = dict(merged.get("runtime_state") or {}) if isinstance(merged.get("runtime_state"), dict) else {}
    existing_contract = runtime_state.get("runtime_contract")
    runtime_state["runtime_contract"] = _merge_snapshot(
        dict(existing_contract) if isinstance(existing_contract, dict) else {},
        deepcopy(runtime_contract),
    )
    merged["runtime_state"] = runtime_state
    return merged


def _is_v2_direct_message_allowed(spec: MessageSpec) -> bool:
    metadata = spec.metadata if isinstance(spec.metadata, dict) else {}
    message_kind = str(metadata.get("message_kind") or "").strip()
    if message_kind == "agent_context":
        return True
    if message_kind.startswith("internal_"):
        return True
    if metadata.get("ui_visible") is False and metadata.get("model_visible") is not False:
        return True
    return False
