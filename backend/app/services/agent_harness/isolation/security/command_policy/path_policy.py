from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

from .splitter import shell_tokens
from .types import CommandRiskTag

_SENSITIVE_PATH_MARKERS = (
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.config/gcloud",
    "~/.azure",
    "~/.docker/config.json",
    ".git/hooks",
    ".git/config",
    ".git/refs",
    ".git/objects",
    ".git/",
    "/.ssh",
    "/.aws",
    "/.gnupg",
    "/.config/gcloud",
    "/.azure",
    "/.docker/config.json",
    "/.git/hooks",
    "/.git/config",
    "/.git/refs",
    "/.git/objects",
)

_REDIRECT_TOKEN_RE = re.compile(r"^(?:[0-9]?(?:<|>|>>)|&>|>&|[0-9]?>&[0-9]?)$")
_INLINE_REDIRECT_RE = re.compile(r"^(?:[0-9]?(?:<|>|>>)|&>|>&)(.+)$")
_INLINE_FD_OR_FILE_REDIRECT_RE = re.compile(r"^[0-9]?>&(.+)$")


def path_risk(command: str, *, ctx, cwd: str) -> tuple[str, str, str] | None:
    lowered = command.lower()
    for marker in _SENSITIVE_PATH_MARKERS:
        if marker.lower() in lowered:
            if ".git" in marker:
                return (
                    "Git internal paths are blocked.",
                    "dangerous_command",
                    CommandRiskTag.GIT_INTERNAL_WRITE.value,
                )
            return (
                "Command references a sensitive credential or shell configuration path.",
                "path_outside_workspace",
                CommandRiskTag.PATH_OUTSIDE_WORKSPACE.value,
            )

    try:
        tokens = shell_tokens(command)
    except ValueError:
        return None

    for idx, token in enumerate(tokens):
        target: str | None = None
        if _REDIRECT_TOKEN_RE.match(token) and idx + 1 < len(tokens):
            target = tokens[idx + 1]
        else:
            fd_or_file = _INLINE_FD_OR_FILE_REDIRECT_RE.match(token)
            if fd_or_file and not fd_or_file.group(1).isdigit():
                target = fd_or_file.group(1)
            else:
                inline = _INLINE_REDIRECT_RE.match(token)
                if inline:
                    target = inline.group(1)
        if target and _redirect_target_escapes(target, ctx=ctx, cwd=cwd):
            return (
                "Command redirects outside the workspace.",
                "path_outside_workspace",
                CommandRiskTag.PATH_OUTSIDE_WORKSPACE.value,
            )

    for token in _extract_path_arguments(tokens):
        if _token_path_escapes(token, ctx=ctx, cwd=cwd):
            return (
                "Command references a path outside the workspace.",
                "path_outside_workspace",
                CommandRiskTag.PATH_OUTSIDE_WORKSPACE.value,
            )
    return None


_SIMPLE_PATH_COMMANDS = {
    "base64",
    "cat",
    "column",
    "cut",
    "du",
    "file",
    "head",
    "hexdump",
    "md5sum",
    "nl",
    "od",
    "paste",
    "sha1sum",
    "sha256sum",
    "sort",
    "stat",
    "strings",
    "tail",
    "tr",
    "uniq",
    "wc",
}
_VALUE_FLAGS = {
    "-A",
    "-B",
    "-C",
    "-L",
    "-N",
    "-b",
    "-c",
    "-d",
    "-f",
    "-j",
    "-k",
    "-m",
    "-n",
    "-o",
    "-s",
    "-t",
    "-w",
    "--after-context",
    "--before-context",
    "--bytes",
    "--characters",
    "--context",
    "--delimiter",
    "--delimiters",
    "--field-separator",
    "--fields",
    "--format",
    "--key",
    "--lines",
    "--max-count",
    "--max-depth",
    "--output",
    "--sort",
    "--wrap",
}
_GIT_VALUE_FLAGS = {
    "-G",
    "-L",
    "-S",
    "-n",
    "--abbrev",
    "--after",
    "--author",
    "--before",
    "--color",
    "--committer",
    "--contains",
    "--count",
    "--date",
    "--diff-algorithm",
    "--diff-filter",
    "--dirty",
    "--format",
    "--grep",
    "--inter-hunk-context",
    "--max-count",
    "--merged",
    "--pretty",
    "--relative",
    "--since",
    "--sort",
    "--until",
    "--word-diff",
    "--word-diff-regex",
}


