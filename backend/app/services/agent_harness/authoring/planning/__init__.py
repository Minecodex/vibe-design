from __future__ import annotations

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "OutlineCoordinator": ".outline_runtime",
    "OutlineLockedError": ".outline_plan",
    "apply_outline_patch": ".outline_plan",
    "build_outline_projection": ".outline_plan",
    "build_plan_context_block": ".outline_runtime",
    "build_user_plan_repair_prompt": ".user_plan",
    "compile_execution_plan": ".outline_plan",
    "complete_conversation_plan_state": ".outline_runtime",
    "complete_outline_runtime_execution": ".outline_runtime",
    "create_outline_state": ".outline_plan",
    "normalize_artifact_type": ".user_plan",
    "outline_from_user_plan": ".outline_plan",
    "outline_to_user_plan": ".outline_plan",
    "plan_has_unfinished_steps": ".outline_runtime",
    "resolve_selection": ".decision_resolver",
    "validate_user_plan": ".user_plan",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
