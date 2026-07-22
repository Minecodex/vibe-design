from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ArtifactKindSpec:
    kind: str
    extensions: frozenset[str]
    renderers: frozenset[str]
    exports: frozenset[str]
    validation_kind: str | None = None


KIND_REGISTRY: dict[str, ArtifactKindSpec] = {
    "spreadsheet": ArtifactKindSpec(
        kind="spreadsheet",
        extensions=frozenset({".xlsx", ".xlsm", ".csv"}),
        renderers=frozenset({"file"}),
        exports=frozenset({"xlsx", "csv"}),
        validation_kind="sheet",
    ),
    "document": ArtifactKindSpec(
        kind="document",
        extensions=frozenset({".docx", ".pdf", ".md"}),
        renderers=frozenset({"file", "markdown"}),
        exports=frozenset({"docx", "pdf", "md"}),
        validation_kind="document",
    ),
    "deck": ArtifactKindSpec(
        kind="deck",
        extensions=frozenset({".pptx", ".html"}),
        renderers=frozenset({"file", "deck-html"}),
        exports=frozenset({"pptx", "pdf", "html", "zip"}),
        validation_kind="presentation",
    ),
    "html": ArtifactKindSpec(
        kind="html",
        extensions=frozenset({".html", ".htm"}),
        renderers=frozenset({"html"}),
        exports=frozenset({"html", "pdf", "zip"}),
        validation_kind="html",
    ),
    "svg": ArtifactKindSpec(
        kind="svg",
        extensions=frozenset({".svg"}),
        renderers=frozenset({"svg"}),
        exports=frozenset({"svg", "zip"}),
        validation_kind="text",
    ),
    "file": ArtifactKindSpec(
        kind="file",
        extensions=frozenset(),
        renderers=frozenset({"file"}),
        exports=frozenset({"file", "zip"}),
        validation_kind=None,
    ),
    "code": ArtifactKindSpec(
        kind="code",
        extensions=frozenset({".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".md", ".json"}),
        renderers=frozenset({"file", "markdown", "html"}),
        exports=frozenset({"file", "zip", "html", "md"}),
        validation_kind=None,
    ),
}


def validate_kind_contract(
    *,
    kind: str,
    renderer: str,
    exports: list[str],
    entry: str,
) -> tuple[bool, list[str], ArtifactKindSpec | None]:
    normalized_kind = str(kind or "").strip().lower()
    spec = KIND_REGISTRY.get(normalized_kind)
    if spec is None:
        return False, [f"unknown artifact kind: {kind}"], None

    errors: list[str] = []
    suffix = Path(entry).suffix.lower()
    normalized_renderer = str(renderer or "").strip().lower()
    normalized_exports = [str(item or "").strip().lower() for item in exports if str(item or "").strip()]

    if spec.extensions and suffix not in spec.extensions:
        errors.append(f"{normalized_kind} entry must use one of: {', '.join(sorted(spec.extensions))}")
    if normalized_renderer not in spec.renderers:
        errors.append(f"{normalized_kind} renderer must be one of: {', '.join(sorted(spec.renderers))}")
    invalid_exports = [item for item in normalized_exports if item not in spec.exports]
    if invalid_exports:
        errors.append(f"{normalized_kind} exports are invalid: {', '.join(invalid_exports)}")
    if normalized_kind not in {"code", "file"} and suffix == ".py":
        errors.append(".py files may only be registered as code artifacts or supporting_files")

    return not errors, errors, spec


def default_renderer_for_entry(*, kind: str, entry: str) -> str | None:
    normalized_kind = str(kind or "").strip().lower()
    spec = KIND_REGISTRY.get(normalized_kind)
    if spec is None:
        return None
    suffix = Path(entry).suffix.lower()
    if len(spec.renderers) == 1:
        return next(iter(spec.renderers))
    if normalized_kind == "deck" and suffix in {".html", ".htm"}:
        return "deck-html"
    if normalized_kind == "html":
        return "html"
    if normalized_kind == "svg":
        return "svg"
    if normalized_kind in {"document", "code"} and suffix == ".md":
        return "markdown"
    if normalized_kind == "code" and suffix in {".html", ".htm"}:
        return "html"
    return "file" if "file" in spec.renderers else next(iter(spec.renderers), None)


def default_exports_for_entry(*, kind: str, entry: str) -> list[str]:
    normalized_kind = str(kind or "").strip().lower()
    spec = KIND_REGISTRY.get(normalized_kind)
    if spec is None:
        return []
    suffix = Path(entry).suffix.lower().lstrip(".")
    if suffix and suffix in spec.exports:
        return [suffix]
    if normalized_kind == "file":
        return ["file"]
    if normalized_kind == "code":
        return ["file"]
    return [next(iter(sorted(spec.exports)))] if spec.exports else []


def manifest_publish_mode(manifest: dict[str, Any]) -> str:
    renderer = str(manifest.get("renderer") or "").strip().lower()
    entry = str(manifest.get("entry") or "").strip().lower()
    if renderer in {"html", "deck-html"} or entry.endswith((".html", ".htm")):
        return "html_bundle"
    return "file"
