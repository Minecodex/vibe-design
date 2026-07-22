from pathlib import Path
from zipfile import ZipFile

import pytest

from app.core.config import Settings
from app.core.redis_coordination import InProcessRedisCoordinator
from app.services.ephemeral_task_coordinator import EphemeralTaskCoordinator, EphemeralTaskKey
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_html_bundle,
    create_conversation,
    render_html_bundle_preview_document,
    render_html_preview_document,
    render_css_preview_document,
)
from app.services.agent_harness.workspace.conversation.workspace_preview_service import (
    _ensure_html_bundle_cache,
    _file_version,
    analyze_html_bundle_entry,
    render_html_bundle_preview_document_async,
)
from app.services.agent_harness.workspace.generated_content.file_version_store import append_file_version


def test_create_html_bundle_includes_local_html_dependencies(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    files_dir = tmp_path / "users" / "7" / "conversations" / "conv-1" / "published" / "f_site" / "v0001" / "site"
    files_dir.mkdir(parents=True)
    entry_file = files_dir / "index.html"
    (files_dir / "styles.css").write_text(
        "body{background:url('./images/bg.png')} @import './theme.css';",
        encoding="utf-8",
    )
    (files_dir / "theme.css").write_text(".hero{background:url('./videos/intro.mp4')}", encoding="utf-8")
    (files_dir / "app.js").write_text("console.log('hi')", encoding="utf-8")
    (files_dir / "images").mkdir()
    (files_dir / "images" / "hero.png").write_bytes(b"hero")
    (files_dir / "images" / "bg.png").write_bytes(b"bg")
    (files_dir / "videos").mkdir()
    (files_dir / "videos" / "intro.mp4").write_bytes(b"video")
    entry_file.write_text(
        """
<!doctype html>
<html>
  <head>
    <link rel="stylesheet" href="./styles.css">
    <script src="./app.js"></script>
  </head>
  <body style="background-image:url('./images/bg.png')">
    <img src="./images/hero.png" srcset="./images/hero.png 1x">
    <video src="./videos/intro.mp4" poster="./images/hero.png"></video>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    bundle_path = create_html_bundle(7, "conv-1", "published/f_site/v0001/site/index.html")

    assert bundle_path.suffix == ".zip"
    with ZipFile(bundle_path) as bundle:
        assert sorted(bundle.namelist()) == [
            "app.js",
            "images/bg.png",
            "images/hero.png",
            "index.html",
            "styles.css",
            "theme.css",
            "videos/intro.mp4",
        ]


def test_analyze_bundle_ignores_inline_svg_fragment_self_reference(tmp_path: Path):
    # Inline SVG noise filter referenced via url(%23n) (percent-encoded '#n') inside a
    # data:image/svg+xml background is an in-document self-reference, not a file.
    entry_file = tmp_path / "index.html"
    entry_file.write_text(
        """
<!doctype html>
<html>
  <body>
    <div style="background:url(&quot;data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg'><filter id='n'><feTurbulence/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>&quot;)"></div>
    <a href="#contact">Contact</a>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    result = analyze_html_bundle_entry(entry_file)

    assert result["errors"] == []
    assert all("%23n" not in err for err in result["errors"])


def test_analyze_bundle_ignores_external_and_special_links(tmp_path: Path):
    entry_file = tmp_path / "index.html"
    entry_file.write_text(
        """
<!doctype html>
<html>
  <body>
    <a href="kakjzzw@gmail.com">Email</a>
    <a href="mailto:kakjzzw@gmail.com">Mailto</a>
    <a href="www.example.com/contact">Bare domain</a>
    <a href="//cdn.example.com/app.css">Protocol-relative CDN</a>
    <a href="whatsapp://send?phone=123">Custom protocol</a>
    <a href="sms:+15551234567">SMS</a>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    result = analyze_html_bundle_entry(entry_file)

    assert result["errors"] == []


def test_create_html_bundle_excludes_remote_and_escaping_dependencies(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    files_dir = tmp_path / "users" / "7" / "conversations" / "conv-1" / "published" / "f_site" / "v0001"
    files_dir.mkdir(parents=True)
    entry_file = files_dir / "index.html"
    (files_dir / "safe.png").write_bytes(b"safe")
    entry_file.write_text(
        """
<!doctype html>
<html>
  <body>
    <img src="./safe.png">
    <img src="https://example.com/remote.png">
    <img src="../secret.png">
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    bundle_path = create_html_bundle(7, "conv-1", "published/f_site/v0001/index.html")

    with ZipFile(bundle_path) as bundle:
        assert sorted(bundle.namelist()) == ["index.html", "safe.png"]


def test_create_html_bundle_rejects_non_html_entries(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    files_dir = tmp_path / "users" / "7" / "conversations" / "conv-1" / "published" / "f_notes" / "v0001"
    files_dir.mkdir(parents=True)
    (files_dir / "notes.txt").write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError):
        create_html_bundle(7, "conv-1", "published/f_notes/v0001/notes.txt")


def test_render_html_preview_document_rewrites_local_dependencies(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    files_dir = tmp_path / "users" / "7" / "conversations" / "conv-1" / "published" / "f_site" / "v0001" / "site"
    (files_dir / "images").mkdir(parents=True)
    (files_dir / "scripts").mkdir(parents=True)
    (files_dir / "styles").mkdir(parents=True)
    (files_dir / "images" / "hero.png").write_bytes(b"hero")
    (files_dir / "scripts" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    (files_dir / "styles" / "site.css").write_text("body{}", encoding="utf-8")
    entry_file = files_dir / "index.html"
    entry_file.write_text(
        """
<!doctype html>
<html>
  <head>
    <link rel="stylesheet" href="./styles/site.css">
    <style>.hero{background:url('./images/hero.png')}</style>
  </head>
  <body style="background-image:url('./images/hero.png')">
    <img src="./images/hero.png" srcset="./images/hero.png 1x, https://example.com/hero.png 2x">
    <script src="./scripts/app.js"></script>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    rendered = render_html_preview_document(
        7,
        "conv-1",
        "published/f_site/v0001/site/index.html",
        preview_url_builder=lambda path: f"/preview/{path}?preview_token=abc",
    )

    assert "/preview/f_site/v0001/site/styles/site.css?preview_token=abc" in rendered
    assert "/preview/f_site/v0001/site/images/hero.png?preview_token=abc" in rendered
    assert "/preview/f_site/v0001/site/scripts/app.js?preview_token=abc" in rendered
    assert "https://example.com/hero.png 2x" in rendered


def test_render_css_preview_document_rewrites_local_css_urls(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    files_dir = tmp_path / "users" / "7" / "conversations" / "conv-1" / "published" / "f_site" / "v0001" / "site"
    (files_dir / "images").mkdir(parents=True)
    (files_dir / "images" / "bg.png").write_bytes(b"bg")
    (files_dir / "nested").mkdir(parents=True)
    css_file = files_dir / "nested" / "page.css"
    css_file.write_text(
        "@import '../theme.css'; .hero{background:url('../images/bg.png')} .remote{background:url('https://example.com/bg.png')}",
        encoding="utf-8",
    )
    (files_dir / "theme.css").write_text("body{}", encoding="utf-8")

    rendered = render_css_preview_document(
        7,
        "conv-1",
        "published/f_site/v0001/site/nested/page.css",
        preview_url_builder=lambda path: f"/preview/{path}?preview_token=xyz",
    )

    assert "@import url(\"/preview/f_site/v0001/site/theme.css?preview_token=xyz\")" in rendered
    assert "url(\"/preview/f_site/v0001/site/images/bg.png?preview_token=xyz\")" in rendered
    assert "https://example.com/bg.png" in rendered


def test_render_html_bundle_preview_document_extracts_versioned_zip(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="HTML bundle")
    root = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    source = root / "work" / "generated" / "run-1" / "site.zip"
    source.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source, "w") as bundle:
        bundle.writestr("index.html", '<link rel="stylesheet" href="styles/site.css"><img src="images/hero.png">')
        bundle.writestr("styles/site.css", "body{background:url('../images/hero.png')}")
        bundle.writestr("images/hero.png", b"hero")
    published = append_file_version(
        7,
        conversation["id"],
        source_path=source,
        name="site.zip",
        file_type="html_bundle",
        run_id="run-1",
    )

    rendered = render_html_bundle_preview_document(
        7,
        conversation["id"],
        published["file_id"],
        "v0001",
        preview_url_builder=lambda path: f"/preview/{path}",
    )

    assert "/preview/.agent/preview_cache/html_bundles/" in rendered
    assert "styles/site.css" in rendered
    assert "images/hero.png" in rendered


def test_render_html_bundle_preview_falls_back_to_root_entry_name(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Legacy HTML bundle")
    root = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    source = root / "work" / "generated" / "run-1" / "site.zip"
    source.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source, "w") as bundle:
        bundle.writestr("index.html", '<link rel="stylesheet" href="styles/site.css"><h1>ok</h1>')
        bundle.writestr("styles/site.css", "body{}")
    published = append_file_version(
        7,
        conversation["id"],
        source_path=source,
        name="site.zip",
        file_type="web",
        run_id="run-1",
        artifact_metadata={
            "artifact_kind": "web_bundle",
            "bundle_format": "zip",
            "entry": "html-ppt-prepared/index.html",
            "source_path": "html-ppt-prepared/index.html",
        },
    )

    rendered = render_html_bundle_preview_document(
        7,
        conversation["id"],
        published["file_id"],
        "v0001",
        preview_url_builder=lambda path: f"/preview/{path}",
    )

    assert "<h1>ok</h1>" in rendered
    assert "/preview/.agent/preview_cache/html_bundles/" in rendered
    assert "styles/site.css" in rendered


def test_render_html_bundle_preview_document_rejects_zip_slip(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Unsafe HTML bundle")
    root = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    source = root / "work" / "generated" / "run-1" / "site.zip"
    source.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source, "w") as bundle:
        bundle.writestr("index.html", "<html></html>")
        bundle.writestr("../escape.txt", "nope")
    published = append_file_version(
        7,
        conversation["id"],
        source_path=source,
        name="site.zip",
        file_type="html_bundle",
        run_id="run-1",
    )

    with pytest.raises(ValueError, match="unsafe"):
        render_html_bundle_preview_document(
            7,
            conversation["id"],
            published["file_id"],
            "v0001",
            preview_url_builder=lambda path: f"/preview/{path}",
        )


@pytest.mark.asyncio
async def test_render_html_bundle_preview_async_extracts_uncached_zip(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Async HTML bundle")
    root = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    source = root / "work" / "generated" / "run-1" / "site.zip"
    source.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source, "w") as bundle:
        bundle.writestr("index.html", '<link rel="stylesheet" href="styles/site.css">')
        bundle.writestr("styles/site.css", "body{}")
    published = append_file_version(
        7,
        conversation["id"],
        source_path=source,
        name="site.zip",
        file_type="html_bundle",
        run_id="run-1",
    )

    rendered = await render_html_bundle_preview_document_async(
        7,
        conversation["id"],
        published["file_id"],
        "v0001",
        preview_url_builder=lambda path: f"/preview/{path}",
    )

    assert "/preview/.agent/preview_cache/html_bundles/" in rendered
    assert "styles/site.css" in rendered


def test_html_bundle_cache_guard_blocks_duplicate_extract_and_allows_retry(monkeypatch, tmp_path: Path):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    source = tmp_path / "site.zip"
    with ZipFile(source, "w") as bundle:
        bundle.writestr("index.html", "<html></html>")
    cache_root = tmp_path / "cache" / "html_bundles" / "f_site" / "v0001" / "abc123"
    guard = EphemeralTaskCoordinator(ttl_seconds=120)
    task = EphemeralTaskKey.build(
        domain="artifact-preview",
        kind="html-bundle-cache",
        resource_parts=[source.name, cache_root.name, cache_root.parent.name],
        version=_file_version(source),
    )
    lease = guard.start_sync(task, ttl_seconds=120, owner_prefix="test")

    with pytest.raises(ValueError, match="still being prepared"):
        _ensure_html_bundle_cache(source, cache_root)

    guard.fail_sync(lease, error_type="SyntheticFailure")
    extracted = _ensure_html_bundle_cache(source, cache_root)

    assert extracted == cache_root
    assert (cache_root / ".complete").exists()
