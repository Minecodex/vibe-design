from __future__ import annotations

from importlib import metadata
import json
import sys
from typing import Iterable

from packaging.utils import canonicalize_name


def collect_installed_packages(
    distributions: Iterable[metadata.Distribution] | None = None,
) -> dict[str, str]:
    installed: dict[str, str] = {}
    for distribution in metadata.distributions() if distributions is None else distributions:
        name = distribution.metadata.get("Name")
        if not name:
            continue
        installed[canonicalize_name(name)] = distribution.version
    return dict(sorted(installed.items()))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        raise SystemExit("usage: python -m runtime.installed_python_packages")
    print(json.dumps(collect_installed_packages(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
