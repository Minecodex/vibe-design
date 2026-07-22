from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Iterable

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from runtime.installed_python_packages import collect_installed_packages


@dataclass(frozen=True)
class RequirementSpec:
    raw: str
    requirement: Requirement


@dataclass(frozen=True)
class RequirementIdentity:
    name: str
    extras: tuple[str, ...]
    specifier: str
    marker: str | None
    url: str | None


def _strip_inline_comment(line: str) -> str:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return ""

    in_quote: str | None = None
    for index, char in enumerate(line):
        if char in {"'", '"'}:
            if in_quote == char:
                in_quote = None
            elif in_quote is None:
                in_quote = char
            continue
        if char == "#" and in_quote is None and (index == 0 or line[index - 1].isspace()):
            return line[:index].strip()
    return stripped


def _unquote_token(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
        return token[1:-1]
    return token


def _parse_include_target(line: str) -> str | None:
    for prefix in ("-r", "--requirement"):
        if line == prefix:
            raise ValueError(f"invalid include directive: {line}")
        if line.startswith(f"{prefix} "):
            target = line[len(prefix):].strip()
            if not target:
                raise ValueError(f"invalid include directive: {line}")
            return _unquote_token(target)
    if line.startswith("--requirement="):
        target = line.partition("=")[2].strip()
        if not target:
            raise ValueError(f"invalid include directive: {line}")
        return _unquote_token(target)
    if line.startswith("-r") and line != "-r":
        target = line[2:].strip()
        if not target:
            raise ValueError(f"invalid include directive: {line}")
        return _unquote_token(target)
    if line.startswith("--requirement") and line != "--requirement":
        remainder = line[len("--requirement"):].strip()
        if remainder:
            return _unquote_token(remainder)
    return None


def _resolve_include_path(parent: Path, include_target: str) -> Path:
    normalized_target = include_target.replace("\\", "/")
    return parent / normalized_target


def _iter_requirement_specs(
    path: Path,
    *,
    visited: set[Path],
    active: set[Path],
) -> list[RequirementSpec]:
    resolved_path = path.resolve()
    if resolved_path in active:
        raise ValueError(f"cyclic requirement include detected at {resolved_path}")
    if resolved_path in visited:
        return []

    active.add(resolved_path)
    try:
        requirements: list[RequirementSpec] = []
        for line_number, raw_line in enumerate(resolved_path.read_text(encoding="utf-8").splitlines(), start=1):
            line = _strip_inline_comment(raw_line)
            if not line:
                continue

            include_target = _parse_include_target(line)
            if include_target is not None:
                requirements.extend(
                    _iter_requirement_specs(
                        _resolve_include_path(resolved_path.parent, include_target),
                        visited=visited,
                        active=active,
                    )
                )
                continue

            try:
                requirement = Requirement(line)
            except Exception as exc:  # pragma: no cover - defensive parse context
                raise ValueError(
                    f"invalid requirement in {resolved_path} at line {line_number}: {line}"
                ) from exc
            requirements.append(RequirementSpec(raw=line, requirement=requirement))

        visited.add(resolved_path)
        return requirements
    finally:
        active.remove(resolved_path)


def read_requirement_entries(paths: Iterable[str | Path]) -> list[RequirementSpec]:
    visited: set[Path] = set()
    active: set[Path] = set()
    requirements: list[RequirementSpec] = []
    for raw_path in paths:
        requirements.extend(
            _iter_requirement_specs(
                Path(raw_path),
                visited=visited,
                active=active,
            )
        )
    return requirements


def read_requirement_specs(paths: Iterable[str | Path]) -> list[str]:
    return [entry.raw for entry in read_requirement_entries(paths)]


def _requirement_identity(requirement: Requirement) -> RequirementIdentity:
    return RequirementIdentity(
        name=canonicalize_name(requirement.name),
        extras=tuple(sorted(requirement.extras)),
        specifier=str(requirement.specifier),
        marker=str(requirement.marker) if requirement.marker is not None else None,
        url=requirement.url,
    )


def _deduplicate_requirement_entries(entries: Iterable[RequirementSpec]) -> list[RequirementSpec]:
    deduplicated: list[RequirementSpec] = []
    seen: dict[str, RequirementIdentity] = {}
    for entry in entries:
        identity = _requirement_identity(entry.requirement)
        existing = seen.get(identity.name)
        if existing is None:
            seen[identity.name] = identity
            deduplicated.append(entry)
            continue
        if existing != identity:
            raise ValueError(f"conflicting requirement declarations for {identity.name}")
    return deduplicated


def _is_requirement_satisfied(requirement: Requirement, installed_packages: dict[str, str]) -> bool:
    if requirement.marker is not None and not requirement.marker.evaluate():
        return True
    if requirement.extras:
        # A name->version inventory cannot prove extras were installed.
        return False

    installed_version = installed_packages.get(canonicalize_name(requirement.name))
    if installed_version is None:
        return False
    if not requirement.specifier:
        return True
    return requirement.specifier.contains(installed_version, prereleases=True)


def requirements_to_install(
    paths: Iterable[str | Path],
    *,
    installed_packages: dict[str, str] | None = None,
) -> list[str]:
    installed = collect_installed_packages() if installed_packages is None else {
        canonicalize_name(name): version for name, version in installed_packages.items()
    }

    pending: list[str] = []
    for entry in _deduplicate_requirement_entries(read_requirement_entries(paths)):
        if _is_requirement_satisfied(entry.requirement, installed):
            continue
        pending.append(entry.raw)
    return pending


def _parse_installed_packages_json(raw_json: str) -> dict[str, str]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ValueError("must decode to a JSON object")
    invalid_entries = [
        key for key, value in payload.items()
        if not isinstance(key, str) or not isinstance(value, str)
    ]
    if invalid_entries:
        raise ValueError("must map package names to version strings")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(prog="python -m runtime.incremental_pip_sync")
    parser.add_argument("paths", nargs="+", help="Requirement files to evaluate")
    parser.add_argument(
        "--installed-json",
        help="JSON object containing normalized package-name -> version inventory",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    installed_packages = None
    if args.installed_json:
        try:
            installed_packages = _parse_installed_packages_json(args.installed_json)
        except ValueError as exc:
            raise SystemExit(f"invalid --installed-json: {exc}") from exc

    pending = requirements_to_install(args.paths, installed_packages=installed_packages)
    if pending:
        print("\n".join(pending))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
