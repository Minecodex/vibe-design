from __future__ import annotations

import re
import shlex
import unicodedata

from .ast_parser import parse_bash_ast
from .types import CommandRiskTag

_DANGEROUS_VARIABLES = {"IFS", "BASH_ENV", "ENV", "SHELLOPTS", "PROMPT_COMMAND"}
_ZSH_DANGEROUS_COMMANDS = {
    "zmodload",
    "emulate",
    "sysopen",
    "sysread",
    "syswrite",
    "sysseek",
    "zpty",
    "ztcp",
    "zsocket",
    "mapfile",
    "zf_rm",
    "zf_mv",
    "zf_ln",
    "zf_chmod",
    "zf_chown",
    "zf_mkdir",
    "zf_rmdir",
    "zf_chgrp",
}
_NETWORK_DEVICE_RE = re.compile(r"/dev/(?:tcp|udp)/[^/\s\"'`$]+/\d+", re.I)
_PROC_ENVIRON_RE = re.compile(r"/proc/(?:self|\d+)/environ\b", re.I)
_BRACE_EXPANSION_RE = re.compile(r"(?<!['\"])\{[^{}\s]*[,\.]{1,2}[^{}\s]*\}")
_GO_TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")
_BACKSLASH_OBFUSCATION_RE = re.compile(r"\\(?:\s|[&|;<>])")
_ANSI_C_QUOTE_RE = re.compile(r"\$'(?:[^'\\]|\\.)*'")


# Verdict markers carried alongside (reason, reason_code, risk_tag). Mirrors
# claude-code's bashSecurity.ts split: dynamic expansions / obfuscation that we cannot
# prove safe are 'ask' (auto-allowed when the OS sandbox is in force), while a small set
# of genuinely dangerous constructs that alter parsing/leak the environment are 'deny'.
_ASK = "ask"
_DENY = "block"


def ast_risk(command: str) -> tuple[str, str, str, str] | None:
    text_result = _text_risk(command)
    if text_result is not None:
        return text_result

    ast = parse_bash_ast(command)
    if ast.root.has_error:
        # An unparseable command cannot be analyzed at all; keep it a hard block rather
        # than relying on the sandbox to contain an unknown structure.
        return (
            "Command could not be parsed as a complete Bash command.",
            "shell_parse_error",
            CommandRiskTag.SHELL_PARSE_ERROR.value,
            _DENY,
        )

    for node in ast.walk():
        # Dynamic shell expansions and substitutions expand to values we cannot resolve
        # at analysis time. Their filesystem effects are bounded by the workspace path
        # policy and the OS sandbox mount set, so they are 'ask' (→ auto-allowed when
        # sandboxed), not a hard block.
        if node.type == "command_substitution":
            return (
                "Command substitution cannot be statically verified.",
                "dangerous_command",
                CommandRiskTag.COMMAND_SUBSTITUTION.value,
                _ASK,
            )
        if node.type == "process_substitution":
            return (
                "Process substitution cannot be statically verified.",
                "dangerous_command",
                CommandRiskTag.PROCESS_SUBSTITUTION.value,
                _ASK,
            )
        if node.type == "expansion":
            return (
                "Parameter expansion cannot be statically verified.",
                "dangerous_command",
                CommandRiskTag.PARAMETER_EXPANSION.value,
                _ASK,
            )
        if node.type == "arithmetic_expansion":
            risk_tag = (
                CommandRiskTag.LEGACY_ARITHMETIC_EXPANSION.value
                if ast.text(node).startswith("$[")
                else CommandRiskTag.PARAMETER_EXPANSION.value
            )
            return (
                "Arithmetic expansion cannot be statically verified.",
                "dangerous_command",
                risk_tag,
                _ASK,
            )
        if node.type == "simple_expansion":
            variable = _variable_name(ast, node)
            if variable in _DANGEROUS_VARIABLES:
                return (
                    "Shell variable expansion can alter command parsing or execution.",
                    "dangerous_command",
                    CommandRiskTag.DANGEROUS_VARIABLE.value,
                    _DENY,
                )
            return (
                "Parameter expansion cannot be statically verified.",
                "dangerous_command",
                CommandRiskTag.PARAMETER_EXPANSION.value,
                _ASK,
            )
        if node.type == "command":
            command_name = _command_name(ast, node)
            if command_name in _ZSH_DANGEROUS_COMMANDS:
                return (
                    "Zsh command forms that can bypass shell policy are blocked.",
                    "dangerous_command",
                    CommandRiskTag.SHELL_OBFUSCATION.value,
                    _DENY,
                )
    return None


