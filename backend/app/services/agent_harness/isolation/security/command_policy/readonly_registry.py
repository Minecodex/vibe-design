from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .splitter import shell_tokens
from .types import CommandRiskTag

FlagArgType = Literal["none", "string", "number", "char", "literal:{}"]


@dataclass(frozen=True, slots=True)
class ReadOnlyCommandRule:
    safe_flags: dict[str, FlagArgType] = field(default_factory=dict)
    dangerous_flags: dict[str, str] = field(default_factory=dict)
    respects_double_dash: bool = True


_WRITE_FLAG = CommandRiskTag.READONLY_FLAG_WRITES.value
_EXEC_FLAG = CommandRiskTag.READONLY_FLAG_EXECUTES_COMMANDS.value
_REVIEW_FLAG = CommandRiskTag.READONLY_FLAG_REQUIRES_REVIEW.value

_COMMON_GIT_FLAGS: dict[str, FlagArgType] = {
    "--color": "string",
    "--no-color": "none",
    "--stat": "none",
    "--numstat": "none",
    "--shortstat": "none",
    "--name-only": "none",
    "--name-status": "none",
    "-n": "number",
    "--max-count": "number",
}

_REGISTRY: dict[tuple[str, ...], ReadOnlyCommandRule] = {
    ("git", "diff"): ReadOnlyCommandRule(
        safe_flags={
            **_COMMON_GIT_FLAGS,
            "--cached": "none",
            "--staged": "none",
            "--check": "none",
            "--exit-code": "none",
            "--no-index": "none",
            "--no-ext-diff": "none",
            "--oneline": "none",
            "--dirstat": "none",
            "--summary": "none",
            "--patch-with-stat": "none",
            "--word-diff": "string",
            "--word-diff-regex": "string",
            "--color-words": "string",
            "--no-renames": "none",
            "--find-renames": "none",
            "--find-copies": "none",
            "--find-copies-harder": "none",
            "--diff-algorithm": "string",
            "--histogram": "none",
            "--patience": "none",
            "--minimal": "none",
            "--ignore-space-at-eol": "none",
            "--ignore-space-change": "none",
            "--ignore-all-space": "none",
            "--ignore-blank-lines": "none",
            "--inter-hunk-context": "number",
            "--function-context": "none",
            "--relative": "string",
            "--diff-filter": "string",
            "-p": "none",
            "-u": "none",
            "-s": "none",
            "-M": "none",
            "-C": "none",
            "-B": "none",
            "-D": "none",
            "-S": "string",
            "-G": "string",
        },
        dangerous_flags={"--output": _WRITE_FLAG, "--ext-diff": _REVIEW_FLAG},
    ),
    ("git", "log"): ReadOnlyCommandRule(
        safe_flags={
            **_COMMON_GIT_FLAGS,
            "--oneline": "none",
            "--graph": "none",
            "--decorate": "none",
            "--no-decorate": "none",
            "--author": "string",
            "--committer": "string",
            "--grep": "string",
            "--all": "none",
            "--branches": "none",
            "--tags": "none",
            "--remotes": "none",
            "--since": "string",
            "--after": "string",
            "--until": "string",
            "--before": "string",
            "--date": "string",
            "--relative-date": "none",
            "--format": "string",
            "--pretty": "string",
            "--patch": "none",
            "--no-patch": "none",
            "--no-ext-diff": "none",
            "-p": "none",
            "-s": "none",
        },
        dangerous_flags={"--output": _WRITE_FLAG, "--ext-diff": _REVIEW_FLAG},
    ),
    ("git", "show"): ReadOnlyCommandRule(
        safe_flags={
            **_COMMON_GIT_FLAGS,
            "--format": "string",
            "--pretty": "string",
            "--patch": "none",
            "--no-patch": "none",
            "--no-ext-diff": "none",
            "--relative": "string",
            "-p": "none",
            "-s": "none",
        },
        dangerous_flags={"--output": _WRITE_FLAG, "--ext-diff": _REVIEW_FLAG},
    ),
    ("git", "shortlog"): ReadOnlyCommandRule(
        safe_flags={**_COMMON_GIT_FLAGS, "-s": "none", "-n": "none", "-e": "none", "--summary": "none", "--numbered": "none"},
    ),
    ("git", "reflog"): ReadOnlyCommandRule(
        safe_flags={**_COMMON_GIT_FLAGS, "--date": "string", "--format": "string", "--all": "none"},
    ),
    ("git", "stash"): ReadOnlyCommandRule(
        safe_flags={"--stat": "none", "-p": "none", "--patch": "none"},
    ),
    ("git", "ls-remote"): ReadOnlyCommandRule(
        safe_flags={"--heads": "none", "--tags": "none", "--refs": "none", "--symref": "none", "--quiet": "none", "-q": "none"},
    ),
    ("git", "status"): ReadOnlyCommandRule(
        safe_flags={"--short": "none", "-s": "none", "--branch": "none", "-b": "none", "--porcelain": "string", "--ignored": "none", "--untracked-files": "string"},
    ),
    ("git", "blame"): ReadOnlyCommandRule(
        safe_flags={"-L": "string", "--line-porcelain": "none", "--porcelain": "none", "--show-name": "none", "-w": "none"},
    ),
    ("git", "ls-files"): ReadOnlyCommandRule(
        safe_flags={"--cached": "none", "--deleted": "none", "--modified": "none", "--others": "none", "--ignored": "none", "--exclude-standard": "none", "-z": "none"},
    ),
    ("git", "config"): ReadOnlyCommandRule(
        safe_flags={"--get": "none", "--get-all": "none", "--list": "none", "-l": "none", "--name-only": "none", "--show-origin": "none"},
        dangerous_flags={"--global": _REVIEW_FLAG, "--system": _REVIEW_FLAG, "--file": _REVIEW_FLAG},
    ),
    ("git", "remote"): ReadOnlyCommandRule(
        safe_flags={"-v": "none", "--verbose": "none", "show": "string"},
    ),
    ("git", "merge-base"): ReadOnlyCommandRule(
        safe_flags={"--all": "none", "--is-ancestor": "none", "--fork-point": "none"},
    ),
    ("git", "rev-parse"): ReadOnlyCommandRule(
        safe_flags={"--show-toplevel": "none", "--git-dir": "none", "--is-inside-work-tree": "none", "--abbrev-ref": "string", "--verify": "none", "--short": "string"},
    ),
    ("git", "rev-list"): ReadOnlyCommandRule(
        safe_flags={**_COMMON_GIT_FLAGS, "--all": "none", "--count": "none", "--objects": "none", "--parents": "none"},
    ),
    ("git", "describe"): ReadOnlyCommandRule(
        safe_flags={"--tags": "none", "--always": "none", "--dirty": "string", "--abbrev": "number", "--contains": "none", "--all": "none"},
    ),
    ("git", "cat-file"): ReadOnlyCommandRule(
        safe_flags={"-p": "none", "-t": "none", "-s": "none", "--batch": "none", "--batch-check": "none"},
    ),
    ("git", "for-each-ref"): ReadOnlyCommandRule(
        safe_flags={"--format": "string", "--sort": "string", "--count": "number", "--merged": "string", "--contains": "string"},
    ),
    ("git", "grep"): ReadOnlyCommandRule(
        safe_flags={"-n": "none", "-i": "none", "-E": "none", "-F": "none", "-e": "string", "--line-number": "none", "--ignore-case": "none", "--cached": "none", "--untracked": "none"},
    ),
    ("git", "worktree"): ReadOnlyCommandRule(safe_flags={"list": "none", "--porcelain": "none"}),
    ("git", "tag"): ReadOnlyCommandRule(
        safe_flags={"-l": "none", "--list": "none", "-n": "number", "--contains": "string", "--merged": "string", "--sort": "string", "--format": "string"},
    ),
    ("git", "branch"): ReadOnlyCommandRule(
        safe_flags={"-a": "none", "-r": "none", "-v": "none", "-vv": "none", "--all": "none", "--remotes": "none", "--list": "none", "--contains": "string", "--merged": "string", "--sort": "string", "--format": "string"},
    ),
    ("ls",): ReadOnlyCommandRule(
        safe_flags={"-l": "none", "-a": "none", "-h": "none", "-R": "none", "-t": "none", "-r": "none", "-S": "none", "-1": "none", "--all": "none", "--long": "none", "--human-readable": "none"},
    ),
    ("cat",): ReadOnlyCommandRule(safe_flags={"-n": "none", "-b": "none", "-s": "none", "-A": "none"}),
    ("head",): ReadOnlyCommandRule(safe_flags={"-n": "number", "-c": "number", "-q": "none", "-v": "none", "--lines": "number", "--bytes": "number"}),
    ("tail",): ReadOnlyCommandRule(safe_flags={"-n": "number", "-c": "number", "-f": "none", "-q": "none", "-v": "none", "--lines": "number", "--bytes": "number"}),
    ("wc",): ReadOnlyCommandRule(safe_flags={"-l": "none", "-w": "none", "-c": "none", "-m": "none", "-L": "none", "--lines": "none", "--words": "none", "--bytes": "none"}),
    ("stat",): ReadOnlyCommandRule(safe_flags={"-c": "string", "-f": "none", "-L": "none", "--format": "string", "--file-system": "none"}),
    ("du",): ReadOnlyCommandRule(safe_flags={"-s": "none", "-h": "none", "-a": "none", "-c": "none", "-d": "number", "--summarize": "none", "--human-readable": "none", "--max-depth": "number"}),
    ("file",): ReadOnlyCommandRule(safe_flags={"-b": "none", "-i": "none", "-L": "none", "-z": "none", "--brief": "none", "--mime": "none", "--dereference": "none"}),
    ("grep",): ReadOnlyCommandRule(
        safe_flags={"-R": "none", "-r": "none", "-n": "none", "-i": "none", "-E": "none", "-F": "none", "-e": "string", "-f": "string", "-A": "number", "-B": "number", "-C": "number", "--include": "string", "--exclude": "string", "--exclude-from": "string", "--exclude-dir": "string", "--regexp": "string", "--file": "string", "--recursive": "none", "--line-number": "none"},
    ),
    ("rg",): ReadOnlyCommandRule(
        safe_flags={
            "--hidden": "none",
            "--no-ignore": "none",
            "--glob": "string",
            "-g": "string",
            "--iglob": "string",
            "--type": "string",
            "-t": "string",
            "--type-not": "string",
            "-T": "string",
            "--files": "none",
            "--json": "none",
            "--line-number": "none",
            "-n": "none",
            "--context": "number",
            "-C": "number",
            "--before-context": "number",
            "-B": "number",
            "--after-context": "number",
            "-A": "number",
            "--max-count": "number",
            "-m": "number",
            "--ignore-case": "none",
            "-i": "none",
            "--fixed-strings": "none",
            "-F": "none",
            "--regexp": "string",
            "-e": "string",
            "--file": "string",
            "-f": "string",
            "--ignore-file": "string",
            "--max-filesize": "string",
            "--max-depth": "number",
            "--threads": "number",
            "-j": "number",
            "--sort": "string",
            "--sortr": "string",
            "--count": "none",
            "-c": "none",
            "--files-with-matches": "none",
            "-l": "none",
            "--files-without-match": "none",
            "--no-messages": "none",
        },
        dangerous_flags={"--pre": _EXEC_FLAG, "--pre-glob": _EXEC_FLAG},
    ),
    ("find",): ReadOnlyCommandRule(
        safe_flags={
            "-maxdepth": "number",
            "-mindepth": "number",
            "-name": "string",
            "-iname": "string",
            "-path": "string",
            "-type": "string",
            "-size": "string",
            "-mtime": "string",
            "-print": "none",
            "-print0": "none",
            "-ls": "none",
        },
        dangerous_flags={
            "-delete": _WRITE_FLAG,
            "-exec": _EXEC_FLAG,
            "-execdir": _EXEC_FLAG,
            "-ok": _EXEC_FLAG,
            "-okdir": _EXEC_FLAG,
            "-fprint": _WRITE_FLAG,
            "-fprintf": _WRITE_FLAG,
            "-fls": _WRITE_FLAG,
        },
    ),
    ("fd",): ReadOnlyCommandRule(
        safe_flags={
            "-h": "none",
            "--help": "none",
            "-V": "none",
            "--version": "none",
            "-H": "none",
            "--hidden": "none",
            "-I": "none",
            "--no-ignore": "none",
            "--no-ignore-vcs": "none",
            "-s": "none",
            "--case-sensitive": "none",
            "-i": "none",
            "--ignore-case": "none",
            "-g": "none",
            "--glob": "none",
            "--regex": "none",
            "-F": "none",
            "--fixed-strings": "none",
            "-a": "none",
            "--absolute-path": "none",
            "-L": "none",
            "--follow": "none",
            "-p": "none",
            "--full-path": "none",
            "-0": "none",
            "--print0": "none",
            "-d": "number",
            "--max-depth": "number",
            "--min-depth": "number",
            "--exact-depth": "number",
            "-t": "string",
            "--type": "string",
            "-e": "string",
            "--extension": "string",
            "-S": "string",
            "--size": "string",
            "--changed-within": "string",
            "--changed-before": "string",
            "-E": "string",
            "--exclude": "string",
            "--ignore-file": "string",
            "-o": "string",
            "--owner": "string",
            "-c": "string",
            "--color": "string",
            "-j": "number",
            "--threads": "number",
            "--max-results": "number",
            "-1": "none",
            "-q": "none",
            "--quiet": "none",
            "--strip-cwd-prefix": "none",
            "--one-file-system": "none",
            "--prune": "none",
            "--search-path": "string",
            "--base-directory": "string",
        },
        dangerous_flags={"-x": _EXEC_FLAG, "--exec": _EXEC_FLAG, "-X": _EXEC_FLAG, "--exec-batch": _EXEC_FLAG, "--list-details": _EXEC_FLAG},
    ),
    ("fdfind",): ReadOnlyCommandRule(
        safe_flags={
            "-h": "none",
            "--help": "none",
            "-V": "none",
            "--version": "none",
            "-H": "none",
            "--hidden": "none",
            "-I": "none",
            "--no-ignore": "none",
            "--no-ignore-vcs": "none",
            "-s": "none",
            "--case-sensitive": "none",
            "-i": "none",
            "--ignore-case": "none",
            "-g": "none",
            "--glob": "none",
            "--regex": "none",
            "-F": "none",
            "--fixed-strings": "none",
            "-a": "none",
            "--absolute-path": "none",
            "-L": "none",
            "--follow": "none",
            "-p": "none",
            "--full-path": "none",
            "-0": "none",
            "--print0": "none",
            "-d": "number",
            "--max-depth": "number",
            "--min-depth": "number",
            "--exact-depth": "number",
            "-t": "string",
            "--type": "string",
            "-e": "string",
            "--extension": "string",
            "-S": "string",
            "--size": "string",
            "--changed-within": "string",
            "--changed-before": "string",
            "-E": "string",
            "--exclude": "string",
            "--ignore-file": "string",
            "-o": "string",
            "--owner": "string",
            "-c": "string",
            "--color": "string",
            "-j": "number",
            "--threads": "number",
            "--max-results": "number",
            "-1": "none",
            "-q": "none",
            "--quiet": "none",
            "--strip-cwd-prefix": "none",
            "--one-file-system": "none",
            "--prune": "none",
            "--search-path": "string",
            "--base-directory": "string",
        },
        dangerous_flags={"-x": _EXEC_FLAG, "--exec": _EXEC_FLAG, "-X": _EXEC_FLAG, "--exec-batch": _EXEC_FLAG, "--list-details": _EXEC_FLAG},
    ),
    ("strings",): ReadOnlyCommandRule(safe_flags={"-a": "none", "-n": "number", "-t": "string"}),
    ("hexdump",): ReadOnlyCommandRule(safe_flags={"-C": "none", "-n": "number", "-s": "string", "-v": "none"}),
    ("od",): ReadOnlyCommandRule(safe_flags={"-A": "string", "-t": "string", "-N": "number", "-j": "string", "-v": "none"}),
    ("base64",): ReadOnlyCommandRule(safe_flags={"-d": "none", "--decode": "none", "-w": "number", "--wrap": "number"}),
    ("nl",): ReadOnlyCommandRule(safe_flags={"-b": "string", "-n": "string", "-w": "number", "-s": "string"}),
    ("sha256sum",): ReadOnlyCommandRule(safe_flags={"-b": "none", "-t": "none", "--binary": "none", "--text": "none"}),
    ("sha1sum",): ReadOnlyCommandRule(safe_flags={"-b": "none", "-t": "none", "--binary": "none", "--text": "none"}),
    ("md5sum",): ReadOnlyCommandRule(safe_flags={"-b": "none", "-t": "none", "--binary": "none", "--text": "none"}),
    ("diff",): ReadOnlyCommandRule(safe_flags={"-u": "none", "-r": "none", "-q": "none", "-N": "none", "--unified": "string", "--recursive": "none", "--brief": "none", "--label": "string"}),
    ("cut",): ReadOnlyCommandRule(safe_flags={"-d": "char", "-f": "string", "-c": "string", "-b": "string", "--delimiter": "char", "--fields": "string", "--characters": "string"}),
    ("paste",): ReadOnlyCommandRule(safe_flags={"-d": "string", "-s": "none", "--delimiters": "string", "--serial": "none"}),
    ("column",): ReadOnlyCommandRule(safe_flags={"-t": "none", "-s": "string", "-o": "string", "-N": "string"}),
    ("uniq",): ReadOnlyCommandRule(safe_flags={"-c": "none", "-d": "none", "-u": "none", "-i": "none", "--count": "none", "--repeated": "none", "--unique": "none"}),
    ("tr",): ReadOnlyCommandRule(safe_flags={"-d": "none", "-s": "none", "-c": "none", "--delete": "none", "--squeeze-repeats": "none"}),
    ("sort",): ReadOnlyCommandRule(
        safe_flags={
            "-n": "none",
            "-r": "none",
            "-u": "none",
            "-f": "none",
            "-k": "string",
            "-t": "string",
            "--numeric-sort": "none",
            "--reverse": "none",
            "--unique": "none",
            "--field-separator": "string",
            "--key": "string",
        },
        dangerous_flags={"-o": _WRITE_FLAG, "--output": _WRITE_FLAG},
    ),
    ("tar",): ReadOnlyCommandRule(
        safe_flags={"-t": "none", "--list": "none", "-f": "string", "--file": "string"},
        dangerous_flags={
            "-x": _WRITE_FLAG,
            "--extract": _WRITE_FLAG,
            "--get": _WRITE_FLAG,
        },
    ),
    ("docker", "ps"): ReadOnlyCommandRule(safe_flags={"-a": "none", "--all": "none", "--format": "string", "-q": "none", "--quiet": "none"}),
    ("docker", "images"): ReadOnlyCommandRule(safe_flags={"-a": "none", "--all": "none", "--format": "string", "-q": "none", "--quiet": "none"}),
    ("docker", "container"): ReadOnlyCommandRule(
        safe_flags={"ls": "none", "list": "none", "-a": "none", "--all": "none", "--format": "string", "-q": "none", "--quiet": "none"},
        dangerous_flags={"run": _EXEC_FLAG, "exec": _EXEC_FLAG, "start": _EXEC_FLAG, "stop": _WRITE_FLAG, "kill": _WRITE_FLAG, "rm": _WRITE_FLAG, "prune": _WRITE_FLAG, "create": _EXEC_FLAG, "cp": _WRITE_FLAG},
    ),
    ("docker", "image"): ReadOnlyCommandRule(
        safe_flags={"ls": "none", "list": "none", "-a": "none", "--all": "none", "--format": "string", "-q": "none", "--quiet": "none"},
        dangerous_flags={"build": _EXEC_FLAG, "pull": CommandRiskTag.READONLY_FLAG_NETWORK.value, "push": CommandRiskTag.READONLY_FLAG_NETWORK.value, "rm": _WRITE_FLAG, "prune": _WRITE_FLAG, "tag": _WRITE_FLAG, "save": _WRITE_FLAG, "load": _WRITE_FLAG},
    ),
    ("docker", "inspect"): ReadOnlyCommandRule(safe_flags={"--format": "string", "-f": "string", "--size": "none"}),
    ("docker", "logs"): ReadOnlyCommandRule(safe_flags={"--tail": "number", "-n": "number", "--since": "string", "--until": "string", "--timestamps": "none", "--follow": "none", "-f": "none"}),
    ("pyright",): ReadOnlyCommandRule(
        safe_flags={"--project": "string", "-p": "string", "--level": "string", "--warnings": "none", "--outputjson": "none", "--stats": "none", "--verbose": "none", "--pythonversion": "string", "--pythonplatform": "string", "--dependencies": "none"},
        dangerous_flags={"--createstub": _WRITE_FLAG, "--verifytypes": CommandRiskTag.READONLY_FLAG_NETWORK.value},
    ),
    ("xargs",): ReadOnlyCommandRule(
        safe_flags={"-0": "none", "-a": "string", "-I": "string", "-n": "number", "-L": "number", "-P": "number", "-r": "none"},
        dangerous_flags={"-i": _EXEC_FLAG, "-e": _EXEC_FLAG, "sh": _EXEC_FLAG, "bash": _EXEC_FLAG, "zsh": _EXEC_FLAG, "python": _EXEC_FLAG, "python3": _EXEC_FLAG, "node": _EXEC_FLAG},
    ),
}


