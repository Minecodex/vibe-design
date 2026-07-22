from __future__ import annotations

from typing import Any

from ..base import ProtocolRuntimeContext, RuntimePrepareRequest, RuntimePrepareResult, SkillProtocol


class BuiltinProtocolAdapter:
    provider = "builtin"

    def can_handle(self, skill: Any, runtime_context: ProtocolRuntimeContext) -> bool:
        return True

    def resolve(self, skill: Any, runtime_context: ProtocolRuntimeContext) -> SkillProtocol:
        mode = str(getattr(skill, "mode", "") or runtime_context.artifact_mode or "web").strip() or "web"
        return SkillProtocol(provider=self.provider, family="builtin_default", mode=mode, surface="web")

    def prepare_runtime(self, request: RuntimePrepareRequest) -> RuntimePrepareResult | None:
        return None