def _extract_path_arguments(tokens: tuple[str, ...]) -> tuple[str, ...]:
    if not tokens:
        return ()
    base = tokens[0].lower()
    args = list(tokens[1:])
    if base == "cd":
        return tuple(_positional_args(args, value_flags=set()))
    if base in _SIMPLE_PATH_COMMANDS:
        return tuple(_positional_args(args, value_flags=_VALUE_FLAGS))
    if base == "grep":
        return tuple(_grep_paths(args))
    if base == "rg":
        return tuple(_rg_paths(args))
    if base == "find":
        return tuple(_find_paths(args))
    if base in {"fd", "fdfind"}:
        return tuple(_fd_paths(args))
    if base == "sed":
        return tuple(_sed_paths(args))
    if base == "git":
        return tuple(_positional_args(args[1:] if args else [], value_flags=_GIT_VALUE_FLAGS))
    if base == "diff":
        return tuple(_positional_args(args, value_flags={*_VALUE_FLAGS, "--label"}))
    path_tokens: list[str] = []
    for index, token in enumerate(tokens):
        normalized = _normalize_token_path(token)
        if index == 0 and _is_allowed_absolute_executable(normalized):
            continue
        if _looks_like_path_argument(normalized):
            path_tokens.append(token)
    return tuple(path_tokens)


def _positional_args(args: list[str], *, value_flags: set[str]) -> list[str]:
    values: list[str] = []
    index = 0
    after_double_dash = False
    while index < len(args):
        token = args[index]
        if after_double_dash:
            values.append(token)
            index += 1
            continue
        if token == "--":
            after_double_dash = True
            index += 1
            continue
        flag = token.split("=", 1)[0] if token.startswith("--") else token
        if token.startswith("-") and token != "-":
            if flag in value_flags and "=" not in token and index + 1 < len(args):
                index += 2
            else:
                index += 1
            continue
        values.append(token)
        index += 1
    return values


def _grep_paths(args: list[str]) -> list[str]:
    paths: list[str] = []
    pattern_seen = False
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            remaining = args[index + 1 :]
            if not pattern_seen and remaining:
                return remaining[1:]
            return remaining
        flag = token.split("=", 1)[0] if token.startswith("--") else token
        if flag in {"-f", "--file", "--exclude-from"}:
            value = _flag_value(args, index)
            if value is not None:
                paths.append(value)
            index += 1 if "=" in token else 2
            continue
        if flag in {"-e", "--regexp", "-A", "-B", "-C", "--include", "--exclude", "--exclude-dir"}:
            index += 1 if "=" in token else 2
            if flag in {"-e", "--regexp"}:
                pattern_seen = True
            continue
        if token.startswith("-") and token != "-":
            index += 1
            continue
        if pattern_seen:
            paths.append(token)
        else:
            pattern_seen = True
        index += 1
    return paths


def _rg_paths(args: list[str]) -> list[str]:
    paths: list[str] = []
    pattern_seen = False
    files_mode = False
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            remaining = args[index + 1 :]
            if files_mode:
                return [*paths, *remaining]
            if not pattern_seen and remaining:
                return [*paths, *remaining[1:]]
            return [*paths, *remaining]
        flag = token.split("=", 1)[0] if token.startswith("--") else token
        if flag in {"-f", "--file", "--ignore-file"}:
            value = _flag_value(args, index)
            if value is not None:
                paths.append(value)
            index += 1 if "=" in token else 2
            continue
        if flag == "--files":
            files_mode = True
            index += 1
            continue
        if flag in {"-e", "--regexp", "-g", "--glob", "--iglob", "-t", "--type", "-T", "--type-not", "-A", "-B", "-C", "-m", "--max-count", "--max-filesize", "--sort", "--sortr"}:
            index += 1 if "=" in token else 2
            if flag in {"-e", "--regexp"}:
                pattern_seen = True
            continue
        if token.startswith("-") and token != "-":
            index += 1
            continue
        if files_mode or pattern_seen:
            paths.append(token)
        else:
            pattern_seen = True
        index += 1
    return paths


