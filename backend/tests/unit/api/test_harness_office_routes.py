from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import harness as harness_endpoint
from app.schemas.harness import (
    CloseWorkspaceOfficeSessionRequest,
    OpenWorkspaceOfficeSessionRequest,
    OpenWorkspaceOfficeSessionRead,
)


def test_harness_router_exposes_office_session_endpoints():
    routes = {
        (",".join(sorted(route.methods or [])), route.path)
        for route in harness_endpoint.router.routes
    }

    assert ("POST", "/agent/harness/conversations/{conversation_id}/office/open") in routes
    assert ("POST", "/agent/harness/conversations/{conversation_id}/office/close") in routes
    assert (
        "GET",
        "/agent/harness/conversations/{conversation_id}/preview-file-version/{file_id}/{version_id}",
    ) in routes
    assert (
        "GET",
        "/agent/harness/conversations/{conversation_id}/preview-file-version/{file_id}/{version_id}/{download_name}",
    ) in routes
    assert ("GET", "/agent/harness/wps-addin/jsplugins.xml") in routes
    assert ("GET", "/agent/harness/wps-addin/{addon_name}/{asset_path:path}") in routes


@pytest.mark.asyncio
async def test_wps_addin_manifest_uses_absolute_asset_urls():
    request = SimpleNamespace(base_url="http://testserver/")

    response = await harness_endpoint.get_wps_addin_manifest(request)
    body = response.body.decode("utf-8")

    assert response.media_type == "application/xml"
    assert 'name="WpsOAAssist" type="wps" url="http://testserver/api/v1/agent/harness/wps-addin/WpsOAAssist/" version="1.0.3"' in body
    assert 'name="EtOAAssist" type="et" url="http://testserver/api/v1/agent/harness/wps-addin/EtOAAssist/" version="1.0.3"' in body
    assert 'name="WppOAAssist" type="wpp" url="http://testserver/api/v1/agent/harness/wps-addin/WppOAAssist/" version="1.0.3"' in body


@pytest.mark.asyncio
async def test_wps_addin_assets_include_minimal_dispatcher():
    response = await harness_endpoint.get_wps_addin_asset("WpsOAAssist", "js/dispatcher.js")
    body = response.body.decode("utf-8")

    assert response.media_type == "application/javascript"
    assert "function dispatcher" in body
    assert "Array.isArray" not in body

    response = await harness_endpoint.get_wps_addin_asset("WpsOAAssist", "js/handler.js")
    body = response.body.decode("utf-8")

    assert "downloadFile" in body
    assert "Documents.Open" in body
    assert "Workbooks.Open" in body
    assert "Presentations.Open" in body


@pytest.mark.asyncio
async def test_wps_addin_assets_pin_current_addin_name():
    response = await harness_endpoint.get_wps_addin_asset("EtOAAssist", "js/index.js")
    body = response.body.decode("utf-8")

    assert 'var aiCodeWpsAddinVersion = "1.0.3";' in body
    assert 'src="js/dispatcher.js?v=' in body
    assert 'src="js/handler.js?v=' in body
    assert "__AICODE_WPS_ADDIN_VERSION__" not in body


@pytest.mark.asyncio
async def test_wps_addin_rejects_unknown_assets():
    with pytest.raises(HTTPException) as exc:
        await harness_endpoint.get_wps_addin_asset("Unknown", "index.js")

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_open_workspace_office_session_delegates_to_service(monkeypatch):
    user = SimpleNamespace(id=7)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.open_workspace_office_session",
        lambda user_id, conversation_id, file_path: {
            "session_id": "office-1",
            "file_path": file_path,
            "file_kind": "doc",
            "engine": "html",
            "preview_file_path": "code/docx-parser-html/index.html",
            "readonly": True,
        },
    )

    response = await harness_endpoint.open_workspace_office_session(
        conversation_id="conv-1",
        data=OpenWorkspaceOfficeSessionRequest(file_path="spec.docx"),
        user=user,
    )
    parsed = OpenWorkspaceOfficeSessionRead.model_validate(response)

    assert parsed.session_id == "office-1"
    assert parsed.file_path == "spec.docx"
    assert parsed.file_kind == "doc"
    assert parsed.engine == "html"
    assert parsed.preview_file_path == "code/docx-parser-html/index.html"
    assert parsed.snapshot is None


