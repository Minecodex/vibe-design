from __future__ import annotations

import re

from .splitter import shell_tokens
from .types import CommandRiskTag

_WRITE_SCRIPT_RE = re.compile(r"(^|[;\n])\s*(?:\d+|[$]|[,0-9$]+)?\s*[wr]\b")
_SUBSTITUTE_WRITE_RE = re.compile(r"s(?P<delim>[^A-Za-z0-9\s\\]).*?(?P=delim).*?(?P=delim)[gp0-9]*w\b")
_TEXT_MUTATION_RE = re.compile(r"(^|[;\n])\s*(?:\d+|[$]|[,0-9$]+)?\s*[aci]\b")
_EXEC_SCRIPT_RE = re.compile(r"(^|[;\n])\s*(?:\d+|[$]|[,0-9$]+)?\s*e\b")
_SUBSTITUTE_EXEC_RE = re.compile(r"s(?P<delim>[^A-Za-z0-9\s\\]).*?(?P=delim).*?(?P=delim)[gp0-9]*e\b")
_EXIT_CODE_RE = re.compile(r"(^|[;\n])\s*(?:\d+|[$]|[,0-9$]+)?\s*[qQ]\s+\d+")


def sed_risk(command: str) -> tuple[str, str, str] | None:
    try:
        tokens = list(shell_tokens(command))
    except ValueError:
        return (
            "Sed command could not be parsed safely.",
            "shell_parse_error",
            CommandRiskTag.SHELL_PARSE_ERROR.value,
        )
    if not tokens or tokens[0].lower() != "sed":
        return None

    scripts: list[str] = []
    script_seen = False
    index = 1
    while index < len(tokens):
        token = tokens[index]
        lowered = token.lower()
        if lowered in {"-i", "--in-place"} or lowered.startswith("-i") or lowered.startswith("--in-place="):
            return (
                "Sed in-place writes are blocked.",
                "dangerous_command",
                CommandRiskTag.SED_WRITE.value,
            )
        if lowered in {"-e", "--expression"}:
            if index + 1 >= len(tokens):
                return (
                    "Sed expression flag requires a script.",
                    "command_requires_review",
                    CommandRiskTag.READONLY_FLAG_REQUIRES_REVIEW.value,
                )
            scripts.append(tokens[index + 1])
            script_seen = True
            index += 2
            continue
        if lowered in {"-f", "--file"}:
            return (
                "Sed script files can contain read, write, or exec commands and are blocked.",
                "dangerous_command",
                CommandRiskTag.SED_EXEC.value,
            )
        if lowered in {"-n", "--quiet", "--silent", "-r", "-E", "--regexp-extended", "--posix", "-u", "--unbuffered"}:
            index += 1
            continue
        if token.startswith("-"):
            return (
                f"Sed flag {token} requires review.",
                "command_requires_review",
                CommandRiskTag.READONLY_FLAG_REQUIRES_REVIEW.value,
            )
        if not script_seen:
            scripts.append(token)
            script_seen = True
        index += 1

    for script in scripts:
        risk = _script_risk(script)
        if risk is not None:
            return risk
    return None


def _script_risk(script: str) -> tuple[str, str, str] | None:
    if "{" in script or "}" in script:
        return (
            "Complex sed blocks require review and are blocked.",
            "dangerous_command",
            CommandRiskTag.SED_EXEC.value,
        )
    if _WRITE_SCRIPT_RE.search(script) or _SUBSTITUTE_WRITE_RE.search(script) or _TEXT_MUTATION_RE.search(script):
        return (
            "Sed scripts that read or write files are blocked.",
            "dangerous_command",
            CommandRiskTag.SED_WRITE.value,
        )
    if _EXEC_SCRIPT_RE.search(script) or _SUBSTITUTE_EXEC_RE.search(script) or _EXIT_CODE_RE.search(script):
        return (
            "Sed scripts that execute commands are blocked.",
            "dangerous_command",
            CommandRiskTag.SED_EXEC.value,
        )
    return None
