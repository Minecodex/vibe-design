from __future__ import annotations

from copy import copy as shallow_copy
from pathlib import Path
from typing import Any

from app.services.agent_harness.capabilities.skills import get_skill

from .base import ProtocolRuntimeContext, RuntimePrepareRequest, RuntimePrepareResult, SkillProtocol, SkillProtocolAdapter
from .builtin.adapter import BuiltinProtocolAdapter
from .open_design.adapter import OpenDesignProtocolAdapter


class SkillProtocolRegistry:
    def __init__(self, adapters: list[SkillProtocolAdapter] | None = None) -> None:
        self._adapters = adapters or [OpenDesignProtocolAdapter(), BuiltinProtocolAdapter()]

    def resolve(self, skill: Any, runtime_context: ProtocolRuntimeContext | None = None) -> SkillProtocol:
        context = runtime_context or ProtocolRuntimeContext()
        for adapter in self._adapters:
            if adapter.can_handle(skill, context):
                return adapter.resolve(skill, context)
        return BuiltinProtocolAdapter().resolve(skill, context)

    def prepare_runtime(self, skill: Any, request: RuntimePrepareRequest) -> RuntimePrepareResult | None:
        context = ProtocolRuntimeContext(
            artifact_mode=request.artifact_mode,
            project_kind=request.artifact_mode,
            workspace_runtime_session=request.workspace_runtime_session,
            work_dir=request.work_dir,
        )
        for adapter in self._adapters:
            if adapter.can_handle(skill, context):
                prepared = adapter.prepare_runtime(request)
                if prepared is not None:
                    return prepared
        return None


DEFAULT_PROTOCOL_REGISTRY = SkillProtocolRegistry()


def resolve_skill_protocol(skill: Any, runtime_context: ProtocolRuntimeContext | None = None) -> SkillProtocol:
    return DEFAULT_PROTOCOL_REGISTRY.resolve(skill, runtime_context)


def prepare_skill_runtime(skill: Any, request: RuntimePrepareRequest) -> RuntimePrepareResult | None:
    return DEFAULT_PROTOCOL_REGISTRY.prepare_runtime(skill, request)


def resolve_protocol_for_context(ctx: Any) -> SkillProtocol:
    skill = get_skill(getattr(ctx, "skill_id", None))
    skill_runtime_dir = getattr(ctx, "skill_runtime_dir", None) or getattr(ctx, "active_skill_dir", None)
    if skill is not None and skill_runtime_dir is not None:
        skill = shallow_copy(skill)
        setattr(skill, "skill_dir", Path(skill_runtime_dir).resolve())
    work_dir = Path(
        getattr(
            ctx,
            "work_dir",
            Path(getattr(ctx, "conversation_dir", Path(".")) or Path(".")) / "project",
        )
        or Path(".")
    )
    return resolve_skill_protocol(
        skill,
        ProtocolRuntimeContext(
            artifact_mode=getattr(ctx, "artifact_mode", None),
            project_kind=getattr(ctx, "artifact_mode", None),
            prepared_workspace=getattr(ctx, "prepared_workspace", None),
            workspace_runtime_session=getattr(ctx, "workspace_runtime_session", None),
            work_dir=work_dir,
        ),
    )
