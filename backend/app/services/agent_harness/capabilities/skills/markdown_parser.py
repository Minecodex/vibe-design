from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml


@dataclass(slots=True)
class ParsedSkillMarkdown:
    meta: dict[str, Any]
    body: str
    frontmatter_status: str


def parse_skill_markdown(text: str) -> ParsedSkillMarkdown:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return ParsedSkillMarkdown(meta={}, body=text, frontmatter_status="missing")

    frontmatter = match.group(1)
    body = match.group(2)
    try:
        meta = yaml.safe_load(frontmatter) or {}
        status = "ok"
    except Exception:
        repaired_lines: list[str] = []
        for line in frontmatter.splitlines():
            key_match = re.match(r"^(\s*[\w-]+\s*:\s*)(.+)$", line)
            if not key_match:
                repaired_lines.append(line)
                continue
            prefix, raw_value = key_match.groups()
            stripped = raw_value.strip()
            if (
                ": " in stripped
                and not stripped.startswith(("'", '"', "[", "{", "|", ">"))
                and not stripped.startswith(("-", "?"))
            ):
                escaped = stripped.replace("\\", "\\\\").replace('"', '\\"')
                repaired_lines.append(f'{prefix}"{escaped}"')
                continue
            repaired_lines.append(line)
        try:
            meta = yaml.safe_load("\n".join(repaired_lines)) or {}
            status = "repaired"
        except Exception:
            meta = {}
            status = "failed"
    return ParsedSkillMarkdown(meta=meta, body=body, frontmatter_status=status)
