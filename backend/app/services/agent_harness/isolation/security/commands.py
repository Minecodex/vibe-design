from __future__ import annotations

import re
from pathlib import Path

from app.services.agent_harness.isolation.security.command_policy.splitter import shell_tokens

from .types import NormalizationEntry

SEMANTIC_ERRORS = [
    (re.compile(r"\bSyntaxError\b", re.I), "SyntaxError", "syntax_error"),
    (re.compile(r"Traceback \(most recent call last\):", re.I), "Traceback", "traceback"),
    (re.compile(r"(?:^|\n|: )\s*(?:tsx|jq|pnpm|npm|node|python3?)\s*:\s*(?:not found|command not found)", re.I), "CommandNotFound", "runtime_dependency_missing"),
    (re.compile(r"Cannot find module|MODULE_NOT_FOUND|ModuleNotFoundError", re.I), "ModuleNotFoundError", "missing_dependency"),
    (re.compile(r"JSONDecodeError|Unexpected token .* in JSON|JSON\.parse", re.I), "JSONParseError", "data_serialization_error"),
    (re.compile(r"修复失败[:：]|validation failed|invalid syntax", re.I), "SemanticFailure", "semantic_failure"),
]

MAX_COMMAND_CHARS = 12_000
_LITERAL_ENV_CWD_VALUES = frozenset(
    {
        name
        for key in (
            "CONVERSATION_DIR",
            "HARNESS_PROJECT_DIR",
            "HARNESS_REFERENCES_DIR",
            "HARNESS_REFERENCE_INPUTS_DIR",
            "HARNESS_REFERENCE_SOURCES_DIR",
            "HARNESS_REFERENCE_GENERATED_DIR",
            "HARNESS_SKILL_ROOT",
            "HARNESS_PUBLISHED_DIR",
        )
        for name in (key, f"${key}", f"${{{key}}}")
    }
)

_LEADING_CD_PROJECT_RE = re.compile(r"^\s*cd\s+(['\"]?)project\1\s*(?:&&|;)\s*(.+?)\s*$", re.IGNORECASE)
_LEADING_PROJECT_SCRIPT_RE = re.compile(
    r"^\s*(python(?:3)?|py|node)\s+(['\"]?)project[\\/](.+?)\2(\s+.*)?$",
    re.IGNORECASE,
)
_COMPOUND_SHELL_RE = re.compile(r"(?:&&|\|\||[;|])")
_REDIRECT_TOKENS = {">", ">>", "1>", "1>>", "2>", "2>>", "&>"}
_SAFE_PROJECT_PATH_BASES = {
    "base64",
    "cat",
    "du",
    "file",
    "grep",
    "head",
    "ls",
    "node",
    "nl",
    "python",
    "python3",
    "py",
    "rg",
    "stat",
    "tail",
    "wc",
}
_DESTRUCTIVE_PROJECT_PATH_BASES = {"cp", "mv", "rm", "rmdir", "unlink"}
_HIDDEN_CONVERSATION_ROOT_NAMES = {".agent", ".meta", "logs"}


def validate_command_text(command: str) -> tuple[str | None, str | None]:
    if len(command) > MAX_COMMAND_CHARS:
        return (
            "Command too long. Inspect or update the target script with write_file or edit_file, "
            "then rerun a short command such as python generate_doc.py.",
            "command_too_long",
        )
    lowered = command.lower()
    if any(marker in lowered for marker in ("cat <<", "tee ", " > ", " >> ")) and len(command) > 1000:
        return (
            "Large shell-based file writes are blocked. Use write_file or edit_file, then rerun a short command.",
            "large_shell_write_blocked",
        )
    return None, None


