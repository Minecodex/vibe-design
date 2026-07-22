import json
from pathlib import Path


def _write_artifact(conversation_dir: Path, *, asset_id: str, status: str) -> None:
    artifacts_dir = conversation_dir / ".meta" / "generation_artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / f"{asset_id}.json").write_text(
        json.dumps({"asset_id": asset_id, "status": status}),
        encoding="utf-8",
    )


def test_resolve_pending_generated_asset_reports_processing(tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    _write_artifact(conversation_dir, asset_id="generated_image_abc123", status="processing")

    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        resolve_pending_generated_asset,
    )

    result = resolve_pending_generated_asset(
        7,
        "conv-1",
        "references/generated/generated_image_abc123/original.png",
        get_conversation_dir_fn=lambda _user_id, _conversation_id: conversation_dir,
    )

    assert result == {"status": "processing", "media_kind": "image", "error": None}


def test_resolve_pending_generated_asset_reports_failed(tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    _write_artifact(conversation_dir, asset_id="generated_video_def456", status="failed")

    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        resolve_pending_generated_asset,
    )

    result = resolve_pending_generated_asset(
        7,
        "conv-1",
        "references/generated/generated_video_def456/original.mp4",
        get_conversation_dir_fn=lambda _user_id, _conversation_id: conversation_dir,
    )

    assert result is not None
    assert result["status"] == "failed"
    assert result["media_kind"] == "video"


def test_resolve_pending_generated_asset_ignores_non_generated_paths(tmp_path: Path):
    conversation_dir = tmp_path / "conversation"

    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        resolve_pending_generated_asset,
    )

    assert (
        resolve_pending_generated_asset(
            7,
            "conv-1",
            "project/report.html",
            get_conversation_dir_fn=lambda _user_id, _conversation_id: conversation_dir,
        )
        is None
    )


def test_workspace_preview_service_supports_project_root(monkeypatch, tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    preview_file = conversation_dir / "project" / "docx-parser-html" / "index.html"
    preview_file.parent.mkdir(parents=True, exist_ok=True)
    preview_file.write_text("<html></html>", encoding="utf-8")

    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        get_preview_workspace_file_path,
    )

    resolved = get_preview_workspace_file_path(
        7,
        "conv-1",
        "project/docx-parser-html/index.html",
        get_conversation_dir_fn=lambda _user_id, _conversation_id: conversation_dir,
    )

    assert resolved is not None
    resolved_file, resolved_root = resolved
    assert resolved_file == preview_file.resolve()
    assert resolved_root == (conversation_dir / "project").resolve()


def test_workspace_preview_service_supports_hidden_preview_cache_only_for_preview(monkeypatch, tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    cached_file = conversation_dir / ".agent" / "preview_cache" / "html_bundles" / "f_site" / "v0001" / "styles.css"
    cached_file.parent.mkdir(parents=True, exist_ok=True)
    cached_file.write_text("body{}", encoding="utf-8")

    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        get_preview_workspace_file_path,
        get_workspace_file_path,
    )

    resolved = get_preview_workspace_file_path(
        7,
        "conv-1",
        ".agent/preview_cache/html_bundles/f_site/v0001/styles.css",
        get_conversation_dir_fn=lambda _user_id, _conversation_id: conversation_dir,
    )

    assert resolved is not None
    resolved_file, resolved_root = resolved
    assert resolved_file == cached_file.resolve()
    assert resolved_root == (conversation_dir / ".agent" / "preview_cache").resolve()
    assert (
        get_workspace_file_path(
            7,
            "conv-1",
            ".agent/preview_cache/html_bundles/f_site/v0001/styles.css",
            get_conversation_dir_fn=lambda _user_id, _conversation_id: conversation_dir,
        )
        is None
    )


def test_workspace_preview_service_rejects_hidden_preview_cache_traversal(monkeypatch, tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    secret = conversation_dir / ".meta" / "secret.txt"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("secret", encoding="utf-8")

    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        get_preview_workspace_file_path,
    )

    assert (
        get_preview_workspace_file_path(
            7,
            "conv-1",
            ".agent/preview_cache/../.meta/secret.txt",
            get_conversation_dir_fn=lambda _user_id, _conversation_id: conversation_dir,
        )
        is None
    )


def test_workspace_preview_service_rejects_legacy_root_preview_cache(monkeypatch, tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    cached_file = conversation_dir / "preview_cache" / "html_bundles" / "f_site" / "v0001" / "styles.css"
    cached_file.parent.mkdir(parents=True, exist_ok=True)
    cached_file.write_text("body{}", encoding="utf-8")

    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        get_preview_workspace_file_path,
    )

    assert (
        get_preview_workspace_file_path(
            7,
            "conv-1",
            "preview_cache/html_bundles/f_site/v0001/styles.css",
            get_conversation_dir_fn=lambda _user_id, _conversation_id: conversation_dir,
        )
        is None
    )


def test_workspace_preview_media_type_sniffs_svg_content_with_png_name(tmp_path: Path):
    preview_file = tmp_path / "hero.png"
    preview_file.write_text(
        "<?xml version='1.0' encoding='UTF-8'?><svg xmlns='http://www.w3.org/2000/svg'></svg>",
        encoding="utf-8",
    )

    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        guess_workspace_preview_media_type,
    )

    assert guess_workspace_preview_media_type(preview_file) == "image/svg+xml"


def test_workspace_preview_media_type_keeps_real_png_type(tmp_path: Path):
    preview_file = tmp_path / "hero.png"
    preview_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        guess_workspace_preview_media_type,
    )

    assert guess_workspace_preview_media_type(preview_file) == "image/png"


def test_workspace_preview_image_thumbnail_generates_smaller_cached_png(tmp_path: Path):
    from PIL import Image

    source = tmp_path / "source.png"
    cache_root = tmp_path / "cache"
    Image.new("RGB", (1200, 600), color=(120, 80, 40)).save(source)

    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        resolve_workspace_image_thumbnail,
    )

    thumbnail = resolve_workspace_image_thumbnail(source, cache_root, 512)

    assert thumbnail is not None
    assert thumbnail.exists()
    assert thumbnail.suffix == ".png"
    with Image.open(thumbnail) as image:
        assert image.width == 512
        assert image.height == 256

    assert resolve_workspace_image_thumbnail(source, cache_root, 512) == thumbnail


def test_workspace_preview_image_thumbnail_ignores_invalid_width_and_non_images(tmp_path: Path):
    source = tmp_path / "notes.txt"
    source.write_text("hello", encoding="utf-8")

    from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
        resolve_workspace_image_thumbnail,
    )

    assert resolve_workspace_image_thumbnail(source, tmp_path / "cache", 512) is None
    assert resolve_workspace_image_thumbnail(source, tmp_path / "cache", 999) is None
