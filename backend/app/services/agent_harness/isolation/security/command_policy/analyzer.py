from __future__ import annotations

from .ast_extract import parse_for_security
from .ast_security import ast_risk
from .bash_policy import bash_risk
from .git_policy import git_risk
from .path_policy import path_risk
from .readonly_registry import readonly_risk
from .sed_policy import sed_risk
from .splitter import MAX_SUBCOMMANDS_FOR_SECURITY_CHECK, shell_tokens
from .types import (
    AnalyzedCommand,
    CommandRiskTag,
    CommandSecurityReport,
    allow_report,
    ask_report,
    block_report,
)

_CONTROL_CHARS = {chr(code) for code in range(0, 32)} | {chr(127)}


def analyze_command(command: str, *, cwd: str, ctx) -> CommandSecurityReport:
    raw = str(command or "").strip()
    if not raw:
        return allow_report(commands=())
    # Newlines (LF) and tabs are ordinary command separators / whitespace and are
    # parsed structurally by the AST below. Carriage returns and other control
    # bytes stay blocked: CR tokenizes differently between shell-quote and bash
    # (a real misparsing/obfuscation vector), and binary control bytes have no
    # legitimate place in a command string.
    if any(ch in raw for ch in _CONTROL_CHARS - {"\n", "\t"}):
        if "\r" in raw:
            return block_report(
                reason="Carriage returns in shell commands are blocked.",
                reason_code="dangerous_command",
                risk_tags=(CommandRiskTag.SHELL_OBFUSCATION.value,),
            )
        return block_report(
            reason="Command contains control characters.",
            reason_code="dangerous_command",
            risk_tags=(CommandRiskTag.CONTROL_CHARACTER.value,),
        )
    ast_result = ast_risk(raw)
    if ast_result is not None:
        reason, reason_code, risk_tag, verdict = ast_result
        report_factory = ask_report if verdict == "ask" else block_report
        return report_factory(
            reason=reason,
            reason_code=reason_code,
            risk_tags=(risk_tag,),
            normalized_command=raw,
        )
    # The tree-sitter AST is the single source of truth for command structure:
    # it splits newlines / `;` / `&&` / `||` / pipelines into discrete commands,
    # keeps heredoc bodies out of the command set, and carries each command's
    # redirects in its text. Every downstream risk check runs per AST command.
    ast_security = parse_for_security(raw)
    if ast_security.blocked:
        return block_report(
            reason=ast_security.reason or "Command is too complex to analyze safely.",
            reason_code=ast_security.reason_code or "command_too_complex",
            risk_tags=(ast_security.risk_tag or CommandRiskTag.TOO_COMPLEX.value,),
            normalized_command=raw,
        )

    analyzed = tuple(
        AnalyzedCommand(text=text, index=index)
        for index, text in enumerate(
            stripped for stripped in (command.text.strip() for command in ast_security.commands) if stripped
        )
    )
    if len(analyzed) > MAX_SUBCOMMANDS_FOR_SECURITY_CHECK:
        return block_report(
            reason="Command is too complex to analyze safely.",
            reason_code="command_too_complex",
            risk_tags=(CommandRiskTag.TOO_COMPLEX.value,),
            commands=analyzed,
        )

    if _contains_cd_then_git(analyzed):
        return block_report(
            reason="Compound commands with cd and git require manual review.",
            reason_code="dangerous_command",
            risk_tags=(CommandRiskTag.GIT_CD_COMPOUND.value,),
            commands=analyzed,
            normalized_command=raw,
        )
    git_compound_report = _git_compound_attack_report(analyzed, raw)
    if git_compound_report is not None:
        return git_compound_report
    if _contains_download_then_shell(analyzed):
        return block_report(
            reason="Downloading and executing remote code is blocked.",
            reason_code="dangerous_command",
            risk_tags=(CommandRiskTag.DANGEROUS_DOWNLOAD_EXECUTION.value,),
            commands=analyzed,
            normalized_command=raw,
        )

    risk_tags: list[str] = []
    normalized = raw
    for segment in analyzed:
        segment_text = segment.text.strip()
        if not segment_text:
            continue
        wrapper_inner = _unwrap_wrapper(segment_text)
        if wrapper_inner is not None:
            inner_report = analyze_command(wrapper_inner, cwd=cwd, ctx=ctx)
            if not inner_report.allowed:
                return block_report(
                    reason="Wrapper command exposes a blocked inner command.",
                    reason_code=inner_report.reason_code or "dangerous_command",
                    risk_tags=tuple(
                        dict.fromkeys(
                            (CommandRiskTag.WRAPPER_COMMAND.value, *inner_report.risk_tags)
                        )
                    ),
                    commands=analyzed,
                    normalized_command=normalized,
                )
        git_result = git_risk(segment_text, ctx=ctx, cwd=cwd)
        if git_result is not None:
            reason, reason_code, risk_tag, *rest = git_result
            risk_tags.append(risk_tag)
            report_factory = ask_report if _is_ask_result(rest) else block_report
            return report_factory(
                reason=reason,
                reason_code=reason_code,
                risk_tags=tuple(dict.fromkeys(risk_tags)),
                commands=analyzed,
                normalized_command=normalized,
            )
        bash_result = bash_risk(segment_text, ctx=ctx, cwd=cwd)
        if bash_result is not None:
            reason, reason_code, risk_tag = bash_result
            risk_tags.append(risk_tag)
            return block_report(
                reason=reason,
                reason_code=reason_code,
                risk_tags=tuple(dict.fromkeys(risk_tags)),
                commands=analyzed,
                normalized_command=normalized,
            )
        sed_result = sed_risk(segment_text)
        if sed_result is not None:
            reason, reason_code, risk_tag = sed_result
            risk_tags.append(risk_tag)
            return block_report(
                reason=reason,
                reason_code=reason_code,
                risk_tags=tuple(dict.fromkeys(risk_tags)),
                commands=analyzed,
                normalized_command=normalized,
            )
        readonly_result = readonly_risk(segment_text)
        if readonly_result is not None:
            reason, reason_code, risk_tag, *rest = readonly_result
            risk_tags.append(risk_tag)
            report_factory = ask_report if _is_ask_result(rest) else block_report
            return report_factory(
                reason=reason,
                reason_code=reason_code,
                risk_tags=tuple(dict.fromkeys(risk_tags)),
                commands=analyzed,
                normalized_command=normalized,
            )
        path_result = path_risk(segment_text, ctx=ctx, cwd=cwd)
        if path_result is not None:
            reason, reason_code, risk_tag = path_result
            risk_tags.append(risk_tag)
            return block_report(
                reason=reason,
                reason_code=reason_code,
                risk_tags=tuple(dict.fromkeys(risk_tags)),
                commands=analyzed,
                normalized_command=normalized,
            )

    return allow_report(commands=analyzed, normalized_command=normalized)