def normalize_project_cwd_command(command: str) -> tuple[str, NormalizationEntry] | None:
    current = str(command or "").strip()
    if not current:
        return None

    cd_match = _LEADING_CD_PROJECT_RE.match(current)
    if cd_match:
        remainder = cd_match.group(2).strip()
        nested = normalize_project_cwd_command(remainder)
        normalized_command = nested[0] if nested else remainder
        return normalized_command, NormalizationEntry(
            warning=(
                "Removed redundant project-directory prefixing from the command. "
                "Commands already run from project/ by default; use project-cwd-relative paths such as 'python foo.py'."
            ),
            normalized_value=normalized_command,
            original_value=current,
            kind="redundant_project_prefix",
        )

    runner_match = _LEADING_PROJECT_SCRIPT_RE.match(current)
    if runner_match:
        executable, quote, script_path, trailing = runner_match.groups()
        normalized_command = f"{executable} {quote}{script_path}{quote}{trailing or ''}".strip()
        return normalized_command, NormalizationEntry(
            warning=(
                f"Removed redundant project/ prefix from command path '{executable} {quote}project/{script_path}{quote}'. "
                "Commands already run from project/ by default; use project-cwd-relative paths such as 'python foo.py'."
            ),
            normalized_value=normalized_command,
            original_value=current,
            kind="redundant_project_prefix",
        )

    rewritten = _rewrite_safe_project_path_tokens(current)
    if rewritten is None:
        return None
    normalized_command, rewrites = rewritten
    return normalized_command, NormalizationEntry(
        warning=(
            "Normalized shell path token(s) for cwd=project. "
            "Commands run from CONVERSATION_DIR/project, so project/foo.txt was rewritten to foo.txt. "
            f"Corrections: {', '.join(rewrites)}."
        ),
        normalized_value=normalized_command,
        original_value=current,
        kind="shell_path_normalization",
    )


def normalize_current_project_absolute_command(ctx, command: str) -> tuple[str, NormalizationEntry] | None:
    if ctx is None:
        return None
    current = _command_for_path_tokenizing(command)
    if not current or _COMPOUND_SHELL_RE.search(current):
        return None
    try:
        tokens = list(shell_tokens(current))
    except ValueError:
        return None
    if not tokens:
        return None
    base = tokens[0].lower()
    if base in _DESTRUCTIVE_PROJECT_PATH_BASES:
        if any(_absolute_path_under_project(ctx, token) for token in tokens[1:]):
            return None
        return None
    if base not in _SAFE_PROJECT_PATH_BASES:
        return None
    rewritten: list[str] = []
    rewrites: list[str] = []
    changed = False
    for index, token in enumerate(tokens):
        replacement = token
        if index > 0:
            project_relative = _absolute_path_under_project(ctx, token)
            if project_relative:
                replacement = project_relative
                rewrites.append(f"{_redacted_absolute_token(token)}->{replacement}")
                changed = True
        rewritten.append(_quote_shell_token(replacement))
    if not changed:
        return None
    normalized_command = " ".join(rewritten)
    return normalized_command, NormalizationEntry(
        warning=(
            "Rewrote absolute current-conversation project path(s) to project-cwd-relative paths. "
            "Commands already run from project/ by default; use relative paths next time. "
            f"Corrections: {', '.join(rewrites)}."
        ),
        normalized_value=normalized_command,
        original_value=current,
        kind="current_project_absolute_path",
    )


def absolute_hidden_root_diagnostic(ctx, command: str) -> str | None:
    if ctx is None:
        return None
    try:
        tokens = list(shell_tokens(_command_for_path_tokenizing(command)))
    except ValueError:
        return None
    conversation_dir = ctx.conversation_dir.resolve()
    for token in tokens[1:]:
        raw = str(token or "").strip().strip("'\"")
        try:
            path = Path(raw)
        except Exception:
            continue
        if not path.is_absolute():
            continue
        try:
            resolved = path.resolve()
            rel = resolved.relative_to(conversation_dir)
        except (OSError, ValueError):
            continue
        first = rel.parts[0] if rel.parts else ""
        if first in _HIDDEN_CONVERSATION_ROOT_NAMES:
            return (
                "Command references an internal conversation root that is not model-visible. "
                "Use project/, references/, skill/, or published/ paths only."
            )
    return None


def destructive_absolute_project_path_diagnostic(ctx, command: str) -> str | None:
    if ctx is None:
        return None
    try:
        tokens = list(shell_tokens(_command_for_path_tokenizing(command)))
    except ValueError:
        return None
    if not tokens or tokens[0].lower() not in _DESTRUCTIVE_PROJECT_PATH_BASES:
        return None
    if not any(_absolute_path_under_project(ctx, token) for token in tokens[1:]):
        return None
    return (
        "Destructive shell command uses an absolute path inside the current project. "
        "The runtime will not auto-rewrite destructive commands. Use a structured file tool, "
        "or rerun with an explicit verified project-cwd-relative path."
    )


