from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


SubagentStatus = Literal[
    "queued",
    "running",
    "completed",
    "degraded",
    "failed",
    "refused",
    "cancelled",
]


@dataclass(frozen=True, slots=True)
class SubagentDefinition:
    name: str
    description: str
    system_prompt: str
    system_prompt_en: str = ""
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    read_only: bool = False
    max_turns: int = 10
    tool_result_summary_chars: int = 4000
    internal: bool = False

    def get_system_prompt(self, language: str = "zh") -> str:
        if language == "en" and self.system_prompt_en:
            return self.system_prompt_en
        return self.system_prompt


@dataclass(frozen=True, slots=True)
class SubagentTaskSpec:
    description: str
    prompt: str
    subagent_type: str = "general-purpose"

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "SubagentTaskSpec":
        return cls(
            description=str(value.get("description") or "").strip(),
            prompt=str(value.get("prompt") or "").strip(),
            subagent_type=str(value.get("subagent_type") or "general-purpose").strip() or "general-purpose",
        )

    @property
    def purpose(self) -> str:
        return self.description

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "prompt": self.prompt,
            "subagent_type": self.subagent_type,
        }


@dataclass(frozen=True, slots=True)
class SubagentRequest:
    task_id: str
    spec: SubagentTaskSpec
    auto_finalize_terminal: bool = True

    @property
    def task(self) -> str:
        return self.spec.prompt

    @property
    def label(self) -> str | None:
        return self.spec.description

    @property
    def subagent_type(self) -> str:
        return self.spec.subagent_type


@dataclass(frozen=True, slots=True)
class SubagentResult:
    task_id: str
    status: SubagentStatus
    summary: str
    result: Any
    usage: dict[str, Any] | None = None
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class SubagentContext:
    parent_run_id: str
    subagent_run_id: str
    subagent_type: str
    label: str | None = None
    skill_id: str | None = None
    conversation_id: str | None = None
