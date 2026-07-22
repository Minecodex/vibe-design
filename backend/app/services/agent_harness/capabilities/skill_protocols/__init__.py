from .base import (
    ExecutionContract,
    PreparedWorkspace,
    ProtocolRuntimeContext,
    PublishProfile,
    RuntimePrepareRequest,
    RuntimePrepareResult,
    SkillProtocol,
    ValidationProfile,
    WritePolicy,
    prepared_workspace_from_payload,
)


def resolve_skill_protocol(*args, **kwargs):
    from .registry import resolve_skill_protocol as _resolve_skill_protocol

    return _resolve_skill_protocol(*args, **kwargs)


def resolve_protocol_for_context(*args, **kwargs):
    from .registry import resolve_protocol_for_context as _resolve_protocol_for_context

    return _resolve_protocol_for_context(*args, **kwargs)


def prepare_skill_runtime(*args, **kwargs):
    from .registry import prepare_skill_runtime as _prepare_skill_runtime

    return _prepare_skill_runtime(*args, **kwargs)


def __getattr__(name: str):
    if name == "SkillProtocolRegistry":
        from .registry import SkillProtocolRegistry

        return SkillProtocolRegistry
    raise AttributeError(name)

__all__ = [
    "ExecutionContract",
    "PreparedWorkspace",
    "ProtocolRuntimeContext",
    "PublishProfile",
    "RuntimePrepareRequest",
    "RuntimePrepareResult",
    "SkillProtocol",
    "SkillProtocolRegistry",
    "ValidationProfile",
    "WritePolicy",
    "prepared_workspace_from_payload",
    "prepare_skill_runtime",
    "resolve_protocol_for_context",
    "resolve_skill_protocol",
]
