from __future__ import annotations

import shlex
from dataclasses import dataclass, replace

from tree_sitter import Node

from .ast_parser import BashAst, parse_bash_ast
from .types import CommandRiskTag


@dataclass(frozen=True, slots=True)
class AstRedirect:
    op: str
    target: str
    fd: int | None = None


@dataclass(frozen=True, slots=True)
class AstSimpleCommand:
    argv: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    redirects: tuple[AstRedirect, ...]
    text: str


@dataclass(frozen=True, slots=True)
class AstSecurityResult:
    commands: tuple[AstSimpleCommand, ...] = ()
    reason: str | None = None
    reason_code: str | None = None
    risk_tag: str | None = None

    @property
    def blocked(self) -> bool:
        return self.reason is not None


_STRUCTURAL_NODES = {"program", "list", "pipeline", "redirected_statement"}
_SEPARATOR_NODES = {"&&", "||", "|", "|&", ";"}
_WORD_NODES = {"word", "number", "raw_string", "string", "concatenation"}
_EXPANSION_NODES = {
    "simple_expansion",
    "expansion",
    "arithmetic_expansion",
    "command_substitution",
    "process_substitution",
}
_SAFE_ENV_VARS = {
    "GOEXPERIMENT",
    "GOOS",
    "GOARCH",
    "CGO_ENABLED",
    "GO111MODULE",
    "RUST_BACKTRACE",
    "RUST_LOG",
    "NODE_ENV",
    "PYTHONUNBUFFERED",
    "PYTHONDONTWRITEBYTECODE",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
    "PYTEST_DEBUG",
    "LANG",
    "LANGUAGE",
    "LC_ALL",
    "LC_CTYPE",
    "LC_TIME",
    "CHARSET",
    "TERM",
    "COLORTERM",
    "NO_COLOR",
    "FORCE_COLOR",
    "TZ",
    "LS_COLORS",
    "LSCOLORS",
    "GREP_COLOR",
    "GREP_COLORS",
    "GCC_COLORS",
    "TIME_STYLE",
    "BLOCK_SIZE",
    "BLOCKSIZE",
}


def parse_for_security(command: str) -> AstSecurityResult:
    ast = parse_bash_ast(command)
    if ast.root.has_error:
        return AstSecurityResult(
            reason="Command could not be parsed as a complete Bash command.",
            reason_code="shell_parse_error",
            risk_tag=CommandRiskTag.SHELL_PARSE_ERROR.value,
        )
    collected = _collect_commands(ast, ast.root, redirects=())
    if isinstance(collected, AstSecurityResult):
        return collected
    return AstSecurityResult(commands=tuple(collected))


def _collect_commands(
    ast: BashAst,
    node: Node,
    *,
    redirects: tuple[AstRedirect, ...],
) -> list[AstSimpleCommand] | AstSecurityResult:
    if node.type == "command":
        return _extract_command(ast, node, redirects=redirects)
    if node.type == "redirected_statement":
        local_redirects = list(redirects)
        subject: Node | None = None
        for child in node.children:
            if child.type == "file_redirect":
                redirect = _extract_redirect(ast, child)
                if isinstance(redirect, AstSecurityResult):
                    return redirect
                local_redirects.append(redirect)
            elif child.type == "heredoc_redirect":
                # A heredoc body is literal stdin data, not executable shell.
                # The command that receives it is judged on its own; the body
                # never needs path/command analysis.
                continue
            elif child.is_named:
                if subject is not None:
                    return _too_complex(ast, child)
                subject = child
        if subject is None:
            return _too_complex(ast, node)
        collected = _collect_commands(ast, subject, redirects=tuple(local_redirects))
        if isinstance(collected, AstSecurityResult):
            return collected
        # Preserve the full redirected text (including the redirect operators and
        # targets) so the downstream boundary check sees the redirect
        # destinations rather than just the bare command.
        full_text = ast.text(node)
        return [replace(command, text=full_text) for command in collected]
    if node.type in {"program", "list", "pipeline"}:
        commands: list[AstSimpleCommand] = []
        for child in node.children:
            if not child.is_named:
                if child.type == "&":
                    return _too_complex(ast, child)
                if child.type in _SEPARATOR_NODES:
                    continue
                if not ast.text(child).strip():
                    continue
                return _too_complex(ast, child)
            if child.type not in _STRUCTURAL_NODES and child.type != "command":
                return _too_complex(ast, child)
            child_commands = _collect_commands(ast, child, redirects=redirects)
            if isinstance(child_commands, AstSecurityResult):
                return child_commands
            commands.extend(child_commands)
        return commands
    return _too_complex(ast, node)


