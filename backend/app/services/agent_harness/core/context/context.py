"""HarnessContext — per-request execution context with workspace isolation."""

from __future__ import annotations

import asyncio
import os
from hashlib import sha256
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable
from weakref import WeakKeyDictionary

from app.core.billing_pricing import get_model_label
from app.core.provider_balance_mode import is_provider_balance_sync_enabled

from app.services.agent_harness.runtime.execution_support.billing import resolve_harness_mode, resolve_harness_mode_label
from app.services.agent_harness.runtime.state.file_state import build_snapshot, snapshot_from_dict, snapshot_to_dict
from app.services.agent_harness.capabilities.tools._internal.base import ToolResult

if TYPE_CHECKING:
    from app.services.agent_harness.runtime.state.conversation_state import ConversationStateSnapshot
    from app.services.agent_harness.capabilities.subagents import SubagentRequest, SubagentResult
    from app.services.agent_harness.runtime.state.runtime_state import RuntimeState
    from app.services.agent_harness.capabilities.skill_protocols.base import PreparedWorkspace
    from app.services.agent_harness.workflow.gateway import AgentRuntimeGateway

_current_context: ContextVar["HarnessContext | None"] = ContextVar(
    "harness_context", default=None
)


def get_current_context() -> "HarnessContext":
    ctx = _current_context.get()
    if ctx is None:
        raise RuntimeError("HarnessContext not set for current task")
    return ctx


def set_current_context(ctx: "HarnessContext") -> Token["HarnessContext | None"]:
    return _current_context.set(ctx)


def reset_current_context(token: Token["HarnessContext | None"]) -> None:
    _current_context.reset(token)