def _contains_cd_then_git(commands: tuple[AnalyzedCommand, ...]) -> bool:
    seen_cd = False
    for command in commands:
        stripped = command.text.strip().lower()
        if stripped.startswith("cd "):
            seen_cd = True
            continue
        if seen_cd and stripped.split()[:1] == ["git"]:
            return True
    return False


def _git_compound_attack_report(commands: tuple[AnalyzedCommand, ...], raw: str) -> CommandSecurityReport | None:
    git_index = _first_git_index(commands)
    if git_index is None or git_index == 0:
        return None
    before_git = commands[:git_index]
    joined = " ".join(command.text.lower() for command in before_git)
    if "../" in joined and ".git/" in joined:
        return block_report(
            reason="Git internal paths that re-enter the current workspace are blocked.",
            reason_code="dangerous_command",
            risk_tags=(CommandRiskTag.GIT_CWD_REENTRY.value,),
            commands=commands,
            normalized_command=raw,
        )
    if _mentions_all(joined, ("head", "objects", "refs")):
        return block_report(
            reason="Creating bare-repository git internals before running git is blocked.",
            reason_code="dangerous_command",
            risk_tags=(CommandRiskTag.GIT_BARE_REPO.value,),
            commands=commands,
            normalized_command=raw,
        )
    if any(command.text.strip().split()[:1] and command.text.strip().split()[0].lower() in _ARCHIVE_EXTRACTORS for command in before_git):
        return block_report(
            reason="Running git after archive extraction requires review.",
            reason_code="dangerous_command",
            risk_tags=(CommandRiskTag.GIT_ARCHIVE_THEN_GIT.value,),
            commands=commands,
            normalized_command=raw,
        )
    return None