def destructive_project_path_diagnostic(command: str) -> str | None:
    """Return a diagnostic when a destructive command contains likely redundant project/ paths."""
    try:
        tokens = list(shell_tokens(str(command or "").strip()))
    except ValueError:
        return None
    if not tokens or tokens[0].lower() not in _DESTRUCTIVE_PROJECT_PATH_BASES:
        return None
    if not any(_is_project_prefixed_path(token) for token in tokens[1:]):
        return None
    return (
        "Destructive shell command uses a project/ path while cwd is already project. "
        "The runtime will not auto-rewrite destructive commands. Use a structured file tool, "
        "or rerun with an explicit verified project-cwd-relative path."
    )


def ambiguous_project_path_diagnostic(command: str) -> str | None:
    try:
        tokens = list(shell_tokens(str(command or "").strip()))
    except ValueError:
        return None
    if not tokens or tokens[0].lower() not in _SAFE_PROJECT_PATH_BASES:
        return None
    for token in tokens[1:]:
        normalized = str(token or "").strip().strip("'\"").replace("\\", "/").lstrip("/")
        if normalized in {"project", "project/", "project/project"}:
            return (
                "Shell command path is ambiguous because cwd is already project. "
                "Use a specific project-cwd-relative path such as foo.txt, or a structured file tool."
            )
    return None


def literal_env_cwd_error(cwd: str) -> str | None:
    raw = str(cwd or "").replace("\\", "/").strip().strip("'\"").strip().strip("/")
    if raw in _LITERAL_ENV_CWD_VALUES:
        return (
            f"Invalid cwd '{cwd}': Use project, references, published, skill, or a concrete conversation-relative path. "
            "Environment variable names like HARNESS_PROJECT_DIR are available inside scripts, not as cwd values."
        )
    return None


def _rewrite_safe_project_path_tokens(command: str) -> tuple[str, list[str]] | None:
    if _COMPOUND_SHELL_RE.search(command):
        return None
    try:
        tokens = list(shell_tokens(command))
    except ValueError:
        return None
    if not tokens:
        return None
    base = tokens[0].lower()
    if base not in _SAFE_PROJECT_PATH_BASES:
        return None
    changed = False
    rewrites: list[str] = []
    rewritten: list[str] = []
    previous = ""
    for index, token in enumerate(tokens):
        replacement = token
        if index > 0 and (_is_project_prefixed_path(token) or previous in _REDIRECT_TOKENS):
            candidate = _strip_project_prefix(token)
            if candidate is None:
                return None
            replacement = candidate
            changed = True
            rewrites.append(f"{token}->{replacement}")
        rewritten.append(_quote_shell_token(replacement))
        previous = token
    if not changed:
        return None
    return " ".join(rewritten), rewrites


def _is_project_prefixed_path(token: str) -> bool:
    normalized = str(token or "").strip().strip("'\"").replace("\\", "/").lstrip("/")
    return normalized.startswith("project/") and ".." not in Path(normalized).parts


def _strip_project_prefix(token: str) -> str | None:
    raw = str(token or "").strip().strip("'\"").replace("\\", "/").lstrip("/")
    if raw in {"project", "project/"}:
        return None
    if raw.startswith("project/project/"):
        return raw[len("project/") :]
    if raw.startswith("project/"):
        return raw[len("project/") :]
    return None


def _absolute_path_under_project(ctx, token: str) -> str | None:
    raw = str(token or "").strip().strip("'\"")
    try:
        path = Path(raw)
    except Exception:
        return None
    if not path.is_absolute():
        return None
    try:
        resolved = path.resolve()
        rel = resolved.relative_to(ctx.project_dir.resolve())
    except (OSError, ValueError):
        return None
    if ".." in rel.parts or not rel.parts:
        return None
    return rel.as_posix()


def _redacted_absolute_token(token: str) -> str:
    name = Path(str(token or "").strip().strip("'\"")).name
    return f"<current-project>/{name}" if name else "<current-project>"


def _command_for_path_tokenizing(command: str) -> str:
    current = str(command or "").strip()
    if re.search(r"[A-Za-z]:\\", current):
        return current.replace("\\", "/")
    return current


def _quote_shell_token(token: str) -> str:
    if not token:
        return "''"
    if re.search(r"\s", token):
        return "'" + token.replace("'", "'\"'\"'") + "'"
    return token


