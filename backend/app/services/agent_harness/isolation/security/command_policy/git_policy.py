from __future__ import annotations

from .splitter import shell_tokens
from .types import CommandRiskTag

_READ_ONLY_GIT_COMMANDS = {
    "branch",
    "diff",
    "log",
    "remote",
    "show",
    "status",
    "tag",
}

_GIT_REMOTE_WRITE_TOKENS = {
    "add",
    "push",
    "remove",
    "rename",
    "rm",
    "set-url",
    "--force",
    "--delete",
    "-d",
    "--mirror",
}

_GIT_EXEC_CONFIG_KEYS = {
    "core.sshcommand",
    "core.hookspath",
    "core.fsmonitor",
    "diff.external",
    "alias.",
}


def git_risk(command: str, *, ctx, cwd: str) -> tuple[str, str, str] | tuple[str, str, str, str] | None:
    try:
        tokens = shell_tokens(command)
    except ValueError:
        return None
    if not tokens or tokens[0].lower() != "git":
        return None

    normalized = [token.lower() for token in tokens]
    if len(normalized) >= 2 and normalized[1] == "config" and not _is_readonly_git_config(normalized[2:]):
        return (
            "Git configuration writes are blocked.",
            "dangerous_command",
            CommandRiskTag.GIT_EXEC_CONFIG.value,
        )
    if len(normalized) >= 2 and normalized[1] == "diff":
        if any(token == "--output" or token.startswith("--output=") for token in normalized[2:]):
            return (
                "Git diff output flags can write files and are blocked.",
                "dangerous_command",
                CommandRiskTag.READONLY_FLAG_WRITES.value,
            )
        if any(token == "--ext-diff" for token in normalized[2:]):
            return (
                "Git diff external diff execution requires review.",
                "command_requires_review",
                CommandRiskTag.READONLY_FLAG_REQUIRES_REVIEW.value,
                "ask",
            )
    if _contains_cd_git_compound(command, tokens):
        return (
            "Compound commands with cd and git require manual review.",
            "dangerous_command",
            CommandRiskTag.GIT_CD_COMPOUND.value,
        )

    if any(token in _GIT_REMOTE_WRITE_TOKENS for token in normalized[1:]):
        return (
            "Git remote write operations are blocked.",
            "dangerous_command",
            CommandRiskTag.GIT_REMOTE_WRITE.value,
        )

    if any(_looks_like_exec_config(token) for token in normalized[1:]):
        return (
            "Git configuration that can execute code is blocked.",
            "dangerous_command",
            CommandRiskTag.GIT_EXEC_CONFIG.value,
        )

    if any(token == "-c" for token in normalized[1:]):
        return (
            "Inline git configuration is blocked.",
            "dangerous_command",
            CommandRiskTag.GIT_EXEC_CONFIG.value,
        )

    if len(tokens) >= 2 and tokens[1] in _READ_ONLY_GIT_COMMANDS:
        return None

    return None


def _contains_cd_git_compound(command: str, tokens: list[str]) -> bool:
    lowered = command.lower()
    if not any(token == "git" for token in tokens):
        return False
    if "cd " not in lowered:
        return False
    return any(op in lowered for op in ("&&", ";", "|"))


def _looks_like_exec_config(token: str) -> bool:
    return any(marker in token for marker in _GIT_EXEC_CONFIG_KEYS)


def _is_readonly_git_config(args: list[str]) -> bool:
    readonly_flags = {"--get", "--get-all", "--list", "-l", "--name-only", "--show-origin"}
    return bool(args and args[0] in readonly_flags)