def readonly_risk(command: str) -> tuple[str, str, str] | tuple[str, str, str, str] | None:
    try:
        tokens = list(shell_tokens(command))
    except ValueError:
        return None
    matched = _match_rule(tokens)
    if matched is None:
        if tokens and tokens[0].lower() == "gh":
            return (
                "GitHub CLI commands use the network and require an explicit project policy.",
                "dangerous_command",
                CommandRiskTag.READONLY_FLAG_NETWORK.value,
            )
        if tokens and tokens[0].lower() == "docker":
            return (
                "Docker commands other than read-only inspection commands are blocked.",
                "dangerous_command",
                CommandRiskTag.READONLY_FLAG_EXECUTES_COMMANDS.value,
            )
        return None
    prefix_len, rule = matched
    return _validate_args(tokens[prefix_len:], rule)


def _match_rule(tokens: list[str]) -> tuple[int, ReadOnlyCommandRule] | None:
    lowered = [token.lower() for token in tokens]
    for key_len in (2, 1):
        key = tuple(lowered[:key_len])
        rule = _REGISTRY.get(key)
        if rule is not None:
            return key_len, rule
    return None


def _validate_args(
    args: list[str],
    rule: ReadOnlyCommandRule,
) -> tuple[str, str, str] | tuple[str, str, str, str] | None:
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--" and rule.respects_double_dash:
            return None
        if not arg.startswith("-") or arg == "-":
            arg_lower = arg.lower()
            dangerous = rule.dangerous_flags.get(arg_lower)
            if dangerous is None:
                dangerous = rule.dangerous_flags.get(arg_lower.rsplit("/", 1)[-1])
            if dangerous is not None:
                return _dangerous_result(arg, dangerous)
            index += 1
            continue
        flag, inline_value = _split_long_value(arg)
        dangerous = _dangerous_flag_risk(flag, rule)
        if dangerous is not None:
            return _dangerous_result(flag, dangerous)
        safe_type = rule.safe_flags.get(flag)
        if safe_type is None and _is_short_bundle(flag):
            bundle_result = _validate_short_bundle(flag, args, index, rule)
            if bundle_result is not None:
                consumed, risk = bundle_result
                if risk is not None:
                    return risk
                index += consumed
                continue
        if safe_type is None:
            return _ask_result(f"Flag {flag} requires review before treating command as read-only.")
        if safe_type == "literal:{}" and inline_value is not None and inline_value != "{}":
            return _ask_result(f"Flag {flag} requires literal {{}}.")
        if safe_type != "none" and inline_value is None:
            if index + 1 >= len(args):
                return _ask_result(f"Flag {flag} requires a value.")
            if safe_type == "literal:{}" and args[index + 1] != "{}":
                return _ask_result(f"Flag {flag} requires literal {{}}.")
            if safe_type == "number" and not args[index + 1].lstrip("-").isdigit():
                return _ask_result(f"Flag {flag} requires a numeric value.")
            if safe_type == "char" and len(args[index + 1]) != 1:
                return _ask_result(f"Flag {flag} requires a single-character value.")
            index += 2
            continue
        if safe_type == "number" and inline_value is not None and not inline_value.isdigit():
            return _ask_result(f"Flag {flag} requires a numeric value.")
        if safe_type == "char" and inline_value is not None and len(inline_value) != 1:
            return _ask_result(f"Flag {flag} requires a single-character value.")
        index += 1
    return None