def _find_paths(args: list[str]) -> list[str]:
    paths: list[str] = []
    for token in args:
        if token == "--":
            continue
        if token.startswith("-") or token in {"!", "(", ")"}:
            break
        paths.append(token)
    return paths


def _fd_paths(args: list[str]) -> list[str]:
    paths: list[str] = []
    pattern_seen = False
    index = 0
    while index < len(args):
        token = args[index]
        flag = token.split("=", 1)[0] if token.startswith("--") else token
        if flag in {"--search-path", "--base-directory", "--ignore-file"}:
            value = _flag_value(args, index)
            if value is not None:
                paths.append(value)
            index += 1 if "=" in token else 2
            continue
        if flag in {"-E", "--exclude", "-e", "--extension", "-d", "--max-depth", "--min-depth", "--exact-depth", "-t", "--type", "-S", "--size", "--changed-within", "--changed-before", "-o", "--owner", "-c", "--color", "-j", "--threads", "--max-results"}:
            index += 1 if "=" in token else 2
            continue
        if token.startswith("-") and token != "-":
            index += 1
            continue
        if pattern_seen:
            paths.append(token)
        else:
            pattern_seen = True
        index += 1
    return paths


def _sed_paths(args: list[str]) -> list[str]:
    paths: list[str] = []
    script_seen = False
    index = 0
    while index < len(args):
        token = args[index]
        lowered = token.lower()
        if lowered in {"-e", "--expression"}:
            script_seen = True
            index += 2
            continue
        if lowered in {"-f", "--file"}:
            if index + 1 < len(args):
                paths.append(args[index + 1])
            index += 2
            continue
        if token.startswith("-") and token != "-":
            index += 1
            continue
        if script_seen:
            paths.append(token)
        else:
            script_seen = True
        index += 1
    return paths


def _flag_value(args: list[str], index: int) -> str | None:
    token = args[index]
    if token.startswith("--") and "=" in token:
        return token.split("=", 1)[1]
    if index + 1 < len(args):
        return args[index + 1]
    return None


def _redirect_target_escapes(target: str, *, ctx, cwd: str) -> bool:
    normalized = _normalize_token_path(target)
    if not normalized or normalized in {"/dev/null", "-"}:
        return False
    # Output redirection (`>`, `>>`) is always a write; it must land in the
    # writable project tree.
    return _normalized_path_escapes(normalized, ctx=ctx, cwd=cwd, writable=True)


def _token_path_escapes(token: str, *, ctx, cwd: str) -> bool:
    normalized = _normalize_token_path(token)
    if not _looks_like_path_argument(normalized):
        return False
    # Command path operands mix reads (e.g. `cp` source) and writes (`cp`
    # destination); the runtime sandbox enforces the read-only roots, so here we
    # only require the landing point to stay inside the workspace (read set).
    return _normalized_path_escapes(normalized, ctx=ctx, cwd=cwd, writable=False)


def _normalize_token_path(token: str) -> str:
    raw = str(token or "").strip().strip("'\"")
    if "=" in raw and raw.startswith("-"):
        raw = raw.split("=", 1)[1]
    return unquote(raw).replace("\\", "/")


def _is_allowed_absolute_executable(normalized: str) -> bool:
    try:
        path = Path(normalized)
    except Exception:
        return False
    if not path.is_absolute():
        return False
    try:
        return path.resolve() == Path(sys.executable).resolve()
    except OSError:
        return False


def _looks_like_path_argument(normalized: str) -> bool:
    if not normalized or normalized in {"-", "/dev/null"}:
        return False
    if "://" in normalized:
        return False
    return (
        normalized == ".."
        or normalized.startswith(("/", "~", "./", "../"))
        or "/.." in normalized
        or "../" in normalized
        or "/" in normalized
    )