@pytest.mark.asyncio
async def test_open_workspace_office_session_supports_sheet_snapshot_contract(monkeypatch):
    user = SimpleNamespace(id=7)
    snapshot = {
        "kind": "sheet",
        "sheets": [
            {
                "id": "sheet-1",
                "name": "Budget 2026",
                "rows": {"0": {"h": 24}, "1": {"h": 28}},
                "cols": {"0": {"w": 120}, "1": {"w": 160}},
                "cells": {
                    "0:0": {"v": "Item", "t": "s"},
                    "0:1": {"v": "Amount", "t": "s"},
                    "1:0": {"v": "Tea", "t": "s"},
                    "1:1": {"v": 18, "t": "n", "styleId": "currency", "numFmt": "$#,##0.00"},
                },
                "merges": [{"startRow": 0, "startCol": 0, "endRow": 0, "endCol": 1}],
                "freeze": {"rowSplit": 1, "colSplit": 0},
            }
        ],
    }
    capabilities = {
        "can_edit": True,
        "can_save": True,
        "supports_styles": True,
        "supports_merges": True,
        "supports_freeze": True,
    }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.open_workspace_office_session",
        lambda user_id, conversation_id, file_path: {
            "session_id": "office-sheet-1",
            "file_path": file_path,
            "file_kind": "sheet",
            "engine": "univer",
            "unit_id": "unit-sheet-1",
            "snapshot": snapshot,
            "source_blob": "UEsDBBQAAAAIA",
            "source_mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "source_encoding": "base64",
            "warnings": ["Workbook formulas are preserved but not recalculated in preview."],
            "capabilities": capabilities,
            "readonly": False,
        },
    )

    response = await harness_endpoint.open_workspace_office_session(
        conversation_id="conv-1",
        data=OpenWorkspaceOfficeSessionRequest(file_path="budget.xlsx"),
        user=user,
    )
    parsed = OpenWorkspaceOfficeSessionRead.model_validate(response)

    assert parsed.file_kind == "sheet"
    assert parsed.snapshot is not None
    assert parsed.snapshot.model_dump(exclude_none=True) == snapshot
    assert parsed.source_blob == "UEsDBBQAAAAIA"
    assert (
        parsed.source_mime_type
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert parsed.source_encoding == "base64"
    assert parsed.warnings == ["Workbook formulas are preserved but not recalculated in preview."]
    assert parsed.capabilities == capabilities


@pytest.mark.asyncio
async def test_close_workspace_office_session_delegates_to_service(monkeypatch):
    user = SimpleNamespace(id=7)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.close_workspace_office_session",
        lambda user_id, conversation_id, session_id: {
            "session_id": session_id,
            "closed": True,
        },
    )

    response = await harness_endpoint.close_workspace_office_session(
        conversation_id="conv-1",
        data=CloseWorkspaceOfficeSessionRequest(session_id="office-3"),
        user=user,
    )

    assert response["session_id"] == "office-3"
    assert response["closed"] is True


@pytest.mark.asyncio
async def test_preview_workspace_file_version_uses_preview_token_without_current_user(monkeypatch, tmp_path):
    version_path = tmp_path / "budget.xlsx"
    version_path.write_bytes(b"excel")

    monkeypatch.setattr(
        harness_endpoint,
        "_validate_harness_preview_token",
        lambda preview_token, conversation_id: 7,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.generated_content.file_version_store.get_versioned_file",
        lambda user_id, conversation_id, file_id: SimpleNamespace(name="budget.xlsx"),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.generated_content.file_version_store.resolve_version_path",
        lambda user_id, conversation_id, file_id, version_id: version_path,
    )

    response = await harness_endpoint.preview_workspace_file_version(
        conversation_id="conv-1",
        file_id="file-1",
        version_id="v2",
        download_name=None,
        preview_token="preview-token",
    )

    assert response.path == version_path
    assert response.filename == "budget.xlsx"


@pytest.mark.asyncio
async def test_preview_workspace_file_version_accepts_download_name_suffix(monkeypatch, tmp_path):
    version_path = tmp_path / "stored-version"
    version_path.write_bytes(b"excel")

    monkeypatch.setattr(
        harness_endpoint,
        "_validate_harness_preview_token",
        lambda preview_token, conversation_id: 7,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.generated_content.file_version_store.get_versioned_file",
        lambda user_id, conversation_id, file_id: SimpleNamespace(name="budget.xlsx"),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.generated_content.file_version_store.resolve_version_path",
        lambda user_id, conversation_id, file_id, version_id: version_path,
    )

    response = await harness_endpoint.preview_workspace_file_version(
        conversation_id="conv-1",
        file_id="file-1",
        version_id="v2",
        download_name="budget.xlsx",
        preview_token="preview-token",
    )

    assert response.path == version_path
    assert response.filename == "budget.xlsx"


@pytest.mark.asyncio
async def test_preview_workspace_file_uses_thumbnail_when_width_requested(monkeypatch, tmp_path):
    source_path = tmp_path / "source.png"
    thumb_path = tmp_path / "thumb.png"
    source_path.write_bytes(b"source")
    thumb_path.write_bytes(b"thumb")

    monkeypatch.setattr(
        harness_endpoint,
        "_validate_harness_preview_token",
        lambda preview_token, conversation_id: 7,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.workspace_preview_service.get_preview_workspace_file_path",
        lambda user_id, conversation_id, file_path: (source_path, tmp_path),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.workspace_preview_service.resolve_workspace_image_thumbnail",
        lambda resolved, cache_root, width: thumb_path if width == 512 else None,
    )

    response = await harness_endpoint.preview_workspace_file(
        conversation_id="conv-1",
        file_path="references/generated/image/original.png",
        preview_token="preview-token",
        w=512,
    )

    assert response.path == thumb_path
    assert response.media_type == "image/png"


@pytest.mark.asyncio
async def test_preview_workspace_file_without_width_returns_original(monkeypatch, tmp_path):
    source_path = tmp_path / "source.txt"
    source_path.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(
        harness_endpoint,
        "_validate_harness_preview_token",
        lambda preview_token, conversation_id: 7,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.workspace_preview_service.get_preview_workspace_file_path",
        lambda user_id, conversation_id, file_path: (source_path, tmp_path),
    )

    response = await harness_endpoint.preview_workspace_file(
        conversation_id="conv-1",
        file_path="project/source.txt",
        preview_token="preview-token",
        w=None,
    )

    assert response.path == source_path
    assert response.filename == "source.txt"