def _extract_command(
    ast: BashAst,
    node: Node,
    *,
    redirects: tuple[AstRedirect, ...],
) -> list[AstSimpleCommand] | AstSecurityResult:
    argv: list[str] = []
    env: list[tuple[str, str]] = []
    for child in node.children:
        if child.type == "variable_assignment":
            assignment = _extract_assignment(ast, child)
            if isinstance(assignment, AstSecurityResult):
                return assignment
            env.append(assignment)
            continue
        if child.type == "command_name":
            value = _word_value(ast, child)
            if value is None:
                return _too_complex(ast, child)
            argv.append(value)
            continue
        if child.type in _WORD_NODES:
            value = _word_value(ast, child)
            if value is None:
                return _too_complex(ast, child)
            argv.append(value)
            continue
        if child.type == "file_redirect":
            redirect = _extract_redirect(ast, child)
            if isinstance(redirect, AstSecurityResult):
                return redirect
            redirects = (*redirects, redirect)
            continue
        if child.type in _EXPANSION_NODES:
            # Dynamic expansions / substitutions used as arguments. Admission
            # here is structural only — `ast_risk` has already decided whether
            # they are permitted at all (allowed solely under sandbox network
            # isolation), so by the time we reach this point they are in force.
            argv.append(ast.text(child))
            continue
        if child.is_named:
            return _too_complex(ast, child)
    if not argv:
        return _too_complex(ast, node)
    return [AstSimpleCommand(argv=tuple(argv), env=tuple(env), redirects=redirects, text=ast.text(node))]


def _extract_assignment(ast: BashAst, node: Node) -> tuple[str, str] | AstSecurityResult:
    name: str | None = None
    value_parts: list[str] = []
    for child in node.children:
        if child.type == "variable_name":
            name = ast.text(child)
        elif child.type in _WORD_NODES:
            value = _word_value(ast, child)
            if value is None:
                return _too_complex(ast, child)
            value_parts.append(value)
        elif child.is_named:
            return _too_complex(ast, child)
    if not name:
        return _too_complex(ast, node)
    if name not in _SAFE_ENV_VARS:
        return AstSecurityResult(
            reason=f"Environment variable {name} can alter command execution and is blocked.",
            reason_code="dangerous_command",
            risk_tag=CommandRiskTag.DANGEROUS_VARIABLE.value,
        )
    return name, "".join(value_parts)


def _extract_redirect(ast: BashAst, node: Node) -> AstRedirect | AstSecurityResult:
    op: str | None = None
    target: str | None = None
    fd: int | None = None
    for child in node.children:
        text = ast.text(child)
        if not child.is_named:
            # Anonymous tokens are either a leading numeric file descriptor or
            # the redirect operator itself (>, >>, <, >&, &>, <&, ...).
            if text.isdigit():
                fd = int(text)
            elif text.strip():
                op = text
            continue
        # `file_descriptor` / `number` appear both as the source descriptor that
        # precedes the operator (the `2` in `2>&1`) and as a descriptor-
        # duplication target (the `1` in `2>&1`, the `2` in `>&2`). Before the
        # operator they are the source fd; after it they are the dup target.
        # Either way this is pure descriptor wiring with no filesystem/network
        # effect, so we record it structurally instead of bailing out.
        if child.type in {"file_descriptor", "number"}:
            if op is None:
                fd = int(text) if text.isdigit() else fd
            else:
                target = text
            continue
        if child.type in _WORD_NODES:
            target = _word_value(ast, child)
            continue
        # An unresolvable target (e.g. expansion / command substitution used as a
        # redirect destination). The runtime path policy treats unresolved
        # destinations conservatively; surface it as a path-ish target so the
        # boundary check downstream can reject it rather than guessing here.
        target = ast.text(child)
    if op is None:
        return _too_complex(ast, node)
    return AstRedirect(op=op, target=target or "", fd=fd)


def _word_value(ast: BashAst, node: Node) -> str | None:
    text = ast.text(node)
    try:
        tokens = shlex.split(text, posix=True)
    except ValueError:
        return None
    if len(tokens) != 1:
        return None
    return tokens[0]


def _too_complex(ast: BashAst, node: Node) -> AstSecurityResult:
    return AstSecurityResult(
        reason=f"Shell syntax '{node.type}' is too complex to analyze safely.",
        reason_code="command_too_complex",
        risk_tag=CommandRiskTag.TOO_COMPLEX.value,
    )
