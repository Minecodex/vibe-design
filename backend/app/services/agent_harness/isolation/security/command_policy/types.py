from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class CommandVerdict(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    BLOCK = "block"


class CommandRiskTag(StrEnum):
    COMMAND_SUBSTITUTION = "command_substitution"
    CONTROL_CHARACTER = "control_character"
    DANGEROUS_DOWNLOAD_EXECUTION = "dangerous_download_execution"
    DANGEROUS_SYSTEM_COMMAND = "dangerous_system_command"
    FORK_BOMB = "fork_bomb"
    GIT_ARCHIVE_THEN_GIT = "git_archive_then_git"
    GIT_BARE_REPO = "git_bare_repo"
    GIT_CD_COMPOUND = "git_cd_compound"
    GIT_CWD_REENTRY = "git_cwd_reentry"
    GIT_INTERNAL_WRITE = "git_internal_write"
    GIT_REMOTE_WRITE = "git_remote_write"
    GIT_EXEC_CONFIG = "git_exec_config"
    LEGACY_ARITHMETIC_EXPANSION = "legacy_arithmetic_expansion"
    PARAMETER_EXPANSION = "parameter_expansion"
    PATH_OUTSIDE_WORKSPACE = "path_outside_workspace"
    PROCESS_SUBSTITUTION = "process_substitution"
    DANGEROUS_REDIRECTION = "dangerous_redirection"
    DANGEROUS_VARIABLE = "dangerous_variable"
    NETWORK_DEVICE_REDIRECT = "network_device_redirect"
    READONLY_FLAG_EXECUTES_COMMANDS = "readonly_flag_executes_commands"
    READONLY_FLAG_MUTATES_SYSTEM = "readonly_flag_mutates_system"
    READONLY_FLAG_NETWORK = "readonly_flag_network"
    READONLY_FLAG_REQUIRES_REVIEW = "readonly_flag_requires_review"
    READONLY_FLAG_WRITES = "readonly_flag_writes"
    SED_EXEC = "sed_exec"
    SED_WRITE = "sed_write"
    SHELL_OBFUSCATION = "shell_obfuscation"
    SHELL_PARSE_ERROR = "shell_parse_error"
    TOO_COMPLEX = "too_complex"
    UNSUPPORTED_SHELL = "unsupported_shell"
    WRAPPER_COMMAND = "wrapper_command"
    ZSH_EQUALS_EXPANSION = "zsh_equals_expansion"
    ZSH_GLOB_QUALIFIER = "zsh_glob_qualifier"


@dataclass(frozen=True, slots=True)
class AnalyzedCommand:
    text: str
    index: int
    operator_before: str | None = None


@dataclass(frozen=True, slots=True)
class CommandSecurityReport:
    verdict: CommandVerdict
    reason: str | None = None
    reason_code: str | None = None
    risk_tags: tuple[str, ...] = ()
    commands: tuple[AnalyzedCommand, ...] = ()
    normalized_command: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.verdict == CommandVerdict.ALLOW

    def to_metadata(self) -> dict[str, object]:
        return {
            "verdict": self.verdict.value,
            "reason": self.reason,
            "reason_code": self.reason_code,
            "risk_tags": list(self.risk_tags),
            "commands": [
                {
                    "index": command.index,
                    "text": command.text,
                    "operator_before": command.operator_before,
                }
                for command in self.commands
            ],
            **self.metadata,
        }


def allow_report(
    *,
    commands: tuple[AnalyzedCommand, ...],
    normalized_command: str | None = None,
) -> CommandSecurityReport:
    return CommandSecurityReport(
        verdict=CommandVerdict.ALLOW,
        commands=commands,
        normalized_command=normalized_command,
    )


def block_report(
    *,
    reason: str,
    reason_code: str,
    risk_tags: tuple[str, ...],
    commands: tuple[AnalyzedCommand, ...] = (),
    normalized_command: str | None = None,
    metadata: dict[str, object] | None = None,
) -> CommandSecurityReport:
    return CommandSecurityReport(
        verdict=CommandVerdict.BLOCK,
        reason=reason,
        reason_code=reason_code,
        risk_tags=risk_tags,
        commands=commands,
        normalized_command=normalized_command,
        metadata=metadata or {},
    )


def ask_report(
    *,
    reason: str,
    reason_code: str,
    risk_tags: tuple[str, ...],
    commands: tuple[AnalyzedCommand, ...] = (),
    normalized_command: str | None = None,
    metadata: dict[str, object] | None = None,
) -> CommandSecurityReport:
    return CommandSecurityReport(
        verdict=CommandVerdict.ASK,
        reason=reason,
        reason_code=reason_code,
        risk_tags=risk_tags,
        commands=commands,
        normalized_command=normalized_command,
        metadata=metadata or {},
    )
