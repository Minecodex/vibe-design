from pathlib import Path

from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_html_bundle,
    get_preview_workspace_file_path,
    get_workspace_file_path,
    render_css_preview_document,
    render_html_preview_document,
)


def test_get_preview_workspace_file_path_supports_project_root(monkeypatch, tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    preview_file = conversation_dir / "project" / "docx-parser-html" / "index.html"
    preview_file.parent.mkdir(parents=True, exist_ok=True)
    preview_file.write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.get_conversation_dir",
        lambda user_id, conversation_id: conversation_dir,
    )

    resolved = get_preview_workspace_file_path(7, "conv-1", "project/docx-parser-html/index.html")

    assert resolved is not None
    resolved_file, resolved_root = resolved
    assert resolved_file == preview_file.resolve()
    assert resolved_root == (conversation_dir / "project").resolve()


def test_get_preview_workspace_file_path_supports_references_prefix(monkeypatch, tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    preview_file = conversation_dir / "references" / "generated" / "generated_image_001" / "original.png"
    preview_file.parent.mkdir(parents=True, exist_ok=True)
    preview_file.write_bytes(b"png")

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.get_conversation_dir",
        lambda user_id, conversation_id: conversation_dir,
    )

    resolved = get_preview_workspace_file_path(7, "conv-1", "references/generated/generated_image_001/original.png")

    assert resolved is not None
    resolved_file, resolved_root = resolved
    assert resolved_file == preview_file.resolve()
    assert resolved_root == (conversation_dir / "references").resolve()


def test_get_preview_workspace_file_path_rejects_removed_intermediate_assets(monkeypatch, tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    preview_file = conversation_dir / "assets" / "intermediate" / "run-1" / "image.png"
    preview_file.parent.mkdir(parents=True, exist_ok=True)
    preview_file.write_bytes(b"png")

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.get_conversation_dir",
        lambda user_id, conversation_id: conversation_dir,
    )

    assert get_preview_workspace_file_path(7, "conv-1", "assets/intermediate/run-1/image.png") is None


def test_render_html_preview_document_rewrites_code_root_assets(monkeypatch, tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    preview_dir = conversation_dir / "project" / "docx-parser-html"
    preview_dir.mkdir(parents=True, exist_ok=True)
    entry_file = preview_dir / "index.html"
    asset_file = preview_dir / "styles.css"
    asset_file.write_text("body {}", encoding="utf-8")
    entry_file.write_text('<html><head><link rel="stylesheet" href="styles.css"></head></html>', encoding="utf-8")

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.get_conversation_dir",
        lambda user_id, conversation_id: conversation_dir,
    )

    rendered = render_html_preview_document(
        7,
        "conv-1",
        "project/docx-parser-html/index.html",
        preview_url_builder=lambda relative_path: f"/preview/{relative_path}",
    )

    assert '/preview/docx-parser-html/styles.css' in rendered


def test_render_html_preview_document_rewrites_url_encoded_image_paths(monkeypatch, tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    preview_dir = conversation_dir / "project" / "docx-parser-html"
    preview_dir.mkdir(parents=True, exist_ok=True)
    entry_file = preview_dir / "index.html"
    asset_name = "黑格尔与康德哲学理论对比_html_b9dccf20935d3126.png"
    asset_file = preview_dir / asset_name
    asset_file.write_bytes(b"fake-png")
    entry_file.write_text(
        '<html><body><img src="%E9%BB%91%E6%A0%BC%E5%B0%94%E4%B8%8E%E5%BA%B7%E5%BE%B7%E5%93%B2%E5%AD%A6%E7%90%86%E8%AE%BA%E5%AF%B9%E6%AF%94_html_b9dccf20935d3126.png"></body></html>',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.get_conversation_dir",
        lambda user_id, conversation_id: conversation_dir,
    )

    rendered = render_html_preview_document(
        7,
        "conv-1",
        "project/docx-parser-html/index.html",
        preview_url_builder=lambda relative_path: f"/preview/{relative_path}",
    )

    assert f'/preview/docx-parser-html/{asset_name}' in rendered


def test_get_workspace_file_path_rejects_prefix_sibling_escape(monkeypatch, tmp_path: Path):
    conversation_dir = tmp_path / "users" / "7" / "conversations" / "conv"
    escaped = conversation_dir.parent / "conv_evil" / "secret.txt"
    escaped.parent.mkdir(parents=True)
    escaped.write_text("secret", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.get_conversation_dir",
        lambda user_id, conversation_id: conversation_dir,
    )

    assert get_workspace_file_path(7, "conv", "published/../../conv_evil/secret.txt") is None


def test_create_html_bundle_uses_service_conversation_dir_override(monkeypatch, tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    html_dir = conversation_dir / "published" / "f_site" / "v0001"
    html_dir.mkdir(parents=True, exist_ok=True)
    (html_dir / "index.html").write_text("<html><body>ok</body></html>", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.get_conversation_dir",
        lambda user_id, conversation_id: conversation_dir,
    )

    bundle_path = create_html_bundle(7, "conv-1", "published/f_site/v0001/index.html")

    assert bundle_path.exists()


def test_render_css_preview_document_uses_service_conversation_dir_override(monkeypatch, tmp_path: Path):
    conversation_dir = tmp_path / "conversation"
    css_dir = conversation_dir / "project" / "docx-parser-html"
    css_dir.mkdir(parents=True, exist_ok=True)
    (css_dir / "bg.png").write_bytes(b"png")
    (css_dir / "styles.css").write_text("body{background:url('./bg.png')}", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_service.get_conversation_dir",
        lambda user_id, conversation_id: conversation_dir,
    )

    rendered = render_css_preview_document(
        7,
        "conv-1",
        "project/docx-parser-html/styles.css",
        preview_url_builder=lambda relative_path: f"/preview/{relative_path}",
    )

    assert '/preview/docx-parser-html/bg.png' in rendered