def extract_command_diagnostics(*, cwd: Path, command: str, stdout: str, stderr: str) -> dict[str, object]:
    combined = "\n".join(part for part in (stdout, stderr) if part)
    metadata: dict[str, object] = {}

    semantic = detect_semantic(stdout, stderr)
    if semantic is not None:
        metadata.update(semantic)

    location = _first_file_location(combined)
    if location is not None:
        metadata.update(location)

    require_stack = _require_stack_files(combined)
    if require_stack:
        metadata["require_stack"] = require_stack

    if re.search(r"JSON\.parse|Unexpected token .* in JSON|JSONDecodeError", combined, re.I):
        metadata["failure_kind"] = "data_serialization_error"
        metadata["diagnostic_hint"] = "Read the JSON/JSONL file, repair its serialization, and rerun the command."
        inferred = _infer_json_inputs(cwd, command)
        if inferred:
            metadata["candidate_data_files"] = inferred

    if re.search(r"\bSyntaxError\b", combined, re.I):
        metadata.setdefault("diagnostic_hint", "Inspect the script syntax and rerun after fixing the file.")

    return metadata


def detect_semantic(*streams: str) -> dict[str, str] | None:
    combined = "\n".join(streams)
    for pattern, error_type, failure_kind in SEMANTIC_ERRORS:
        if pattern.search(combined):
            return {"error_type": error_type, "failure_kind": failure_kind}
    return None


def classify_failure_text(output: str, error_type: str | None = None) -> str:
    semantic = detect_semantic(output)
    if semantic and semantic.get("failure_kind"):
        return str(semantic["failure_kind"])
    lowered = (output or "").lower()
    if error_type == "SyntaxError" or "syntaxerror" in lowered or "invalid syntax" in lowered:
        return "syntax_error"
    if "timed out" in lowered or "timeout" in lowered:
        return "timeout"
    if "permission denied" in lowered or "sandbox denied" in lowered:
        return "permission_required"
    if "old_string not found" in lowered or "old_text" in lowered and "not found" in lowered:
        return "patch_target_not_found"
    if re.search(r"(?:^|\n|: )\s*(?:tsx|jq|pnpm|npm|node|python3?)\s*:\s*(?:not found|command not found)", output or "", re.I):
        return "runtime_dependency_missing"
    if (
        "path escapes workspace" in lowered
        or "cwd escapes workspace" in lowered
        or "must live under project/" in lowered
        or "dangerous command" in lowered
        or "blocked: dangerous command pattern" in lowered
    ):
        return "path_outside_workspace"
    if "file not found" in lowered:
        return "file_not_found"
    if "html dependency " in lowered:
        return "html_dependency_error"
    return "unknown_failure"


def _first_file_location(text: str) -> dict[str, object] | None:
    for line in text.splitlines():
        match = re.search(r"(?P<file>(?:[A-Za-z]:)?[/\\][^:\n\r]+?\.(?:js|mjs|cjs|json|jsonl|py)):(?P<line>\d+)(?::(?P<column>\d+))?", line)
        if match:
            payload: dict[str, object] = {
                "error_file": match.group("file").replace("\\", "/"),
                "error_line": int(match.group("line")),
            }
            if match.group("column"):
                payload["error_column"] = int(match.group("column"))
            return payload
    return None


def _require_stack_files(text: str) -> list[str]:
    files: list[str] = []
    in_stack = False
    for line in text.splitlines():
        if "Require stack:" in line:
            in_stack = True
            continue
        if not in_stack:
            continue
        stripped = line.strip()
        if not stripped.startswith("- "):
            break
        files.append(stripped[2:].replace("\\", "/"))
    return files


def _infer_json_inputs(cwd: Path, command: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(r"['\"]([^'\"]+\.(?:json|jsonl))['\"]", command):
        raw = match.group(1)
        path = Path(raw)
        resolved = path if path.is_absolute() else cwd / path
        if resolved.exists():
            candidates.append(str(resolved.resolve()).replace("\\", "/"))
    if not candidates:
        try:
            candidates = [
                str(path.resolve()).replace("\\", "/")
                for path in cwd.glob("*.json")
                if path.name not in {"package.json", "package-lock.json"}
            ]
        except Exception:
            candidates = []
    return candidates[:10]