def _split_long_value(arg: str) -> tuple[str, str | None]:
    if arg.startswith("--") and "=" in arg:
        flag, value = arg.split("=", 1)
        return flag, value
    return arg, None


def _dangerous_flag_risk(flag: str, rule: ReadOnlyCommandRule) -> str | None:
    if flag in rule.dangerous_flags:
        return rule.dangerous_flags[flag]
    if flag.startswith("--") and "=" in flag:
        return rule.dangerous_flags.get(flag.split("=", 1)[0])
    if _is_short_bundle(flag):
        for char in flag[1:]:
            risk = rule.dangerous_flags.get(f"-{char}")
            if risk is not None:
                return risk
    return None


def _dangerous_result(flag: str, risk_tag: str) -> tuple[str, str, str] | tuple[str, str, str, str]:
    if risk_tag == _REVIEW_FLAG:
        return (
            f"Flag {flag} requires review before treating command as read-only.",
            "command_requires_review",
            risk_tag,
            "ask",
        )
    return (
        f"Flag {flag} is not read-only and is blocked.",
        "dangerous_command",
        risk_tag,
    )


def _ask_result(message: str) -> tuple[str, str, str, str]:
    return (message, "command_requires_review", _REVIEW_FLAG, "ask")


def _is_short_bundle(flag: str) -> bool:
    return flag.startswith("-") and not flag.startswith("--") and len(flag) > 2


def _validate_short_bundle(
    flag: str,
    args: list[str],
    index: int,
    rule: ReadOnlyCommandRule,
) -> tuple[int, tuple[str, str, str] | tuple[str, str, str, str] | None] | None:
    for offset, char in enumerate(flag[1:], start=1):
        short = f"-{char}"
        dangerous = rule.dangerous_flags.get(short)
        if dangerous is not None:
            return 1, _dangerous_result(short, dangerous)
        safe_type = rule.safe_flags.get(short)
        if safe_type is None:
            return 1, _ask_result(f"Flag {short} requires review before treating command as read-only.")
        if safe_type == "none":
            continue
        attached = flag[offset + 1 :]
        if attached:
            if safe_type == "number" and not attached.isdigit():
                return 1, _ask_result(f"Flag {short} requires a numeric value.")
            return 1, None
        if index + 1 >= len(args):
            return 1, _ask_result(f"Flag {short} requires a value.")
        if safe_type == "number" and not args[index + 1].lstrip("-").isdigit():
            return 1, _ask_result(f"Flag {short} requires a numeric value.")
        return 2, None
    return 1, None
