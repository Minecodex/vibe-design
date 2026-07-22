"""HomeHarness workspace file listing and preview rendering."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import re
import shutil
import tempfile
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from app.services.ephemeral_task_coordinator import EphemeralTaskCoordinator, EphemeralTaskKey

from .conversation_store_support import (
    get_conversation_dir,
    guess_workspace_file_type,
    is_within_path,
    read_json,
)

_PREVIEW_CACHE_PREFIX = ".agent/preview_cache"


def list_workspace_files(user_id: int, conversation_id: str) -> list[dict]:
    from app.services.agent_harness.workspace.session_v2.db_store import list_workspace_file_payloads

    items = list_workspace_file_payloads(user_id, conversation_id)
    if not items:
        items = _load_workspace_asset_fallback(user_id, conversation_id)
    return sorted(
        items,
        key=lambda item: (
            str(item.get("created_at") or item.get("updated_at") or ""),
            str(item.get("name") or ""),
        ),
    )


def _workspace_file_item(item: dict, source: str) -> dict:
    return {**item, "source": source}


def _workspace_asset_item(asset: dict) -> dict:
    path = str(asset.get("path") or "")
    name = str(asset.get("original_name") or Path(path).name or asset.get("asset_id") or "asset")
    mime_type = str(asset.get("mime_type") or "")
    file_type = guess_workspace_file_type(Path(name or path))
    if mime_type.startswith("image/"):
        file_type = "image"
    elif mime_type.startswith("video/"):
        file_type = "video"
    kind = str(asset.get("kind") or "")
    return {
        "file_id": str(asset.get("asset_id") or path),
        "name": name,
        "path": path,
        "type": file_type,
        "size": int(asset.get("size") or 0),
        "created_at": str(asset.get("created_at") or ""),
        "updated_at": None,
        "current_version_id": "",
        "versions": [],
        "source": "reference_asset" if kind == "reference" else "input_asset",
    }


def _load_workspace_asset_fallback(user_id: int, conversation_id: str) -> list[dict]:
    conversation_dir = get_conversation_dir(user_id, conversation_id)
    if not conversation_dir.exists():
        return []
    manifest_path = conversation_dir / ".meta" / "assets_manifest.json"
    if not manifest_path.exists():
        return []
    try:
        manifest = read_json(manifest_path)
    except Exception:
        return []
    assets = manifest.get("assets") if isinstance(manifest, dict) else None
    if not isinstance(assets, list):
        return []
    items: list[dict] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        item = _workspace_asset_item(asset)
        file_path = conversation_dir / Path(str(item.get("path") or "").replace("/", "\\"))
        if file_path.is_file():
            item["size"] = int(file_path.stat().st_size)
        items.append(item)
    return items


def get_workspace_file_path(
    user_id: int,
    conversation_id: str,
    file_path: str,
    *,
    get_conversation_dir_fn: Callable[[int, str], Path] = get_conversation_dir,
) -> Path | None:
    conversation_dir = get_conversation_dir_fn(user_id, conversation_id).resolve()
    normalized = file_path.replace("\\", "/").lstrip("/")
    allowed_prefixes = (
        "published/",
        "project/",
        "references/inputs/",
        "references/sources/",
        "references/generated/",
    )
    if not normalized.startswith(allowed_prefixes):
        return None
    resolved = (conversation_dir / Path(normalized)).resolve()
    if not is_within_path(resolved, conversation_dir):
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


def get_preview_workspace_file_path(
    user_id: int,
    conversation_id: str,
    file_path: str,
    *,
    get_conversation_dir_fn: Callable[[int, str], Path] = get_conversation_dir,
) -> tuple[Path, Path] | None:
    conversation_dir = get_conversation_dir_fn(user_id, conversation_id).resolve()
    normalized = str(file_path or "").replace("\\", "/").strip().lstrip("/")
    if not normalized:
        return None

    candidates: list[tuple[Path, str]] = []
    if normalized.startswith("published/"):
        candidates.append((conversation_dir / "published", normalized[len("published/"):]))
    elif normalized.startswith("project/"):
        candidates.append((conversation_dir / "project", normalized[len("project/"):]))
    elif normalized.startswith("references/"):
        candidates.append((conversation_dir / "references", normalized[len("references/"):]))
    elif normalized.startswith(f"{_PREVIEW_CACHE_PREFIX}/"):
        candidates.append((_preview_cache_root(conversation_dir), normalized[len(f"{_PREVIEW_CACHE_PREFIX}/"):]))
    elif normalized.startswith(("assets/", "work/")):
        return None
    else:
        candidates.append((conversation_dir / "project", normalized))
        candidates.append((conversation_dir / "published", normalized))
        candidates.append((conversation_dir / "references", normalized))

    for base_dir, relative_path in candidates:
        resolved = _resolve_workspace_relative_file(base_dir, relative_path)
        if resolved is not None:
            return resolved, base_dir.resolve()
    return None


# Matches a planned generated-asset path, e.g.
# "references/generated/generated_image_<hex16>/original.png".
_GENERATED_ASSET_RE = re.compile(
    r"^references/generated/(?P<asset_id>[^/]+)/original\.[A-Za-z0-9]+$"
)


def resolve_pending_generated_asset(
    user_id: int,
    conversation_id: str,
    file_path: str,
    *,
    get_conversation_dir_fn: Callable[[int, str], Path] = get_conversation_dir,
) -> dict | None:
    """When a generated asset isn't on disk yet, report its generation status.

    Returns a dict ``{"status", "media_kind", "error"}`` when ``file_path`` points
    at a known generated asset whose file has not materialized yet, otherwise
    ``None`` (caller should treat ``None`` as a normal 404).

    ``status`` is normalized to ``"processing"`` (still generating / just landed
    but not flushed) or ``"failed"``. The lookup is pure filesystem (scans
    ``.meta/generation_artifacts``); it never touches the database.
    """
    normalized = str(file_path or "").replace("\\", "/").strip().lstrip("/")
    match = _GENERATED_ASSET_RE.match(normalized)
    if not match:
        return None
    asset_id = match.group("asset_id")
    media_kind = "video" if asset_id.startswith("generated_video_") else "image"

    conversation_dir = get_conversation_dir_fn(user_id, conversation_id).resolve()
    artifacts_dir = conversation_dir / ".meta" / "generation_artifacts"
    if not artifacts_dir.is_dir():
        return None

    for json_path in artifacts_dir.glob("*.json"):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or str(data.get("asset_id") or "") != asset_id:
            continue
        status = str(data.get("status") or "").strip().lower()
        if status == "failed":
            return {
                "status": "failed",
                "media_kind": media_kind,
                "error": data.get("error") or data.get("error_message"),
            }
        # planned / processing / running / pending — or completed but the file
        # hasn't been flushed to disk yet (download race): keep the client polling.
        return {"status": "processing", "media_kind": media_kind, "error": None}
    return None


class _HtmlDependencyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self.style_blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): (value or "") for name, value in attrs}

        for attr_name in ("src", "href", "poster"):
            value = attributes.get(attr_name)
            if value:
                self.references.append(value)

        srcset = attributes.get("srcset")
        if srcset:
            self.references.extend(_extract_srcset_urls(srcset))

        inline_style = attributes.get("style")
        if inline_style:
            self.references.extend(_extract_css_urls(inline_style))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self.lasttag == "style":
            self.style_blocks.append(data)


_CSS_URL_PATTERN = re.compile(r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)", re.IGNORECASE)
_CSS_IMPORT_PATTERN = re.compile(r"@import\s+(?:url\(\s*)?['\"]([^'\")]+)['\"]\s*\)?", re.IGNORECASE)
_HTML_ATTR_PATTERN = re.compile(r'(?P<attr>\b(?:src|href|poster)=["\'])(?P<url>[^"\']+)(?P<quote>["\'])', re.IGNORECASE)
_HTML_SRCSET_PATTERN = re.compile(r'(?P<attr>\bsrcset=["\'])(?P<value>[^"\']+)(?P<quote>["\'])', re.IGNORECASE)
_HTML_STYLE_ATTR_PATTERN = re.compile(r'(?P<attr>\bstyle=["\'])(?P<value>[^"\']*)(?P<quote>["\'])', re.IGNORECASE)
_HTML_STYLE_BLOCK_PATTERN = re.compile(r"(<style\b[^>]*>)(.*?)(</style>)", re.IGNORECASE | re.DOTALL)
_HTML_BUNDLE_MAX_FILES = 1000
_HTML_BUNDLE_MAX_TOTAL_BYTES = 100 * 1024 * 1024
_HTML_BUNDLE_MAX_FILE_BYTES = 25 * 1024 * 1024


def analyze_html_bundle_entry(entry_file: Path, files_root: Path | None = None) -> dict[str, object]:
    resolved_entry = entry_file.resolve()
    resolved_root = (files_root or resolved_entry.parent).resolve()
    errors: list[str] = []
    members = _collect_html_bundle_members(resolved_entry, resolved_root, errors=errors, strict=True)
    entry = str(resolved_entry.relative_to(resolved_root)).replace("\\", "/")
    return {
        "entry": entry,
        "files_root": resolved_root,
        "members": members,
        "errors": errors,
    }


def create_html_bundle_from_entry(entry_file: Path, *, files_root: Path | None = None, output_dir: Path | None = None) -> Path:
    resolved_entry = entry_file.resolve()
    resolved_root = (files_root or resolved_entry.parent).resolve()
    bundle_members = _collect_html_bundle_members(resolved_entry, resolved_root)
    temp_root = (output_dir or Path(tempfile.gettempdir())).resolve()
    temp_root.mkdir(parents=True, exist_ok=True)

    sanitized_name = re.sub(r"[^A-Za-z0-9._-]+", "-", resolved_entry.stem).strip("-") or "bundle"
    temp_file = tempfile.NamedTemporaryFile(
        prefix=f"{sanitized_name}-",
        suffix=".zip",
        delete=False,
        dir=str(temp_root),
    )
    temp_path = Path(temp_file.name)
    temp_file.close()

    with ZipFile(temp_path, "w", compression=ZIP_DEFLATED) as archive:
        for member in sorted(bundle_members):
            archive.write(member, arcname=str(member.relative_to(resolved_root)).replace("\\", "/"))

    return temp_path


def create_html_bundle(
    user_id: int,
    conversation_id: str,
    file_path: str,
    *,
    get_conversation_dir_fn: Callable[[int, str], Path] = get_conversation_dir,
) -> Path:
    entry_file = get_workspace_file_path(
        user_id,
        conversation_id,
        file_path,
        get_conversation_dir_fn=get_conversation_dir_fn,
    )
    if entry_file is None:
        raise FileNotFoundError(file_path)
    if entry_file.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("HTML bundle export only supports .html or .htm files")

    entry_file = entry_file.resolve()
    files_root = entry_file.parent.resolve()
    return create_html_bundle_from_entry(entry_file, files_root=files_root)


def render_html_preview_document(
    user_id: int,
    conversation_id: str,
    file_path: str,
    *,
    preview_url_builder: callable,
    get_conversation_dir_fn: Callable[[int, str], Path] = get_conversation_dir,
) -> str:
    resolved = get_preview_workspace_file_path(
        user_id,
        conversation_id,
        file_path,
        get_conversation_dir_fn=get_conversation_dir_fn,
    )
    if resolved is None:
        raise FileNotFoundError(file_path)
    entry_file, files_root = resolved
    if entry_file.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("HTML preview only supports .html or .htm files")

    return _render_html_entry(
        entry_file,
        files_root,
        preview_url_builder=_preview_cache_url_builder(
            entry_file,
            files_root,
            preview_url_builder,
            get_conversation_dir_fn(user_id, conversation_id).resolve(),
        ),
    )


def render_html_bundle_preview_document(
    user_id: int,
    conversation_id: str,
    file_id: str,
    version_id: str | None,
    *,
    preview_url_builder: callable,
    entry: str | None = None,
    get_conversation_dir_fn: Callable[[int, str], Path] = get_conversation_dir,
) -> str:
    from app.services.agent_harness.workspace.generated_content.file_version_store import (
        get_versioned_file,
        resolve_version_path,
    )

    source = resolve_version_path(user_id, conversation_id, file_id, version_id)
    if source.suffix.lower() != ".zip":
        raise ValueError("HTML bundle preview only supports .zip files")
    file = get_versioned_file(user_id, conversation_id, file_id)
    target_version_id = version_id or file.current_version_id
    current_version = next(
        (item for item in file.versions if item.version_id == target_version_id),
        None,
    )
    if current_version is None:
        raise FileNotFoundError(target_version_id or file_id)

    conversation_dir = get_conversation_dir_fn(user_id, conversation_id).resolve()
    cache_root = _html_bundle_cache_root(
        conversation_dir,
        file_id,
        current_version.version_id,
        current_version.sha256,
    )
    extract_root = _ensure_html_bundle_cache(source, cache_root)
    resolved_entry = entry
    if resolved_entry is None:
        resolved_entry = str((current_version.artifact_metadata or {}).get("entry") or "").strip() or None
    entry_path = _resolve_html_bundle_entry(extract_root, resolved_entry)
    preview_root = _preview_cache_root(conversation_dir)
    return _render_html_entry(
        entry_path,
        extract_root,
        preview_url_builder=lambda relative_path: preview_url_builder(
            (Path(_PREVIEW_CACHE_PREFIX) / Path(relative_path)).as_posix()
            if not str(relative_path).startswith(f"{_PREVIEW_CACHE_PREFIX}/")
            else str(relative_path)
        ),
        preview_root=preview_root,
    )


async def render_html_bundle_preview_document_async(
    user_id: int,
    conversation_id: str,
    file_id: str,
    version_id: str | None,
    *,
    preview_url_builder: callable,
    entry: str | None = None,
    get_conversation_dir_fn: Callable[[int, str], Path] = get_conversation_dir,
) -> str:
    from app.services.agent_harness.workspace.generated_content.file_version_store import (
        get_versioned_file,
        resolve_version_path,
    )

    source = resolve_version_path(user_id, conversation_id, file_id, version_id)
    if source.suffix.lower() != ".zip":
        raise ValueError("HTML bundle preview only supports .zip files")
    file = get_versioned_file(user_id, conversation_id, file_id)
    target_version_id = version_id or file.current_version_id
    current_version = next(
        (item for item in file.versions if item.version_id == target_version_id),
        None,
    )
    if current_version is None:
        raise FileNotFoundError(target_version_id or file_id)

    conversation_dir = get_conversation_dir_fn(user_id, conversation_id).resolve()
    cache_root = _html_bundle_cache_root(
        conversation_dir,
        file_id,
        current_version.version_id,
        current_version.sha256,
    )
    extract_root = await _ensure_html_bundle_cache_async(source, cache_root)
    resolved_entry = entry
    if resolved_entry is None:
        resolved_entry = (
            str((current_version.artifact_metadata or {}).get("entry") or "").strip() or None
        )
    entry_path = _resolve_html_bundle_entry(extract_root, resolved_entry)
    preview_root = _preview_cache_root(conversation_dir)
    return _render_html_entry(
        entry_path,
        extract_root,
        preview_url_builder=lambda relative_path: preview_url_builder(
            (Path(_PREVIEW_CACHE_PREFIX) / Path(relative_path)).as_posix()
            if not str(relative_path).startswith(f"{_PREVIEW_CACHE_PREFIX}/")
            else str(relative_path)
        ),
        preview_root=preview_root,
    )


def render_css_preview_document(
    user_id: int,
    conversation_id: str,
    file_path: str,
    *,
    preview_url_builder: callable,
    get_conversation_dir_fn: Callable[[int, str], Path] = get_conversation_dir,
) -> str:
    resolved = get_preview_workspace_file_path(
        user_id,
        conversation_id,
        file_path,
        get_conversation_dir_fn=get_conversation_dir_fn,
    )
    if resolved is None:
        raise FileNotFoundError(file_path)
    css_file, files_root = resolved
    css_text = css_file.read_text(encoding="utf-8")
    return _rewrite_css_text(
        css_text,
        css_file,
        files_root,
        _preview_cache_url_builder(
            css_file,
            files_root,
            preview_url_builder,
            get_conversation_dir_fn(user_id, conversation_id).resolve(),
        ),
    )


def resolve_workspace_preview_path(user_id: int, conversation_id: str, file_path: str) -> Path | None:
    resolved = get_preview_workspace_file_path(user_id, conversation_id, file_path)
    return resolved[0] if resolved else None


def guess_workspace_preview_media_type(path: Path) -> str:
    sniffed = _sniff_preview_media_type(path)
    if sniffed:
        return sniffed
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def resolve_workspace_image_thumbnail(
    source_path: Path,
    cache_root: Path,
    width: int | None,
) -> Path | None:
    safe_width = _normalize_preview_thumbnail_width(width)
    if safe_width is None:
        return None
    media_type = guess_workspace_preview_media_type(source_path)
    if not media_type.startswith("image/") or media_type == "image/svg+xml":
        return None

    try:
        from PIL import Image
    except Exception:
        return None

    try:
        stat = source_path.stat()
    except OSError:
        return None

    cache_dir = cache_root / "image_thumbs"
    cache_name = f"{source_path.stem}-{stat.st_mtime_ns}-{stat.st_size}-w{safe_width}.png"
    target_path = cache_dir / cache_name
    if target_path.exists():
        return target_path

    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = cache_dir / f".{cache_name}.{uuid.uuid4().hex}.tmp"
    try:
        with Image.open(source_path) as image:
            image.load()
            if image.width <= safe_width:
                return None
            next_image = image.convert("RGBA") if image.mode not in ("RGB", "RGBA") else image.copy()
            ratio = safe_width / float(next_image.width)
            next_height = max(1, int(round(next_image.height * ratio)))
            next_image.thumbnail((safe_width, next_height), Image.Resampling.LANCZOS)
            next_image.save(tmp_path, format="PNG", optimize=True)
        tmp_path.replace(target_path)
        return target_path
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _normalize_preview_thumbnail_width(width: int | None) -> int | None:
    if width is None:
        return None
    try:
        value = int(width)
    except (TypeError, ValueError):
        return None
    return value if value in {256, 512, 1024} else None


def _render_html_entry(
    entry_file: Path,
    files_root: Path,
    *,
    preview_url_builder: callable,
    preview_root: Path | None = None,
) -> str:
    html_text = entry_file.read_text(encoding="utf-8")
    root_for_urls = preview_root or files_root

    rewritten = _HTML_ATTR_PATTERN.sub(
        lambda match: _rewrite_html_attr_match(match, entry_file, root_for_urls, preview_url_builder),
        html_text,
    )
    rewritten = _HTML_SRCSET_PATTERN.sub(
        lambda match: _rewrite_html_srcset_match(match, entry_file, root_for_urls, preview_url_builder),
        rewritten,
    )
    rewritten = _HTML_STYLE_ATTR_PATTERN.sub(
        lambda match: _rewrite_html_style_attr_match(match, entry_file, root_for_urls, preview_url_builder),
        rewritten,
    )
    rewritten = _HTML_STYLE_BLOCK_PATTERN.sub(
        lambda match: f"{match.group(1)}{_rewrite_css_text(match.group(2), entry_file, root_for_urls, preview_url_builder)}{match.group(3)}",
        rewritten,
    )
    return rewritten


def _ensure_html_bundle_cache(source: Path, cache_root: Path) -> Path:
    marker = cache_root / ".complete"
    if marker.exists():
        return cache_root
    coordinator = EphemeralTaskCoordinator(ttl_seconds=120.0)
    task = _html_bundle_cache_task(source, cache_root)
    lease = coordinator.start_sync(task, ttl_seconds=120.0, owner_prefix="html-preview")
    if not lease.acquired:
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            if marker.exists():
                return cache_root
            time.sleep(0.025)
        raise ValueError("HTML bundle preview is still being prepared")
    try:
        _extract_html_bundle_cache(source, cache_root)
        coordinator.finish_sync(lease, status="done", result={"cache": "ready"})
    except BadZipFile as exc:
        coordinator.fail_sync(lease, error_type="BadZipFile")
        raise ValueError("Invalid HTML bundle zip") from exc
    except Exception as exc:
        coordinator.fail_sync(lease, error_type=type(exc).__name__)
        raise
    return cache_root


async def _ensure_html_bundle_cache_async(source: Path, cache_root: Path) -> Path:
    marker = cache_root / ".complete"
    if marker.exists():
        return cache_root
    coordinator = EphemeralTaskCoordinator(ttl_seconds=120.0)
    task = _html_bundle_cache_task(source, cache_root)
    lease = await coordinator.start(task, ttl_seconds=120.0, owner_prefix="html-preview")
    if not lease.acquired:
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            if marker.exists():
                return cache_root
            await asyncio.sleep(0.025)
        raise ValueError("HTML bundle preview is still being prepared")
    try:
        await asyncio.to_thread(_extract_html_bundle_cache, source, cache_root)
        await coordinator.finish(lease, status="done", result={"cache": "ready"})
    except BadZipFile as exc:
        await coordinator.fail(lease, error_type="BadZipFile")
        raise ValueError("Invalid HTML bundle zip") from exc
    except Exception as exc:
        await coordinator.fail(lease, error_type=type(exc).__name__)
        raise
    return cache_root


def _html_bundle_cache_root(
    conversation_dir: Path,
    file_id: str,
    version_id: str,
    sha256: str,
) -> Path:
    return (
        _preview_cache_root(conversation_dir)
        / "html_bundles"
        / file_id
        / version_id
        / sha256[:16]
    )


def _html_bundle_cache_task(source: Path, cache_root: Path) -> EphemeralTaskKey:
    return EphemeralTaskKey.build(
        domain="artifact-preview",
        kind="html-bundle-cache",
        resource_parts=[source.name, cache_root.name, cache_root.parent.name],
        version=_file_version(source),
    )


def _extract_html_bundle_cache(source: Path, cache_root: Path) -> None:
    with ZipFile(source) as archive:
        members = _validated_html_bundle_members(archive)
        temp_root = cache_root.parent / f".{cache_root.name}.{uuid.uuid4().hex}.tmp"
        if temp_root.exists():
            shutil.rmtree(temp_root)
        temp_root.mkdir(parents=True, exist_ok=True)
        try:
            for info in members:
                target = _safe_bundle_member_path(temp_root, info.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            marker_tmp = temp_root / ".complete"
            marker_tmp.write_text("ok", encoding="utf-8")
            if cache_root.exists():
                shutil.rmtree(cache_root)
            temp_root.rename(cache_root)
        except Exception:
            shutil.rmtree(temp_root, ignore_errors=True)
            raise


def _validated_html_bundle_members(archive: ZipFile):
    members = [info for info in archive.infolist() if not info.is_dir()]
    if len(members) > _HTML_BUNDLE_MAX_FILES:
        raise ValueError("HTML bundle has too many files")
    total_size = 0
    for info in members:
        _validate_bundle_member_name(info.filename)
        if _zip_member_is_symlink(info):
            raise ValueError(f"HTML bundle contains unsafe symlink: {info.filename}")
        if info.file_size > _HTML_BUNDLE_MAX_FILE_BYTES:
            raise ValueError(f"HTML bundle member is too large: {info.filename}")
        total_size += int(info.file_size or 0)
        if total_size > _HTML_BUNDLE_MAX_TOTAL_BYTES:
            raise ValueError("HTML bundle is too large")
    return members


def _zip_member_is_symlink(info) -> bool:
    mode = (int(getattr(info, "external_attr", 0)) >> 16) & 0o170000
    return mode == 0o120000


def _validate_bundle_member_name(name: str) -> None:
    normalized = str(name or "").replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"HTML bundle contains unsafe path: {name}")


def _safe_bundle_member_path(root: Path, name: str) -> Path:
    _validate_bundle_member_name(name)
    target = (root / PurePosixPath(str(name).replace("\\", "/"))).resolve()
    if not is_within_path(target, root):
        raise ValueError(f"HTML bundle contains unsafe path: {name}")
    return target


def _resolve_html_bundle_entry(extract_root: Path, entry: str | None) -> Path:
    requested_entry = _html_bundle_manifest_entry(extract_root) if entry is None else entry
    requested_entry = requested_entry or "index.html"
    candidates = [requested_entry]
    requested_path = PurePosixPath(str(requested_entry).replace("\\", "/"))
    if len(requested_path.parts) > 1 and requested_path.name:
        candidates.append(requested_path.name)

    for candidate in candidates:
        entry_path = _safe_bundle_member_path(extract_root, candidate)
        if not entry_path.exists() or not entry_path.is_file():
            continue
        if entry_path.suffix.lower() not in {".html", ".htm"}:
            raise ValueError("HTML bundle entry must be an .html or .htm file")
        return entry_path

    raise FileNotFoundError(requested_entry)


def _html_bundle_manifest_entry(extract_root: Path) -> str | None:
    manifest_path = extract_root / "manifest.json"
    if not manifest_path.exists() or not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    entry = str(data.get("entry") or "").strip()
    return entry or None


def _collect_html_bundle_members(
    entry_file: Path,
    files_root: Path,
    *,
    errors: list[str] | None = None,
    strict: bool = False,
) -> set[Path]:
    members: set[Path] = {entry_file}
    queued_css: list[Path] = []
    visited_css: set[Path] = set()

    html_text = entry_file.read_text(encoding="utf-8")
    parser = _HtmlDependencyParser()
    parser.feed(html_text)

    for reference in parser.references:
        resolved = _resolve_bundle_reference(reference, entry_file, files_root, errors=errors, strict=strict)
        if resolved is None:
            continue
        members.add(resolved)
        if resolved.suffix.lower() == ".css":
            queued_css.append(resolved)

    for style_block in parser.style_blocks:
        for reference in _extract_css_references(style_block):
            resolved = _resolve_bundle_reference(reference, entry_file, files_root, errors=errors, strict=strict)
            if resolved is None:
                continue
            members.add(resolved)
            if resolved.suffix.lower() == ".css":
                queued_css.append(resolved)

    while queued_css:
        css_file = queued_css.pop()
        if css_file in visited_css:
            continue
        visited_css.add(css_file)

        try:
            css_text = css_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for reference in _extract_css_references(css_text):
            resolved = _resolve_bundle_reference(reference, css_file, files_root, errors=errors, strict=strict)
            if resolved is None:
                continue
            if resolved not in members:
                members.add(resolved)
            if resolved.suffix.lower() == ".css" and resolved not in visited_css:
                queued_css.append(resolved)

    return members


def _rewrite_html_attr_match(match: re.Match[str], base_file: Path, files_root: Path, preview_url_builder) -> str:
    raw_url = match.group("url")
    resolved = _resolve_bundle_reference(raw_url, base_file, files_root)
    if resolved is None:
        return match.group(0)
    preview_url = preview_url_builder(str(resolved.relative_to(files_root)).replace("\\", "/"))
    return f"{match.group('attr')}{preview_url}{match.group('quote')}"


def _rewrite_html_srcset_match(match: re.Match[str], base_file: Path, files_root: Path, preview_url_builder) -> str:
    rewritten_parts: list[str] = []
    for item in match.group("value").split(","):
        trimmed = item.strip()
        if not trimmed:
            continue
        parts = trimmed.split()
        raw_url = parts[0]
        resolved = _resolve_bundle_reference(raw_url, base_file, files_root)
        if resolved is None:
            rewritten_parts.append(trimmed)
            continue
        preview_url = preview_url_builder(str(resolved.relative_to(files_root)).replace("\\", "/"))
        if len(parts) > 1:
            rewritten_parts.append(f"{preview_url} {' '.join(parts[1:])}")
        else:
            rewritten_parts.append(preview_url)
    return f"{match.group('attr')}{', '.join(rewritten_parts)}{match.group('quote')}"


def _rewrite_html_style_attr_match(match: re.Match[str], base_file: Path, files_root: Path, preview_url_builder) -> str:
    rewritten_value = _rewrite_css_text(match.group("value"), base_file, files_root, preview_url_builder)
    return f"{match.group('attr')}{rewritten_value}{match.group('quote')}"


def _rewrite_css_text(css_text: str, base_file: Path, files_root: Path, preview_url_builder) -> str:
    rewritten = _CSS_IMPORT_PATTERN.sub(
        lambda match: _rewrite_css_import_match(match, base_file, files_root, preview_url_builder),
        css_text,
    )
    rewritten = _CSS_URL_PATTERN.sub(
        lambda match: _rewrite_css_url_match(match, base_file, files_root, preview_url_builder),
        rewritten,
    )
    return rewritten


def _rewrite_css_import_match(match: re.Match[str], base_file: Path, files_root: Path, preview_url_builder) -> str:
    raw_url = match.group(1)
    resolved = _resolve_bundle_reference(raw_url, base_file, files_root)
    if resolved is None:
        return match.group(0)
    preview_url = preview_url_builder(str(resolved.relative_to(files_root)).replace("\\", "/"))
    return f'@import url("{preview_url}")'


def _rewrite_css_url_match(match: re.Match[str], base_file: Path, files_root: Path, preview_url_builder) -> str:
    raw_url = match.group(2)
    resolved = _resolve_bundle_reference(raw_url, base_file, files_root)
    if resolved is None:
        return match.group(0)
    preview_url = preview_url_builder(str(resolved.relative_to(files_root)).replace("\\", "/"))
    return f'url("{preview_url}")'


def _extract_css_references(css_text: str) -> list[str]:
    return [*_extract_css_urls(css_text), *_extract_css_imports(css_text)]


def _extract_css_urls(css_text: str) -> list[str]:
    return [match.group(2).strip() for match in _CSS_URL_PATTERN.finditer(css_text or "")]


def _extract_css_imports(css_text: str) -> list[str]:
    return [match.group(1).strip() for match in _CSS_IMPORT_PATTERN.finditer(css_text or "")]


def _extract_srcset_urls(srcset: str) -> list[str]:
    urls: list[str] = []
    for item in str(srcset or "").split(","):
        candidate = item.strip().split(" ", 1)[0].strip()
        if candidate:
            urls.append(candidate)
    return urls


def _resolve_bundle_reference(
    reference: str,
    base_file: Path,
    files_root: Path,
    *,
    errors: list[str] | None = None,
    strict: bool = False,
) -> Path | None:
    normalized = _normalize_local_bundle_reference(reference)
    if not normalized:
        return None

    resolved = (base_file.parent / normalized).resolve()
    files_root_resolved = files_root.resolve()
    if not is_within_path(resolved, files_root_resolved):
        if strict and errors is not None:
            errors.append(f"html bundle dependency escapes the bundle root: {reference}")
        return None
    if not resolved.exists() or not resolved.is_file():
        if strict and errors is not None:
            errors.append(f"html bundle dependency does not exist: {reference}")
        return None
    return resolved


def _normalize_local_bundle_reference(reference: str) -> str | None:
    raw = str(reference or "").strip()
    if not raw:
        return None
    if raw.startswith("#"):
        return None
    if _is_external_or_special_bundle_reference(raw):
        return None

    split = urlsplit(raw)
    if split.scheme or split.netloc:
        return None

    candidate = unquote((split.path or "").strip())
    # In-document fragment references (anchors, SVG filter/gradient self-refs like
    # `url(#n)`) are not file dependencies. The pre-split `startswith("#")` guard
    # misses percent-encoded forms (e.g. `%23n` inside an inline `data:image/svg+xml`
    # URI), so re-check after decoding.
    if not candidate or candidate.startswith("#"):
        return None
    if candidate.startswith("/"):
        candidate = candidate.lstrip("/")
    if candidate.startswith(("/", "\\")):
        return None
    return candidate


def _is_external_or_special_bundle_reference(value: str) -> bool:
    if _looks_like_email_bundle_reference(value):
        return True
    if _looks_like_external_bundle_url_reference(value):
        return True
    split = urlsplit(value)
    return bool(split.scheme or split.netloc)


def _looks_like_email_bundle_reference(value: str) -> bool:
    if any(separator in value for separator in ("/", "\\", "?", "#")):
        return False
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))


_COMMON_EXTERNAL_BUNDLE_TLDS = {
    "app",
    "biz",
    "cn",
    "co",
    "com",
    "dev",
    "edu",
    "io",
    "me",
    "net",
    "org",
    "site",
    "top",
    "xyz",
}


def _looks_like_external_bundle_url_reference(value: str) -> bool:
    if value.startswith(("./", "../", "/", "\\")):
        return False
    first_segment = value.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].strip().lower()
    if not first_segment or "." not in first_segment:
        return False
    tld = first_segment.rsplit(".", 1)[-1]
    return tld in _COMMON_EXTERNAL_BUNDLE_TLDS


def _resolve_workspace_relative_file(base_dir: Path, relative_path: str) -> Path | None:
    normalized = str(relative_path or "").replace("\\", "/").lstrip("/")
    if not normalized:
        return None

    base_resolved = base_dir.resolve()
    resolved = (base_resolved / Path(normalized)).resolve()
    if not is_within_path(resolved, base_resolved):
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


def _sniff_preview_media_type(path: Path) -> str | None:
    try:
        with path.open("rb") as file:
            sample = file.read(512)
    except OSError:
        return None
    stripped = sample.lstrip()
    if not stripped:
        return None
    if stripped.startswith(b"\xef\xbb\xbf"):
        stripped = stripped[3:].lstrip()
    lower = stripped[:256].lower()
    if lower.startswith(b"<svg") or (lower.startswith(b"<?xml") and b"<svg" in lower):
        return "image/svg+xml"
    return None


def _preview_cache_root(conversation_dir: Path) -> Path:
    return conversation_dir / ".agent" / "preview_cache"


def _preview_cache_url_builder(
    entry_file: Path,
    files_root: Path,
    preview_url_builder: callable,
    conversation_dir: Path,
):
    preview_root = _preview_cache_root(conversation_dir).resolve()
    try:
        entry_file.resolve().relative_to(preview_root)
        files_root.resolve().relative_to(preview_root)
    except ValueError:
        return preview_url_builder

    def _build(relative_path: str) -> str:
        normalized = str(relative_path or "").replace("\\", "/").strip().lstrip("/")
        if normalized.startswith(f"{_PREVIEW_CACHE_PREFIX}/"):
            return preview_url_builder(normalized)
        return preview_url_builder((Path(_PREVIEW_CACHE_PREFIX) / Path(normalized)).as_posix())

    return _build


def _file_version(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"