def _is_within_path(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _tool_stream_event_key(
    *,
    run_id: str,
    step_id: str,
    tool_call_id: str,
    event_type: str,
    payload: dict[str, Any],
    sequence: int,
) -> str:
    digest = sha256(repr(sorted(payload.items())).encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"run:{run_id}:step:{step_id}:tool-stream:{tool_call_id}:{event_type}:{sequence}:{digest}"


# ---------------------------------------------------------------------------
# HarnessContext
# ---------------------------------------------------------------------------

@dataclass
class HarnessContext:
    # Identity
    user_id: int
    conversation_id: str
    run_id: str
    language: str = "zh"
    runtime_profile: str = "home"
    project_id: int | None = None

    # Workspace — if None, __post_init__ resolves from settings lazily.
    workspace_root: Path | None = None
    skill_id: str | None = None
    artifact_mode: str = "web"
    design_system_id: str | None = None
    model_preferences: dict[str, Any] = field(default_factory=dict)
    runtime_state: "RuntimeState | None" = None
    history_summary: dict[str, Any] | None = None
    conversation_state: "ConversationStateSnapshot | None" = None

    # Model preferences (populated from conversation.model_preferences)
    image_model: str | None = None
    image_provider: str = "builtin"
    video_model: str | None = None
    video_provider: str = "builtin"
    multimodal_model: str | None = None
    multimodal_provider: str = "builtin"

    # Billing
    parent_usage_log_id: int | None = None
    accumulated_amount_cents: float = 0.0
    billing_breakdown: list[dict] = field(default_factory=list)
    billing_counts: dict[str, int] = field(default_factory=dict)
    billing_models: dict[str, set[str]] = field(default_factory=dict)
    billing_model_stats: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    billing_elapsed_ms: dict[str, int] = field(default_factory=dict)

    # Event queue for streaming
    event_queue: asyncio.Queue | None = None
    runtime_gateway: "AgentRuntimeGateway | None" = None
    _tool_stream_callbacks: WeakKeyDictionary[asyncio.Task[Any], Callable[[str, dict[str, Any]], Awaitable[None]]] = field(
        default_factory=WeakKeyDictionary,
        init=False,
        repr=False,
    )
    _tool_stream_scope: WeakKeyDictionary[asyncio.Task[Any], dict[str, Any]] = field(
        default_factory=WeakKeyDictionary,
        init=False,
        repr=False,
    )
    _tool_stream_sequence: WeakKeyDictionary[asyncio.Task[Any], int] = field(
        default_factory=WeakKeyDictionary,
        init=False,
        repr=False,
    )

    # Callback used by the synchronous Agent tool and internal workflow subagents.
    run_subagent_handler: Callable[
        ["SubagentRequest", "HarnessContext"],
        Awaitable["SubagentResult | ToolResult | Any"],
    ] | None = None

    # Active skill's on-disk directory for command environment exposure.
    # Set by the engine when a skill is selected for this run.
    active_skill_dir: Path | None = None
    skill_runtime_dir: Path | None = None
    prepared_workspace: "PreparedWorkspace | None" = None
    workspace_runtime_session: dict[str, Any] | None = None
    artifact_work_root: str | None = None
    prepared_entry_file: str | None = None
    _read_snapshots_cache: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)

    # Child-run lineage metadata. These stay unset for top-level runs.
    parent_run_id: str | None = None
    subagent_run_id: str | None = None
    subagent_label: str | None = None
    subagent_type: str | None = None
    is_subagent: bool = False
    subagent_depth: int = 0  # 0 = top-level run; incremented on each nesting

    # UI placement anchor for run-produced cards/events. Plan execution runs use
    # the synthetic "Start plan execution" user message as their anchor.
    run_output_anchor_message_id: str | None = None
    run_output_anchor_created_at: str | None = None
    run_output_anchor_source: str | None = None

    def __post_init__(self) -> None:
        if self.workspace_root is None:
            # Lazy import to avoid circulars at module import time.
            from app.core.config import settings

            self.workspace_root = Path(settings.HARNESS_WORKSPACE_ROOT).expanduser().resolve()
        elif not isinstance(self.workspace_root, Path):
            self.workspace_root = Path(self.workspace_root).expanduser().resolve()
        else:
            self.workspace_root = self.workspace_root.expanduser().resolve()

    def record_billing(self, category: str, amount: float, detail: dict | None = None) -> None:
        """Accumulate billing for consolidated agent billing."""
        if is_provider_balance_sync_enabled():
            amount = 0
        self.accumulated_amount_cents += amount
        self.billing_breakdown.append({
            "category": category,
            "amount": amount,
            "detail": detail or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._record_summary_event(
            category=category,
            model_name=(detail or {}).get("model_name") if isinstance(detail, dict) else None,
            elapsed_ms=(detail or {}).get("elapsed_ms") if isinstance(detail, dict) else None,
            outcome="success",
        )

    def record_model_call(
        self,
        category: str,
        *,
        model_name: str | None = None,
        elapsed_ms: int | None = None,
        outcome: str = "success",
    ) -> None:
        self._record_summary_event(
            category=category,
            model_name=model_name,
            elapsed_ms=elapsed_ms,
            outcome=outcome,
        )

    @staticmethod
    def _normalize_summary_category(category: str | None) -> str | None:
        normalized = str(category or "").strip().lower()
        if normalized == "multimodal":
            return "multimodal"
        if normalized == "image_analysis":
            return "image_analysis"
        if normalized == "image_generation":
            return "image_generation"
        if normalized == "video_generation":
            return "video_generation"
        if normalized == "context_compression":
            return "context_compression"
        return None

    def _record_summary_event(
        self,
        *,
        category: str | None,
        model_name: str | None = None,
        elapsed_ms: int | None = None,
        outcome: str = "success",
    ) -> None:
        normalized_category = self._normalize_summary_category(category)
        if normalized_category is None:
            return

        self.billing_counts[normalized_category] = self.billing_counts.get(normalized_category, 0) + 1

        normalized_model = str(model_name or "").strip()
        if normalized_model:
            self.billing_models.setdefault(normalized_category, set()).add(normalized_model)
            model_stats = self.billing_model_stats.setdefault(normalized_category, {}).setdefault(
                normalized_model,
                {
                    "model_name": normalized_model,
                    "model_label": get_model_label(normalized_model),
                    "calls": 0,
                    "success_calls": 0,
                    "failed_calls": 0,
                },
            )
            model_stats["calls"] += 1
            normalized_outcome = str(outcome or "success").strip().lower()
            if normalized_outcome == "failed":
                model_stats["failed_calls"] += 1
            else:
                model_stats["success_calls"] += 1

        try:
            normalized_elapsed = int(elapsed_ms or 0)
        except (TypeError, ValueError):
            normalized_elapsed = 0
        if normalized_elapsed > 0:
            self.billing_elapsed_ms[normalized_category] = (
                self.billing_elapsed_ms.get(normalized_category, 0) + normalized_elapsed
            )

    def build_billing_summary(self, *, mode: str | None = None) -> dict[str, Any]:
        resolved_mode = resolve_harness_mode(mode=mode or self.artifact_mode, skill_id=self.skill_id)
        multimodal_stats = list(self.billing_model_stats.get("multimodal", {}).values())
        image_analysis_stats = list(self.billing_model_stats.get("image_analysis", {}).values())
        image_stats = list(self.billing_model_stats.get("image_generation", {}).values())
        video_stats = list(self.billing_model_stats.get("video_generation", {}).values())
        compression_stats = list(self.billing_model_stats.get("context_compression", {}).values())
        return {
            "mode": resolved_mode,
            "mode_label": resolve_harness_mode_label(mode=mode or self.artifact_mode, skill_id=self.skill_id),
            "multimodal_calls": self.billing_counts.get("multimodal", 0),
            "image_analysis_calls": self.billing_counts.get("image_analysis", 0),
            "image_generation_calls": self.billing_counts.get("image_generation", 0),
            "video_generation_calls": self.billing_counts.get("video_generation", 0),
            "context_compression_calls": self.billing_counts.get("context_compression", 0),
            "multimodal_models": sorted(self.billing_models.get("multimodal", set())),
            "image_analysis_models": sorted(self.billing_models.get("image_analysis", set())),
            "image_models": sorted(self.billing_models.get("image_generation", set())),
            "video_models": sorted(self.billing_models.get("video_generation", set())),
            "context_compression_models": sorted(self.billing_models.get("context_compression", set())),
            "multimodal_model_stats": sorted(multimodal_stats, key=lambda item: str(item.get("model_label") or item.get("model_name") or "")),
            "image_analysis_model_stats": sorted(image_analysis_stats, key=lambda item: str(item.get("model_label") or item.get("model_name") or "")),
            "image_model_stats": sorted(image_stats, key=lambda item: str(item.get("model_label") or item.get("model_name") or "")),
            "video_model_stats": sorted(video_stats, key=lambda item: str(item.get("model_label") or item.get("model_name") or "")),
            "context_compression_model_stats": sorted(compression_stats, key=lambda item: str(item.get("model_label") or item.get("model_name") or "")),
            "total_elapsed_ms": sum(self.billing_elapsed_ms.values()),
        }

    def absorb_billing_from(self, child_ctx: "HarnessContext") -> None:
        self.accumulated_amount_cents += child_ctx.accumulated_amount_cents
        self.billing_breakdown.extend(child_ctx.billing_breakdown)

        for category, count in child_ctx.billing_counts.items():
            self.billing_counts[category] = self.billing_counts.get(category, 0) + count

        for category, models in child_ctx.billing_models.items():
            self.billing_models.setdefault(category, set()).update(models)

        for category, stats_by_model in child_ctx.billing_model_stats.items():
            merged_category = self.billing_model_stats.setdefault(category, {})
            for model_name, stats in stats_by_model.items():
                merged_stats = merged_category.setdefault(
                    model_name,
                    {
                        "model_name": stats.get("model_name") or model_name,
                        "model_label": stats.get("model_label") or get_model_label(model_name),
                        "calls": 0,
                        "success_calls": 0,
                        "failed_calls": 0,
                    },
                )
                merged_stats["calls"] += int(stats.get("calls") or 0)
                merged_stats["success_calls"] += int(stats.get("success_calls") or 0)
                merged_stats["failed_calls"] += int(stats.get("failed_calls") or 0)

        for category, elapsed_ms in child_ctx.billing_elapsed_ms.items():
            self.billing_elapsed_ms[category] = self.billing_elapsed_ms.get(category, 0) + int(elapsed_ms or 0)

    def build_usage_log_params(self, *, mode: str | None = None) -> dict[str, Any]:
        return {
            "engine": "agent_harness",
            "conversation_id": self.conversation_id,
            "agent_run_id": self.run_id,
            "billing_summary": self.build_billing_summary(mode=mode),
        }

    def bind_tool_stream_callback(
        self,
        callback: Callable[[str, dict[str, Any]], Awaitable[None]],
    ) -> None:
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Tool stream callback must be bound from an async task")
        self._tool_stream_callbacks[task] = callback

    def clear_tool_stream_callback(self) -> None:
        task = asyncio.current_task()
        if task is None:
            return
        self._tool_stream_callbacks.pop(task, None)

    async def emit_tool_stream_event(self, event_type: str, payload: dict[str, Any]) -> None:
        task = asyncio.current_task()
        if task is None:
            return
        gateway = self.runtime_gateway
        if gateway is not None:
            from app.services.agent_harness.workflow.contracts import EventSpec

            scope = self._tool_stream_scope.get(task) or {}
            tool_call_id = scope.get("tool_call_id")
            sequence = int(self._tool_stream_sequence.get(task, 0)) + 1
            self._tool_stream_sequence[task] = sequence
            await gateway.append_event(
                EventSpec(
                    event_type=event_type,
                    payload=dict(payload),
                    tool_call_id=str(tool_call_id) if tool_call_id else None,
                    idempotency_key=_tool_stream_event_key(
                        run_id=self.run_id,
                        step_id=gateway.step_id,
                        tool_call_id=str(tool_call_id or "tool"),
                        event_type=event_type,
                        payload=payload,
                        sequence=sequence,
                    ),
                )
            )
        callback = self._tool_stream_callbacks.get(task)
        if callback is None:
            return
        await callback(event_type, payload)

    async def emit_workflow_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        block_id: str | None = None,
        tool_call_id: str | None = None,
        artifact_id: str | None = None,
        parent_block_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        gateway = self.runtime_gateway
        if gateway is None:
            return None
        from app.services.agent_harness.workflow.contracts import EventSpec

        enriched_payload = dict(payload)
        for key, value in self.run_output_anchor_payload().items():
            enriched_payload.setdefault(key, value)
        return await gateway.append_event(
            EventSpec(
                event_type=event_type,
                payload=enriched_payload,
                block_id=block_id,
                tool_call_id=tool_call_id,
                artifact_id=artifact_id,
                parent_block_id=parent_block_id,
                idempotency_key=idempotency_key,
            )
        )

    def run_output_anchor_payload(self) -> dict[str, Any]:
        anchor_message_id = str(self.run_output_anchor_message_id or "").strip()
        if not anchor_message_id:
            return {}
        payload: dict[str, Any] = {
            "anchor_message_id": anchor_message_id,
            "anchor_source": str(self.run_output_anchor_source or "run_output").strip() or "run_output",
        }
        anchor_created_at = str(self.run_output_anchor_created_at or "").strip()
        if anchor_created_at:
            payload["anchor_created_at"] = anchor_created_at
        return payload

    def hydrate_run_output_anchor(self, anchor: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.run_output_anchor_payload():
            return self.run_output_anchor_payload()
        if anchor is None:
            try:
                from app.services.agent_harness.runtime.state.store_core import read_runtime_state

                runtime_state = read_runtime_state(self.user_id, self.conversation_id)
                anchor = runtime_state.get("run_output_anchor") if isinstance(runtime_state.get("run_output_anchor"), dict) else None
            except Exception:
                anchor = None
        if not isinstance(anchor, dict):
            return {}
        anchor_message_id = str(anchor.get("anchor_message_id") or anchor.get("anchorMessageId") or "").strip()
        if not anchor_message_id:
            return {}
        self.run_output_anchor_message_id = anchor_message_id
        self.run_output_anchor_created_at = str(anchor.get("anchor_created_at") or anchor.get("anchorCreatedAt") or "").strip() or None
        self.run_output_anchor_source = (
            str(anchor.get("anchor_source") or anchor.get("anchorSource") or "run_output").strip()
            or "run_output"
        )
        return self.run_output_anchor_payload()

    def bind_tool_stream_scope(
        self,
        *,
        tool_name: str,
        tool_call_id: str | None = None,
        message_key: str | None = None,
        parent_block_key: str | None = None,
        order: int | None = None,
    ) -> None:
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Tool stream scope must be bound from an async task")
        self._tool_stream_scope[task] = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "message_key": message_key,
            "parent_block_key": parent_block_key,
            "order": order,
        }

    def clear_tool_stream_scope(self) -> None:
        task = asyncio.current_task()
        if task is None:
            return
        self._tool_stream_scope.pop(task, None)
        self._tool_stream_sequence.pop(task, None)

    def get_tool_stream_scope(self) -> dict[str, Any] | None:
        task = asyncio.current_task()
        if task is None:
            return None
        return self._tool_stream_scope.get(task)

    # -----------------------------------------------------------------------
    # Directory helpers
    # -----------------------------------------------------------------------

    @property
    def conversation_dir(self) -> Path:
        runtime_profile = str(self.runtime_profile or "home").strip().lower() or "home"
        if runtime_profile == "canvas":
            if self.project_id is None:
                raise ValueError("project_id is required for canvas runtime profile")
            return (
                self.workspace_root
                / "project"
                / str(self.project_id)
                / "users"
                / str(self.user_id)
                / "conversations"
                / str(self.conversation_id)
            )
        return (
            self.workspace_root
            / "users"
            / str(self.user_id)
            / "conversations"
            / str(self.conversation_id)
        )

    @property
    def code_dir(self) -> Path:
        return self.project_dir

    @property
    def project_dir(self) -> Path:
        return self.conversation_dir / "project"

    @property
    def references_dir(self) -> Path:
        return self.conversation_dir / "references"

    @property
    def reference_inputs_dir(self) -> Path:
        return self.references_dir / "inputs"

    @property
    def reference_sources_dir(self) -> Path:
        return self.references_dir / "sources"

    @property
    def reference_generated_dir(self) -> Path:
        return self.references_dir / "generated"

    @property
    def skill_dir(self) -> Path:
        return self.conversation_dir / "skill"

    @property
    def agent_dir(self) -> Path:
        return self.conversation_dir / ".agent"

    @property
    def work_dir(self) -> Path:
        """Deprecated alias for project_dir."""
        return self.project_dir

    @property
    def assets_dir(self) -> Path:
        """Deprecated alias for references_dir."""
        return self.references_dir

    @property
    def published_dir(self) -> Path:
        return self.conversation_dir / "published"

    @property
    def logs_dir(self) -> Path:
        return self.conversation_dir / "logs"

    @property
    def meta_dir(self) -> Path:
        return self.conversation_dir / ".meta"

    def _canonical_read_key(self, file_path: Path) -> str:
        try:
            resolved = file_path.resolve()
        except Exception:
            resolved = file_path
        try:
            rel = resolved.relative_to(self.conversation_dir.resolve())
            return str(rel).replace("\\", "/")
        except Exception:
            return str(resolved).replace("\\", "/")

    def _load_read_files(self) -> dict[str, dict[str, Any]]:
        try:
            from app.services.agent_harness.workspace.session_v2.db_store import read_runtime_state_payload

            conversation = read_runtime_state_payload(self.user_id, self.conversation_id) or {}
            runtime_state = conversation.get("runtime_state") if isinstance(conversation.get("runtime_state"), dict) else {}
            snapshots = runtime_state.get("read_file_snapshots") if isinstance(runtime_state.get("read_file_snapshots"), dict) else {}
            normalized: dict[str, dict[str, Any]] = {}
            for key, value in snapshots.items():
                snapshot = snapshot_from_dict(value)
                if snapshot is None:
                    continue
                normalized[str(key)] = snapshot_to_dict(snapshot)
            if normalized:
                self._read_snapshots_cache = dict(normalized)
                return normalized
        except Exception:
            pass
        return dict(self._read_snapshots_cache)

    def mark_file_read(self, file_path: Path) -> None:
        key = self._canonical_read_key(file_path)
        seen = self._load_read_files()
        seen[key] = snapshot_to_dict(build_snapshot(file_path))
        self._read_snapshots_cache = dict(seen)
        self._persist_read_files(seen)

    def get_read_snapshot(self, file_path: Path):
        key = self._canonical_read_key(file_path)
        return snapshot_from_dict(self._load_read_files().get(key))

    def has_any_read_snapshot(self, file_path: Path) -> bool:
        key = self._canonical_read_key(file_path)
        return key in self._load_read_files()

    def is_snapshot_current(self, file_path: Path) -> bool:
        snapshot = self.get_read_snapshot(file_path)
        if snapshot is None or not file_path.exists() or not file_path.is_file():
            return False
        try:
            current = build_snapshot(file_path)
        except Exception:
            return False
        return current == snapshot

    def has_read_file(self, file_path: Path) -> bool:
        return self.is_snapshot_current(file_path)

    def _persist_read_files(self, snapshots: dict[str, dict[str, Any]]) -> None:
        try:
            from app.services.agent_harness.runtime.state.store_core import utc_now
            from app.services.agent_harness.workspace.session_v2.db_store import read_runtime_state_payload, update_conversation_record

            conversation = read_runtime_state_payload(self.user_id, self.conversation_id) or {}
            if not isinstance(conversation, dict):
                return
            runtime_state = (
                dict(conversation.get("runtime_state") or {})
                if isinstance(conversation.get("runtime_state"), dict)
                else {}
            )
            runtime_state["read_file_snapshots"] = snapshots
            update_conversation_record(
                self.user_id,
                self.conversation_id,
                {
                    "runtime_state": runtime_state,
                    "updated_at": utc_now(),
                },
            )
        except Exception:
            pass

    def ensure_dirs(self) -> None:
        """Create workspace sub-directories. Called when conversation is created."""
        for d in (
            self.project_dir,
            self.reference_inputs_dir,
            self.reference_sources_dir,
            self.reference_generated_dir,
            self.skill_dir,
            self.agent_dir,
            self.published_dir,
            self.meta_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def resolve_workspace_path(
        self,
        path: str,
        *,
        default_scope: str = "code",
        allow_fallback_to_files: bool = False,
    ) -> Path | None:
        raw_path = (path or "").strip()
        if not raw_path:
            base = self._artifact_work_dir()
            return base.resolve()

        expanded_path = self._expand_tool_path(raw_path)
        expanded_candidate = Path(expanded_path).expanduser()
        conversation_root = self.conversation_dir.resolve()

        if expanded_candidate.is_absolute():
            try:
                resolved_absolute = expanded_candidate.resolve()
            except Exception:
                return None
            if _is_within_path(resolved_absolute, conversation_root):
                return resolved_absolute
            return None

        normalized = expanded_path.replace("\\", "/").lstrip("/")

        scopes: list[tuple[Path, str]]
        if normalized == "project" or normalized.startswith("project/"):
            rel = normalized[8:] if normalized.startswith("project/") else ""
            scopes = [(self.project_dir, rel)]
        elif normalized == "references" or normalized.startswith("references/"):
            rel = normalized[11:] if normalized.startswith("references/") else ""
            scopes = [(self.references_dir, rel)]
        elif normalized == "published" or normalized.startswith("published/"):
            rel = normalized[10:] if normalized.startswith("published/") else ""
            scopes = [(self.published_dir, rel)]
        elif normalized == "skill" or normalized.startswith("skill/"):
            rel = normalized[6:] if normalized.startswith("skill/") else ""
            scopes = [(self.skill_dir, rel)]
        elif normalized == "files" or normalized.startswith("files/"):
            return None
        elif normalized == "work" or normalized.startswith("work/") or normalized == "assets" or normalized.startswith("assets/"):
            return None
        else:
            default_base = self._artifact_work_dir()
            scopes = [(default_base, normalized)]

        candidates: list[Path] = []
        for base, relative in scopes:
            resolved = (base / relative).resolve()
            if _is_within_path(resolved, conversation_root):
                candidates.append(resolved)
        if not candidates:
            return None
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _artifact_work_root(self) -> str:
        workspace_session = self.workspace_runtime_session if isinstance(self.workspace_runtime_session, dict) else {}
        value = str(workspace_session.get("artifact_work_root") or "").replace("\\", "/").strip().lstrip("/").strip("/")
        if value:
            return value.removeprefix("project/").strip("/")
        agent_cwd = str(workspace_session.get("agent_cwd") or "").replace("\\", "/").strip().lstrip("/").strip("/")
        if agent_cwd.startswith("project/"):
            return agent_cwd.removeprefix("project/").strip("/")
        if self.prepared_workspace is not None:
            value = str(getattr(self.prepared_workspace, "artifact_work_root", "") or "").replace("\\", "/").strip().lstrip("/").strip("/")
            if value:
                return value.removeprefix("project/").strip("/")
        return str(self.artifact_work_root or "").replace("\\", "/").strip().lstrip("/").strip("/").removeprefix("project/").strip("/")

    def _artifact_work_dir(self) -> Path:
        artifact_work_root = self._artifact_work_root()
        return self.project_dir / artifact_work_root if artifact_work_root else self.project_dir

    def _expand_tool_path(self, path: str) -> str:
        artifact_work_root = self._artifact_work_root()
        artifact_work_dir = self._artifact_work_dir()
        env_map = {
            "CONVERSATION_DIR": str(self.conversation_dir),
            "HARNESS_CONVERSATION_DIR": str(self.conversation_dir),
            "HARNESS_PROJECT_DIR": str(self.project_dir),
            "HARNESS_ARTIFACT_WORK_DIR": str(artifact_work_dir),
            "HARNESS_ARTIFACT_WORK_ROOT": artifact_work_root,
            "HARNESS_REFERENCES_DIR": str(self.references_dir),
            "HARNESS_REFERENCE_INPUTS_DIR": str(self.reference_inputs_dir),
            "HARNESS_REFERENCE_SOURCES_DIR": str(self.reference_sources_dir),
            "HARNESS_REFERENCE_GENERATED_DIR": str(self.reference_generated_dir),
            "HARNESS_PUBLISHED_DIR": str(self.published_dir),
            "HARNESS_SKILL_ROOT": str(self.skill_dir),
            "HARNESS_AUTHOR_NAME": "Harness",
        }

        expanded = path
        for key, value in env_map.items():
            expanded = expanded.replace(f"${{{key}}}", value)
            expanded = expanded.replace(f"${key}", value)

        return os.path.expandvars(expanded)


