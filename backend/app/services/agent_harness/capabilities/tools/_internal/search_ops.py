from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import TYPE_CHECKING

from app.services.agent_harness.capabilities.tools._internal.file_ops import (
    workspace_path_metadata,
)

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

RG_TIMEOUT_SECONDS = 20
RG_MAX_BUFFER_BYTES = 20_000_000
PROJECT_INTERNAL_RUNTIME_ROOT = ".skill_runtime"
VCS_DIRECTORIES_TO_EXCLUDE = (".git", ".svn", ".hg", ".bzr", ".jj", ".sl")


@dataclass(frozen=True, slots=True)
class RipgrepResult:
    lines: list[str]
    duration_ms: int
    stderr: str = ""
    backend: str = "ripgrep"


class RipgrepUnavailableError(RuntimeError):
    pass


class RipgrepExecutionError(RuntimeError):
    def __init__(self, message: str, *, returncode: int | None = None, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


def run_ripgrep(args: list[str], *, target: str, cwd: Path) -> RipgrepResult:
    rg_path = which("rg")
    if not rg_path:
        return _run_python_search(args, target=target, cwd=cwd)

    command = [rg_path, "--no-config", *args, target]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    start = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RG_TIMEOUT_SECONDS,
            check=False,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired as exc:
        raise RipgrepExecutionError(
            f"ripgrep timed out after {RG_TIMEOUT_SECONDS} seconds",
            stderr=str(exc.stderr or ""),
        ) from exc

    duration_ms = int((time.perf_counter() - start) * 1000)
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if len(stdout.encode("utf-8", errors="replace")) > RG_MAX_BUFFER_BYTES:
        raise RipgrepExecutionError(
            f"ripgrep output exceeded {RG_MAX_BUFFER_BYTES} bytes; narrow the path, pattern, glob, or head_limit",
            returncode=completed.returncode,
            stderr=stderr,
        )
    if completed.returncode not in {0, 1}:
        message = (stderr or stdout or f"ripgrep exited with code {completed.returncode}").strip()
        raise RipgrepExecutionError(message, returncode=completed.returncode, stderr=stderr)
    return RipgrepResult(lines=stdout.splitlines(), duration_ms=duration_ms, stderr=stderr)


@dataclass(frozen=True, slots=True)
class _PythonSearchOptions:
    pattern: str | None = None
    files_mode: bool = False
    files_with_matches: bool = False
    count_mode: bool = False
    line_numbers: bool = False
    case_insensitive: bool = False
    multiline: bool = False
    before_context: int = 0
    after_context: int = 0
    type_filter: str | None = None
    include_globs: tuple[str, ...] = ()
    exclude_globs: tuple[str, ...] = ()


def _run_python_search(args: list[str], *, target: str, cwd: Path) -> RipgrepResult:
    start = time.perf_counter()
    resolved_cwd = cwd.resolve()
    options = _parse_python_search_options(args)
    if options.type_filter and not is_supported_ripgrep_type(options.type_filter):
        raise RipgrepExecutionError(
            f"Unsupported ripgrep type filter: {options.type_filter}. "
            "The `file_type` parameter filters files by language or extension; omit it for regex searches."
        )
    root = (cwd / target).resolve() if target != "." else resolved_cwd
    files = _iter_python_search_files(root=root, cwd=resolved_cwd, options=options)
    if options.files_mode:
        lines = [_relative_search_path(path, cwd=resolved_cwd) for path in files]
        return _python_fallback_result(lines, start=start)
    if not options.pattern:
        return _python_fallback_result([], start=start)
    try:
        flags = re.IGNORECASE if options.case_insensitive else 0
        if options.multiline:
            flags |= re.MULTILINE | re.DOTALL
        compiled = re.compile(options.pattern, flags)
    except re.error as exc:
        raise RipgrepExecutionError(f"invalid regex: {exc}") from exc

    if options.files_with_matches:
        lines = [
            _relative_search_path(path, cwd=resolved_cwd)
            for path in files
            if _file_has_match(path, compiled)
        ]
    elif options.count_mode:
        lines = []
        for path in files:
            count = _file_match_count(path, compiled)
            if count:
                lines.append(f"{_relative_search_path(path, cwd=resolved_cwd)}:{count}")
    else:
        lines = _python_content_lines(files, compiled, cwd=resolved_cwd, options=options)
    return _python_fallback_result(lines, start=start)


def _parse_python_search_options(args: list[str]) -> _PythonSearchOptions:
    pattern: str | None = None
    files_mode = False
    files_with_matches = False
    count_mode = False
    line_numbers = False
    case_insensitive = False
    multiline = False
    before_context = 0
    after_context = 0
    type_filter: str | None = None
    include_globs: list[str] = []
    exclude_globs: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--files":
            files_mode = True
        elif token == "-l":
            files_with_matches = True
        elif token == "-c":
            count_mode = True
        elif token == "-n":
            line_numbers = True
        elif token == "-i":
            case_insensitive = True
        elif token in {"-U", "--multiline-dotall"}:
            multiline = True
        elif token == "--glob" and index + 1 < len(args):
            glob = args[index + 1]
            if glob.startswith("!"):
                exclude_globs.append(glob[1:])
            else:
                include_globs.append(glob)
            index += 1
        elif token == "--type" and index + 1 < len(args):
            type_filter = args[index + 1]
            index += 1
        elif token == "-B" and index + 1 < len(args):
            before_context = _safe_int(args[index + 1])
            index += 1
        elif token == "-A" and index + 1 < len(args):
            after_context = _safe_int(args[index + 1])
            index += 1
        elif token == "-C" and index + 1 < len(args):
            before_context = after_context = _safe_int(args[index + 1])
            index += 1
        elif token == "-e" and index + 1 < len(args):
            pattern = args[index + 1]
            index += 1
        elif token in {"--max-columns"} and index + 1 < len(args):
            index += 1
        elif token.startswith("-"):
            pass
        elif pattern is None and not files_mode:
            pattern = token
        index += 1
    return _PythonSearchOptions(
        pattern=pattern,
        files_mode=files_mode,
        files_with_matches=files_with_matches,
        count_mode=count_mode,
        line_numbers=line_numbers,
        case_insensitive=case_insensitive,
        multiline=multiline,
        before_context=max(before_context, 0),
        after_context=max(after_context, 0),
        type_filter=type_filter,
        include_globs=tuple(include_globs),
        exclude_globs=tuple(exclude_globs),
    )


def _iter_python_search_files(
    *,
    root: Path,
    cwd: Path,
    options: _PythonSearchOptions,
) -> list[Path]:
    candidates = [root] if root.is_file() else list(_walk_python_search_files(root, cwd=cwd, options=options))
    files = [
        path.resolve()
        for path in candidates
        if _matches_python_search_filters(path.resolve(), cwd=cwd, options=options)
    ]
    files.sort(key=lambda path: path.as_posix())
    return files


def _walk_python_search_files(root: Path, *, cwd: Path, options: _PythonSearchOptions) -> list[Path]:
    candidates: list[Path] = []
    for current_root, dirnames, filenames in os.walk(root):
        current = Path(current_root)
        retained_dirs: list[str] = []
        for dirname in dirnames:
            directory = current / dirname
            rel = _relative_search_path(directory, cwd=cwd)
            if any(_glob_matches(rel, pattern) for pattern in options.exclude_globs):
                continue
            retained_dirs.append(dirname)
        dirnames[:] = retained_dirs
        candidates.extend(current / filename for filename in filenames)
    return candidates


def _matches_python_search_filters(path: Path, *, cwd: Path, options: _PythonSearchOptions) -> bool:
    rel = _relative_search_path(path, cwd=cwd)
    if any(_glob_matches(rel, pattern) for pattern in options.exclude_globs):
        return False
    if options.include_globs and not any(
        _glob_matches(rel, pattern) for pattern in options.include_globs
    ):
        return False
    if options.type_filter:
        extensions = ripgrep_type_extensions(options.type_filter)
        if extensions is None or path.suffix.lower() not in extensions:
            return False
    return True


def _glob_matches(rel_path: str, pattern: str) -> bool:
    normalized = str(pattern or "").replace("\\", "/").strip()
    if not normalized:
        return False
    if fnmatch.fnmatchcase(rel_path, normalized):
        return True
    if normalized.startswith("**/") and fnmatch.fnmatchcase(rel_path, normalized[3:]):
        return True
    if "/" not in normalized and fnmatch.fnmatchcase(Path(rel_path).name, normalized):
        return True
    if normalized.endswith("/**"):
        prefix = normalized[:-3].rstrip("/")
        return rel_path == prefix or rel_path.startswith(f"{prefix}/")
    return False


def ripgrep_type_extensions(type_name: str) -> set[str] | None:
    mapping = {
        "js": {".js", ".jsx", ".mjs", ".cjs"},
        "ts": {".ts", ".tsx", ".mts", ".cts"},
        "py": {".py", ".pyw"},
        "rust": {".rs"},
        "go": {".go"},
        "java": {".java"},
        "json": {".json"},
        "md": {".md", ".markdown"},
        "html": {".html", ".htm"},
        "css": {".css"},
    }
    return mapping.get(str(type_name or "").lower())


def is_supported_ripgrep_type(type_name: str | None) -> bool:
    if not str(type_name or "").strip():
        return True
    return ripgrep_type_extensions(str(type_name)) is not None


def _file_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _file_has_match(path: Path, pattern: re.Pattern[str]) -> bool:
    return bool(pattern.search(_file_text(path)))


def _file_match_count(path: Path, pattern: re.Pattern[str]) -> int:
    return len(pattern.findall(_file_text(path)))


def _python_content_lines(
    files: list[Path],
    pattern: re.Pattern[str],
    *,
    cwd: Path,
    options: _PythonSearchOptions,
) -> list[str]:
    lines: list[str] = []
    for path in files:
        text = _file_text(path)
        file_lines = text.splitlines()
        matched_indexes: set[int] = set()
        for index, line in enumerate(file_lines):
            if pattern.search(line):
                start = max(0, index - options.before_context)
                end = min(len(file_lines), index + options.after_context + 1)
                matched_indexes.update(range(start, end))
        for index in sorted(matched_indexes):
            rel = _relative_search_path(path, cwd=cwd)
            if options.line_numbers:
                lines.append(f"{rel}:{index + 1}:{file_lines[index]}")
            else:
                lines.append(f"{rel}:{file_lines[index]}")
    return lines


def _relative_search_path(path: Path, *, cwd: Path) -> str:
    try:
        return path.resolve().relative_to(cwd.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _safe_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _python_fallback_result(lines: list[str], *, start: float) -> RipgrepResult:
    return RipgrepResult(
        lines=lines,
        duration_ms=int((time.perf_counter() - start) * 1000),
        backend="python_fallback",
    )


def semantic_output_path(ctx: "HarnessContext", resolved: Path, *, location: str) -> str:
    return str(workspace_path_metadata(ctx, resolved, location=location).get("path") or resolved.as_posix())


def normalize_rg_output_path(raw_path: str, *, cwd: Path) -> Path:
    normalized = str(raw_path or "").strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    path = Path(normalized)
    if path.is_absolute():
        return path.resolve()
    return (cwd / normalized).resolve()


def project_internal_globs(location: str) -> list[str]:
    if location != "project":
        return []
    return [
        f"!{PROJECT_INTERNAL_RUNTIME_ROOT}",
        f"!{PROJECT_INTERNAL_RUNTIME_ROOT}/**",
    ]


def is_hidden_project_internal_path(ctx: "HarnessContext", path: Path, *, location: str) -> bool:
    if location != "project":
        return False
    try:
        rel = path.resolve().relative_to(ctx.project_dir.resolve()).as_posix()
    except ValueError:
        return False
    return rel == PROJECT_INTERNAL_RUNTIME_ROOT or rel.startswith(f"{PROJECT_INTERNAL_RUNTIME_ROOT}/")


def split_rg_glob_patterns(glob: str | None) -> list[str]:
    patterns: list[str] = []
    for raw_pattern in str(glob or "").split():
        if "{" in raw_pattern and "}" in raw_pattern:
            patterns.append(raw_pattern)
        else:
            patterns.extend(part for part in raw_pattern.split(",") if part)
    return [pattern for pattern in patterns if pattern]


def apply_head_limit[T](
    items: list[T],
    *,
    head_limit: int | None,
    offset: int = 0,
) -> tuple[list[T], int | None]:
    if head_limit == 0:
        return items[offset:], None
    effective_limit = 250 if head_limit is None else head_limit
    sliced = items[offset : offset + effective_limit]
    was_truncated = len(items) - offset > effective_limit
    return sliced, effective_limit if was_truncated else None
