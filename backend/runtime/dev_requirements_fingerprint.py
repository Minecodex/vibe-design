from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys

from runtime.incremental_pip_sync import read_requirement_specs


def compute_fingerprint(paths: list[str | Path]) -> str:
    digest = sha256()
    for requirement in read_requirement_specs(paths):
        digest.update(requirement.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise SystemExit("usage: python -m runtime.dev_requirements_fingerprint <path> [<path> ...]")
    print(compute_fingerprint(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