def _text_risk(command: str) -> tuple[str, str, str, str] | None:
    if _PROC_ENVIRON_RE.search(command):
        return (
            "Reading process environment is blocked.",
            "dangerous_command",
            CommandRiskTag.DANGEROUS_VARIABLE.value,
            _DENY,
        )
    if _NETWORK_DEVICE_RE.search(command):
        return (
            "Bash network device redirect cannot be statically verified.",
            "dangerous_command",
            CommandRiskTag.NETWORK_DEVICE_REDIRECT.value,
            _ASK,
        )
    # Obfuscation that exists to defeat static analysis (encoded bytes, comment desync,
    # invisible separators) stays a hard block — it has no legitimate use and admitting
    # it would let a dangerous payload skip the per-command checks below.
    if _ANSI_C_QUOTE_RE.search(command):
        return (
            "ANSI-C shell quoting is blocked.",
            "dangerous_command",
            CommandRiskTag.SHELL_OBFUSCATION.value,
            _DENY,
        )
    jq_risk = _jq_risk(command)
    if jq_risk is not None:
        return jq_risk
    if any(_is_unicode_whitespace(ch) for ch in command):
        return (
            "Unicode whitespace in shell commands is blocked.",
            "dangerous_command",
            CommandRiskTag.SHELL_OBFUSCATION.value,
            _DENY,
        )
    if _has_dangerous_backslash_obfuscation(command):
        return (
            "Backslash-escaped whitespace or operators are blocked.",
            "dangerous_command",
            CommandRiskTag.SHELL_OBFUSCATION.value,
            _DENY,
        )
    if _has_mid_word_hash(command):
        return (
            "Mid-word hash characters are blocked in shell commands.",
            "dangerous_command",
            CommandRiskTag.SHELL_OBFUSCATION.value,
            _DENY,
        )
    # Brace expansion (e.g. cp x.{js,css}) is a legitimate shell feature we cannot
    # statically resolve, so it is 'ask' (auto-allowed under sandbox) rather than blocked.
    command_without_templates = _GO_TEMPLATE_RE.sub("", command)
    if _BRACE_EXPANSION_RE.search(command_without_templates):
        return (
            "Brace expansion cannot be statically verified.",
            "dangerous_command",
            CommandRiskTag.SHELL_OBFUSCATION.value,
            _ASK,
        )
    return None


def _has_mid_word_hash(command: str) -> bool:
    quote: str | None = None
    escaped = False
    for index, ch in enumerate(command):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if quote is not None:
            if ch == quote:
                quote = None
            continue
        if ch in {"'", '"'}:
            quote = ch
            continue
        if ch == "#":
            before = command[index - 1] if index > 0 else " "
            after = command[index + 1] if index + 1 < len(command) else " "
            return not before.isspace() and not after.isspace()
    return False


def _jq_risk(command: str) -> tuple[str, str, str, str] | None:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    if not tokens or tokens[0] != "jq":
        return None
    expressions: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in {"-f", "--from-file"}:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        expressions.append(token)
        break
    if any("system(" in expression for expression in expressions):
        return (
            "Jq expressions that execute commands are blocked.",
            "dangerous_command",
            CommandRiskTag.SHELL_OBFUSCATION.value,
            _DENY,
        )
    return None


def _is_unicode_whitespace(ch: str) -> bool:
    return ch != " " and unicodedata.category(ch) == "Zs"


def _has_dangerous_backslash_obfuscation(command: str) -> bool:
    matches = list(_BACKSLASH_OBFUSCATION_RE.finditer(command))
    if not matches:
        return False
    return any(match.group(0) != r"\;" for match in matches)


def _variable_name(ast, node) -> str | None:  # noqa: ANN001
    for child in node.children:
        if child.type == "variable_name":
            return ast.text(child)
    return None


def _command_name(ast, node) -> str | None:  # noqa: ANN001
    for child in node.children:
        if child.type != "command_name":
            continue
        words = [ast.text(grandchild) for grandchild in child.children if grandchild.is_named]
        return "".join(words).lower() if words else ast.text(child).lower()
    return None
