from __future__ import annotations

import re

from .splitter import shell_tokens
from .types import CommandRiskTag

_UNSUPPORTED_SHELL_COMMANDS = {
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "cmd",
    "cmd.exe",
}

_DANGEROUS_BASE_COMMANDS = {
    "rm",
    "doas",
    "mkfs",
    "poweroff",
    "reboot",
    "shutdown",
    "su",
    "sudo",
}
_SHELL_BASE_COMMANDS = {"bash", "dash", "fish", "ksh", "sh", "zsh"}

_DOWNLOAD_EXECUTION_RE = re.compile(r"\b(?:curl|wget)\b[^\n\r|;&]*\|\s*(?:sh|bash|zsh|python|python3|node)\b", re.I)
_REMOTE_INTERPRETATION_RE = re.compile(r"\b(?:curl|wget)\b[^\n\r|;&]*&&\s*(?:sh|bash|zsh|python|python3|node)\b", re.I)


def bash_risk(command: str, *, ctx, cwd: str) -> tuple[str, str, str] | None:
    lowered = command.lower()
    try:
        tokens = list(shell_tokens(command))
    except ValueError:
        return (
            "Command could not be parsed safely.",
            "shell_parse_error",
            CommandRiskTag.SHELL_PARSE_ERROR.value,
        )
    if any(token.lower() in _UNSUPPORTED_SHELL_COMMANDS for token in tokens):
        return (
            "Windows shell commands are not supported in this deployment.",
            "unsupported_shell",
            CommandRiskTag.UNSUPPORTED_SHELL.value,
        )
    if re.search(r"(?:^|[\s;&|])=[A-Za-z_]", command):
        return (
            "Zsh equals expansion is blocked.",
            "dangerous_command",
            CommandRiskTag.ZSH_EQUALS_EXPANSION.value,
        )
    if "(e:" in command or "(+" in command:
        return (
            "Zsh glob qualifiers that can execute commands are blocked.",
            "dangerous_command",
            CommandRiskTag.ZSH_GLOB_QUALIFIER.value,
        )
    if ":(){ :|:& };:" in lowered.replace(" ", ""):
        return (
            "Fork bomb patterns are blocked.",
            "dangerous_command",
            CommandRiskTag.FORK_BOMB.value,
        )
    if _DOWNLOAD_EXECUTION_RE.search(command) or _REMOTE_INTERPRETATION_RE.search(command):
        return (
            "Downloading and executing remote code is blocked.",
            "dangerous_command",
            CommandRiskTag.DANGEROUS_DOWNLOAD_EXECUTION.value,
        )

    if not tokens:
        return None
    base = _strip_wrappers(tokens[0]).lower()
    if base == "rm":
        rm_args = [token.lower() for token in tokens[1:]]
        has_recursive_force = any(arg.startswith("-") and "r" in arg and "f" in arg for arg in rm_args)
        targets = [arg for arg in rm_args if not arg.startswith("-")]
        if has_recursive_force and any(target in {"/", "~", "~/" } or target.startswith(("/", "~/")) for target in targets):
            return (
                "Recursive destructive remove is blocked.",
                "dangerous_command",
                CommandRiskTag.DANGEROUS_SYSTEM_COMMAND.value,
            )
    if base in _DANGEROUS_BASE_COMMANDS - {"rm"}:
        return (
            "Dangerous system command is blocked.",
            "dangerous_command",
            CommandRiskTag.DANGEROUS_SYSTEM_COMMAND.value,
        )
    if base in _SHELL_BASE_COMMANDS and any(token == "-c" for token in tokens[1:]):
        return (
            "Shell command execution through -c is blocked.",
            "dangerous_command",
            CommandRiskTag.READONLY_FLAG_EXECUTES_COMMANDS.value,
        )
    if base == "dd" and any("of=/dev/" in token.lower() for token in tokens[1:]):
        return (
            "Writing to /dev devices is blocked.",
            "dangerous_command",
            CommandRiskTag.DANGEROUS_SYSTEM_COMMAND.value,
        )
    if base == "date" and any(token.lower() in {"-s", "--set"} or token.lower().startswith("--set=") for token in tokens[1:]):
        return (
            "Date flags that mutate system time are blocked.",
            "dangerous_command",
            CommandRiskTag.READONLY_FLAG_MUTATES_SYSTEM.value,
        )
    if base == "less" and any(token == "-S" for token in tokens[1:]):
        return (
            "Less flags with terminal command capabilities require review and are blocked.",
            "dangerous_command",
            CommandRiskTag.READONLY_FLAG_EXECUTES_COMMANDS.value,
        )

    return None


def _strip_wrappers(token: str) -> str:
    cleaned = token.strip()
    while cleaned and cleaned[0] in {"(", "{", "[", "'", '"'}:
        cleaned = cleaned[1:]
    while cleaned and cleaned[-1] in {")",
        "}",
        "]",
        "'",
        '"',
        ";",
    }:
        cleaned = cleaned[:-1]
    return cleaned
