from __future__ import annotations

import shlex
from dataclasses import dataclass

from .types import AnalyzedCommand

MAX_SUBCOMMANDS_FOR_SECURITY_CHECK = 50


@dataclass(frozen=True, slots=True)
class SplitResult:
    commands: tuple[AnalyzedCommand, ...] = ()
    error: str | None = None
    too_complex: bool = False


def split_shell_commands(command: str) -> SplitResult:
    segments: list[AnalyzedCommand] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    operator_before: str | None = None
    index = 0
    i = 0

    while i < len(command):
        ch = command[i]
        if escaped:
            current.append(ch)
            escaped = False
            i += 1
            continue
        if ch == "\\":
            current.append(ch)
            escaped = True
            i += 1
            continue
        if quote is not None:
            current.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in {"'", '"'}:
            current.append(ch)
            quote = ch
            i += 1
            continue

        op = _operator_at(command, i)
        if op is not None:
            text = "".join(current).strip()
            if text:
                segments.append(AnalyzedCommand(text=text, index=index, operator_before=operator_before))
                index += 1
                if len(segments) > MAX_SUBCOMMANDS_FOR_SECURITY_CHECK:
                    return SplitResult(commands=tuple(segments), too_complex=True)
            current = []
            operator_before = op
            i += len(op)
            continue

        current.append(ch)
        i += 1

    if escaped:
        return SplitResult(error="Command ends with an unfinished escape sequence")
    if quote is not None:
        return SplitResult(error="Command has an unclosed quote")

    text = "".join(current).strip()
    if text:
        segments.append(AnalyzedCommand(text=text, index=index, operator_before=operator_before))
    if len(segments) > MAX_SUBCOMMANDS_FOR_SECURITY_CHECK:
        return SplitResult(commands=tuple(segments), too_complex=True)
    return SplitResult(commands=tuple(segments))


def shell_tokens(command: str) -> tuple[str, ...]:
    return tuple(shlex.split(command, posix=True))


def _operator_at(command: str, index: int) -> str | None:
    pair = command[index : index + 2]
    if pair in {"&&", "||"}:
        return pair
    ch = command[index]
    if ch in {";", "|"}:
        return ch
    return None