def _normalized_path_escapes(normalized: str, *, ctx, cwd: str, writable: bool) -> bool:
    # A leading ~ is shell-expanded to $HOME at runtime; we never see the real
    # target, so treat it as an escape (TOCTOU). Reject URL-like tokens too.
    if normalized.startswith("~"):
        return True
    if "://" in normalized:
        return True
    if ctx is None:
        # Without a context we cannot resolve the landing point against the
        # workspace roots; fall back to the conservative string-level guard.
        return normalized.startswith("/") or ".." in Path(normalized).parts
    base = _resolve_cwd(ctx, cwd)
    if base is None:
        return True
    # Resolve the *landing point* (collapsing `..` and symlinks) and judge it
    # against the workspace roots, instead of rejecting any literal `..`. This
    # mirrors the runtime sandbox boundary (build_policy) and lets legitimate
    # cross-root reads such as `cp ../../skill/assets/x .` through, while still
    # blocking anything that resolves outside the conversation workspace.
    try:
        resolved = (base / normalized).resolve()
    except (OSError, RuntimeError, ValueError):
        return True
    return not _path_within_workspace_roots(resolved, ctx, writable=writable)


def _path_within_workspace_roots(resolved: Path, ctx, *, writable: bool) -> bool:
    # Writes must land in the writable project tree; reads may also come from the
    # read-only roots (skill / references / published / active skill). This reuses
    # the same root set the cwd guard and runtime sandbox already enforce.
    from app.services.agent_harness.isolation.security.paths import allowed_cwd_roots

    roots: tuple[Path, ...] = (ctx.project_dir.resolve(),) if writable else allowed_cwd_roots(ctx)
    for root in roots:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _resolve_cwd(ctx, cwd: str) -> Path | None:
    raw = str(cwd or "work").replace("\\", "/").strip().strip("/")
    if raw in {"", ".", "work", "project"}:
        root = _active_artifact_work_root(ctx)
        return (ctx.project_dir / root).resolve() if root else ctx.project_dir.resolve()
    if raw == "project:":
        return ctx.project_dir.resolve()
    if raw.startswith("project:"):
        fragment = raw.split(":", 1)[1].strip().strip("/")
        if not fragment:
            return ctx.project_dir.resolve()
        if ".." in Path(fragment).parts:
            return None
        candidate = (ctx.project_dir / fragment).resolve()
        try:
            candidate.relative_to(ctx.project_dir.resolve())
            return candidate
        except ValueError:
            return None
    if raw == "skill":
        skill_root = getattr(ctx, "active_skill_dir", None) or getattr(ctx, "skill_dir", None)
        return Path(skill_root).resolve() if skill_root else None
    if raw == "references":
        return ctx.references_dir.resolve()
    if raw == "published":
        return ctx.published_dir.resolve()
    if raw.startswith("project/"):
        fragment = raw.removeprefix("project/").strip("/")
        if ".." in Path(fragment).parts:
            return None
        candidate = (ctx.project_dir / fragment).resolve()
        try:
            candidate.relative_to(ctx.project_dir.resolve())
            return candidate
        except ValueError:
            return None
    return None


def _active_artifact_work_root(ctx) -> str | None:
    workspace_session = getattr(ctx, "workspace_runtime_session", None)
    if isinstance(workspace_session, dict):
        value = str(workspace_session.get("artifact_work_root") or "").replace("\\", "/").strip().strip("/")
        if value:
            return value.removeprefix("project/").strip("/") or None
        agent_cwd = str(workspace_session.get("agent_cwd") or "").replace("\\", "/").strip().strip("/")
        if agent_cwd.startswith("project/"):
            return agent_cwd.removeprefix("project/").strip("/") or None
    session = getattr(ctx, "prepared_workspace", None)
    value = str(getattr(session, "artifact_work_root", "") or "").replace("\\", "/").strip().strip("/")
    if value:
        return value.removeprefix("project/").strip("/") or None
    value = str(getattr(ctx, "artifact_work_root", "") or "").replace("\\", "/").strip().strip("/")
    return value.removeprefix("project/").strip("/") or None