def _first_git_index(commands: tuple[AnalyzedCommand, ...]) -> int | None:
    for index, command in enumerate(commands):
        if [token.lower() for token in command.text.strip().split()[:1]] == ["git"]:
            return index
    return None


def _is_ask_result(extra: list[str]) -> bool:
    return bool(extra and extra[0] == "ask")


def _mentions_all(text: str, needles: tuple[str, ...]) -> bool:
    words = set(text.replace("/", " ").replace(".", " ").split())
    return all(needle in words for needle in needles)


def _unwrap_wrapper(command: str) -> str | None:
    try:
        tokens = list(shell_tokens(command))
    except ValueError:
        return None
    if not tokens:
        return None
    base = tokens[0].lower()
    if base == "env":
        rest = _strip_env_prefix(tokens[1:])
    elif base == "timeout":
        rest = _strip_timeout_prefix(tokens[1:])
    elif base == "nice":
        rest = _strip_nice_prefix(tokens[1:])
    elif base == "stdbuf":
        rest = _strip_stdbuf_prefix(tokens[1:])
    elif base in {"nohup", "time"}:
        rest = tokens[1:]
    else:
        return None
    if not rest:
        return None
    shell_inner = _shell_c_inner(rest)
    if shell_inner is not None:
        return shell_inner
    return " ".join(rest)


def _strip_env_prefix(tokens: list[str]) -> list[str]:
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {"-u", "--unset"}:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        if "=" in token and not token.startswith("="):
            index += 1
            continue
        break
    return tokens[index:]


def _strip_timeout_prefix(tokens: list[str]) -> list[str]:
    index = 0
    while index < len(tokens) and tokens[index].startswith("-"):
        index += 1
    if index < len(tokens):
        index += 1
    return tokens[index:]


def _strip_nice_prefix(tokens: list[str]) -> list[str]:
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "-n":
            index += 2
            continue
        if token.startswith("-") and token[1:].isdigit():
            index += 1
            continue
        break
    return tokens[index:]


def _strip_stdbuf_prefix(tokens: list[str]) -> list[str]:
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {"-i", "-o", "-e"}:
            index += 2
            continue
        if token.startswith(("-i", "-o", "-e")):
            index += 1
            continue
        break
    return tokens[index:]


def _shell_c_inner(tokens: list[str]) -> str | None:
    if not tokens or tokens[0].lower() not in {"bash", "dash", "fish", "ksh", "sh", "zsh"}:
        return None
    for index, token in enumerate(tokens[1:], start=1):
        if token == "-c" and index + 1 < len(tokens):
            return tokens[index + 1]
    return None


def _contains_download_then_shell(commands: tuple[AnalyzedCommand, ...]) -> bool:
    for index, command in enumerate(commands[:-1]):
        first = command.text.strip().split()[:1]
        if not first or first[0].lower() not in {"curl", "wget"}:
            continue
        next_segment = commands[index + 1].text.strip().split()[:1]
        if next_segment and next_segment[0].lower() in {"sh", "bash", "zsh", "python", "python3", "node"}:
            return True
    return False


_ARCHIVE_EXTRACTORS = {"tar", "unzip", "7z", "7za", "gzip", "gunzip", "bsdtar"}
