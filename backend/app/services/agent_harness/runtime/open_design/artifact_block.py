from __future__ import annotations

import html
import re
from html.parser import HTMLParser

from .contracts import ArtifactBlock

MAX_ARTIFACT_HTML_BYTES = 2 * 1024 * 1024


class ArtifactBlockError(ValueError):
    pass


def parse_artifact_block(text: str) -> ArtifactBlock:
    raw = str(text or "")
    matches = list(re.finditer(r"<artifact\b(?P<attrs>[^>]*)>(?P<body>[\s\S]*?)</artifact>", raw, re.I))
    if not matches:
        raise ArtifactBlockError("artifact block not found")
    if len(matches) != 1:
        raise ArtifactBlockError("multiple artifact blocks are not supported")
    match = matches[0]
    before = raw[: match.start()]
    after = raw[match.end() :]
    if "```" in before or "```" in after:
        raise ArtifactBlockError("artifact blocks must not be wrapped in markdown fences")
    attrs = _parse_attrs(match.group("attrs") or "")
    artifact_type = str(attrs.get("type") or "text/html").strip().lower() or "text/html"
    if artifact_type != "text/html":
        raise ArtifactBlockError("only text/html artifact blocks are supported")
    body = html.unescape(match.group("body") or "").strip()
    if len(body.encode("utf-8")) > MAX_ARTIFACT_HTML_BYTES:
        raise ArtifactBlockError("artifact html exceeds the maximum supported size")
    if not _looks_like_complete_html(body):
        raise ArtifactBlockError("artifact body must be a complete standalone html document")
    if after.strip():
        raise ArtifactBlockError("artifact block must be the final assistant output")
    return ArtifactBlock(
        identifier=str(attrs.get("identifier") or "").strip() or None,
        type=artifact_type,
        title=str(attrs.get("title") or "").strip() or None,
        html=body,
        raw_text_before=before,
        raw_text_after=after,
    )


class _AttrParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.attrs: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "artifact":
            self.attrs = {key.lower(): value or "" for key, value in attrs}


def _parse_attrs(raw_attrs: str) -> dict[str, str]:
    parser = _AttrParser()
    parser.feed(f"<artifact {raw_attrs}>")
    return parser.attrs


def _looks_like_complete_html(body: str) -> bool:
    lowered = body.lower()
    return "<!doctype html" in lowered and "<html" in lowered and ("<body" in lowered or "</body>" in lowered)

