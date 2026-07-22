import base64
from pathlib import Path
from zipfile import ZipFile

import pytest
from docx import Document
from openpyxl.chart import BarChart, Reference
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation

from app.schemas.harness import OpenWorkspaceOfficeSessionRead
from app.services.agent_harness.workspace.conversation import office_session_service
from app.services.agent_harness.workspace.conversation.office_session_service import (
    _build_presentation_svg_preview_html,
    cleanup_expired_workspace_office_sessions,
    _polish_sheet_html_preview,
    _sanitize_presentation_svg_for_static_preview,
    close_workspace_office_session,
    open_workspace_office_session,
)


@pytest.fixture(autouse=True)
def stub_docx_html_preview(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_conversation_dir",
        lambda user_id, conversation_id: tmp_path / "conversation",
    )

    def fake_soffice_run(*args, **kwargs):
        command = list(args[0])
        if "--outdir" not in command:
            return None
        outdir = Path(command[command.index("--outdir") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        input_path = Path(command[-1])
        (outdir / f"{input_path.stem}.html").write_text("<html><body>Preview</body></html>", encoding="utf-8")
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.subprocess.run",
        fake_soffice_run,
    )


def test_open_workspace_office_session_creates_doc_session_with_snapshot(monkeypatch, tmp_path: Path):
    conversation_file = tmp_path / "spec.docx"
    document = Document()
    document.add_paragraph("Project Brief")
    document.add_paragraph("Second paragraph")
    document.save(conversation_file)
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_workspace_file_path",
        lambda user_id, conversation_id, file_path: conversation_file,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_conversation_dir",
        lambda user_id, conversation_id: tmp_path / "conversation",
    )
    def fake_soffice_run(*args, **kwargs):
        command = list(args[0])
        outdir = Path(command[command.index("--outdir") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "spec.html").write_text("<html><body>Preview</body></html>", encoding="utf-8")
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.subprocess.run",
        fake_soffice_run,
    )

    result = open_workspace_office_session(7, "conv-1", "spec.docx")

    assert result["file_path"] == "spec.docx"
    assert result["file_kind"] == "doc"
    assert result["engine"] == "html"
    assert result["readonly"] is True
    assert result["session_id"]
    assert result["preview_file_path"].startswith(".agent/preview_cache/docx-parser-html/")
    assert result["preview_file_path"].endswith("/index.html")
    preview_dir = tmp_path / "conversation" / Path(result["preview_file_path"]).parent
    assert (preview_dir / "index.html").read_text(encoding="utf-8") == "<html><body>Preview</body></html>"
    assert "snapshot" not in result


def test_open_workspace_office_session_creates_readonly_presentation_session(monkeypatch, tmp_path: Path):
    conversation_file = tmp_path / "deck.pptx"
    with ZipFile(conversation_file, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", "<slide />")
        archive.writestr("ppt/slides/slide2.xml", "<slide />")

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_workspace_file_path",
        lambda user_id, conversation_id, file_path: conversation_file,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_conversation_dir",
        lambda user_id, conversation_id: tmp_path / "conversation",
    )

    def fake_soffice_run(*args, **kwargs):
        command = list(args[0])
        outdir = Path(command[command.index("--outdir") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        convert_to = command[command.index("--convert-to") + 1]
        if "PageNumber" in convert_to and '"value":"1"' in convert_to:
            (outdir / "deck.svg").write_text("<svg><text>Slide 1</text></svg>", encoding="utf-8")
        elif "PageNumber" in convert_to and '"value":"2"' in convert_to:
            (outdir / "deck.svg").write_text("<svg><text>Slide 2</text></svg>", encoding="utf-8")
        else:
            raise AssertionError(f"Unexpected convert-to payload: {convert_to}")
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.subprocess.run",
        fake_soffice_run,
    )

    result = open_workspace_office_session(7, "conv-1", "deck.pptx")

    assert result["file_kind"] == "presentation"
    assert result["engine"] == "html"
    assert result["readonly"] is True
    assert result["preview_file_path"].startswith(".agent/preview_cache/ppt-parser-html/")
    assert result["preview_file_path"].endswith("/index.html")
    preview_dir = tmp_path / "conversation" / Path(result["preview_file_path"]).parent
    html = (preview_dir / "index.html").read_text(encoding="utf-8")
    assert "<img" not in html
    assert html.count("<svg") == 2
    assert "PPT Preview" in html
    assert "Slide 1" in html
    assert "Slide 2" in html
    assert "deck.pptx" not in html
    assert (preview_dir / "slide-1.svg").read_text(encoding="utf-8") == "<svg><text>Slide 1</text></svg>"
    assert (preview_dir / "slide-2.svg").read_text(encoding="utf-8") == "<svg><text>Slide 2</text></svg>"
    assert "snapshot" not in result


def test_sanitize_presentation_svg_for_static_preview_keeps_requested_slide(tmp_path: Path):
    svg_path = tmp_path / "slide.svg"
    svg_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg">
  <g class="SlideGroup">
    <g visibility="hidden">
      <g id="container-id1">
        <g class="Page">
          <defs class="SlideBackground">
            <g id="bg-id1" class="Background">
              <path fill="rgb(1,2,3)" d="M 0,0 L 10,0 10,10 0,10 Z"/>
            </g>
          </defs>
          <text>Slide 1</text>
        </g>
      </g>
    </g>
    <g visibility="hidden">
      <g id="container-id2">
        <g class="Page">
          <defs class="SlideBackground">
            <g id="bg-id2" class="Background">
              <path fill="rgb(4,5,6)" d="M 0,0 L 10,0 10,10 0,10 Z"/>
            </g>
          </defs>
          <text>Slide 2</text>
        </g>
      </g>
    </g>
  </g>
  <script type="text/ecmascript">console.log("animated");</script>
</svg>
""",
        encoding="utf-8",
    )

    _sanitize_presentation_svg_for_static_preview(svg_path, 2)

    sanitized = svg_path.read_text(encoding="utf-8")
    assert "<script" not in sanitized
    assert 'visibility="hidden"' not in sanitized
    assert 'visibility="visible"' in sanitized
    assert "container-id2" in sanitized
    assert "Slide 2" in sanitized
    assert 'id="bg-id2"' in sanitized
    assert 'fill="rgb(4,5,6)"' in sanitized
    assert "container-id1" not in sanitized
    assert "Slide 1" not in sanitized
    assert 'id="bg-id1"' not in sanitized


def test_build_presentation_svg_preview_html_inlines_svg_content(tmp_path: Path):
    slide_1 = tmp_path / "slide-1.svg"
    slide_2 = tmp_path / "slide-2.svg"
    slide_1.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>Slide 1</text></svg>', encoding="utf-8")
    slide_2.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>Slide 2</text></svg>', encoding="utf-8")

    html = _build_presentation_svg_preview_html("deck.pptx", [slide_1, slide_2])

    assert "<img" not in html
    assert html.count("<svg") == 2
    assert "Slide 1" in html
    assert "Slide 2" in html
    assert "1/2" in html
    assert "2/2" in html
    assert "重新生成第1页" in html
    assert "重新生成第2页" in html
    assert "home_harness_ppt_regenerate_slide" in html
    assert "home_harness_ppt_regenerate_state" in html
    assert "slide-card" not in html
    assert "deck.pptx" not in html


def test_open_workspace_office_session_rejects_unsupported_types(monkeypatch, tmp_path: Path):
    conversation_file = tmp_path / "notes.txt"
    conversation_file.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_workspace_file_path",
        lambda user_id, conversation_id, file_path: conversation_file,
    )

    with pytest.raises(ValueError, match="Unsupported office file type"):
        open_workspace_office_session(7, "conv-1", "notes.txt")


def test_open_workspace_office_session_creates_sheet_snapshot(monkeypatch, tmp_path: Path):
    conversation_file = tmp_path / "budget.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Budget"
    worksheet["A1"] = "Item"
    worksheet["B1"] = "Amount"
    worksheet["A2"] = "Tea"
    worksheet["B2"] = 18
    workbook.save(conversation_file)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_workspace_file_path",
        lambda user_id, conversation_id, file_path: conversation_file,
    )

    session = open_workspace_office_session(7, "conv-1", "budget.xlsx")
    parsed = OpenWorkspaceOfficeSessionRead.model_validate(session)

    assert session["file_kind"] == "sheet"
    assert parsed.file_kind == "sheet"
    assert parsed.snapshot is not None
    assert session["snapshot"]["kind"] == "sheet"
    assert session["snapshot"]["styles"] == {}
    assert session["snapshot"]["sheets"] == [
        {
            "id": "sheet-Budget",
            "name": "Budget",
            "rows": {},
            "cols": {},
            "cells": {
                "0:0": {"v": "Item", "t": "s", "numFmt": "General"},
                "0:1": {"v": "Amount", "t": "s", "numFmt": "General"},
                "1:0": {"v": "Tea", "t": "s", "numFmt": "General"},
                "1:1": {"v": 18, "t": "n", "numFmt": "General"},
            },
            "merges": [],
            "freeze": None,
        }
    ]


def test_open_workspace_office_session_returns_xlsx_source_blob_and_workbook_metadata(monkeypatch, tmp_path: Path):
    conversation_file = tmp_path / "budget.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Budget"
    worksheet["A1"] = "Net"
    worksheet["B1"] = "Tax"
    worksheet["C1"] = "Total"
    worksheet["A2"] = 10
    worksheet["B2"] = 2
    worksheet["C2"] = "=A2+B2"
    workbook.save(conversation_file)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_workspace_file_path",
        lambda user_id, conversation_id, file_path: conversation_file,
    )

    session = open_workspace_office_session(7, "conv-1", "budget.xlsx")

    assert session["source_blob"] == base64.b64encode(conversation_file.read_bytes()).decode("ascii")
    assert (
        session["source_mime_type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert session["source_encoding"] == "base64"
    assert session["warnings"] == ["预览中会保留公式，但不会重新计算结果。"]
    assert session["capabilities"]["can_edit"] is False
    assert session["capabilities"]["can_save"] is False
    assert session["capabilities"]["supports_styles"] is True
    assert session["capabilities"]["supports_merges"] is True
    assert session["capabilities"]["supports_freeze"] is True
    assert session["capabilities"]["detected_unsupported_features"] == []
    assert session["readonly"] is True


def test_open_workspace_office_session_scans_xlsx_for_unsupported_workbook_features(monkeypatch, tmp_path: Path):
    conversation_file = tmp_path / "feature-scan.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Budget"
    worksheet["A1"] = "Amount"
    worksheet["A2"] = 10
    worksheet["A3"] = 25
    worksheet["B2"] = "Needs review"
    worksheet["B2"].comment = Comment("Check this line item", "Reviewer")

    validation = DataValidation(type="list", formula1='"Yes,No"')
    worksheet.add_data_validation(validation)
    validation.add(worksheet["C2"])

    worksheet.conditional_formatting.add(
        "A2:A3",
        CellIsRule(operator="greaterThan", formula=["20"], fill=None),
    )

    chart = BarChart()
    chart.add_data(Reference(worksheet, min_col=1, min_row=1, max_row=3), titles_from_data=True)
    worksheet.add_chart(chart, "E2")

    workbook.save(conversation_file)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_workspace_file_path",
        lambda user_id, conversation_id, file_path: conversation_file,
    )

    session = open_workspace_office_session(7, "conv-1", "feature-scan.xlsx")

    assert "检测到批注，但预览暂不支持显示。" in session["warnings"]
    assert "预览暂不支持条件格式规则。" in session["warnings"]
    assert "预览暂不支持数据验证规则。" in session["warnings"]
    assert "检测到图表、图片或形状，已使用 HTML 预览渲染。" in session["warnings"]
    assert "检测到图表、图片或形状，但预览暂不支持显示。" not in session["warnings"]
    assert session["preview_file_path"].startswith(".agent/preview_cache/xlsx-parser-html/")
    assert session["preview_file_path"].endswith("/index.html")
    preview_dir = tmp_path / "conversation" / Path(session["preview_file_path"]).parent
    preview_html = (preview_dir / "index.html").read_text(encoding="utf-8")
    assert "home-harness-sheet-html-preview" in preview_html
    assert "<body>Preview</body>" in preview_html
    assert session["capabilities"]["supports_comments"] is False
    assert session["capabilities"]["supports_conditional_formatting"] is False
    assert session["capabilities"]["supports_data_validation"] is False
    assert session["capabilities"]["supports_charts"] is False
    assert session["capabilities"]["detected_unsupported_features"] == [
        "comments",
        "conditional_formatting",
        "data_validation",
        "charts",
    ]


def test_polish_sheet_html_preview_injects_spreadsheet_preview_styles(tmp_path: Path):
    preview_html = tmp_path / "index.html"
    preview_html.write_text(
        """<!DOCTYPE html>
<html>
  <head><meta charset="utf-8"><title>Preview</title></head>
  <body>
    <hr>
    <center><h1>Overview</h1><a href="#sheet1">Sheet 1</a></center>
    <hr>
    <h1 id="sheet1">Sheet 1: Budget</h1>
    <table><tr><td>Year</td><td>Amount</td></tr></table>
    <img src="chart.png">
  </body>
</html>
""",
        encoding="utf-8",
    )

    _polish_sheet_html_preview(preview_html)

    html = preview_html.read_text(encoding="utf-8")
    assert "home-harness-sheet-html-preview" in html
    assert "body > center:first-of-type" in html
    assert "border-collapse: collapse" in html
    assert "max-width: min(100%, 1120px)" in html
    assert '<img src="chart.png">' in html
    assert "<td>Year</td>" in html


def test_open_workspace_office_session_scans_xlsx_for_macro_archive_entries(monkeypatch, tmp_path: Path):
    conversation_file = tmp_path / "macro-workbook.xlsx"
    workbook = Workbook()
    workbook.active["A1"] = "Macro test"
    workbook.save(conversation_file)

    with ZipFile(conversation_file, "a") as archive:
        archive.writestr("xl/vbaProject.bin", b"fake-vba-project")

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_workspace_file_path",
        lambda user_id, conversation_id, file_path: conversation_file,
    )

    session = open_workspace_office_session(7, "conv-1", "macro-workbook.xlsx")

    assert "检测到宏/VBA 内容，但预览暂不支持运行或显示。" in session["warnings"]
    assert session["capabilities"]["supports_macros"] is False
    assert "macros" in session["capabilities"]["detected_unsupported_features"]


def test_open_workspace_office_session_returns_csv_source_blob_and_workbook_metadata(monkeypatch, tmp_path: Path):
    conversation_file = tmp_path / "budget.csv"
    conversation_file.write_text("Item,Amount\nTea,18\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_workspace_file_path",
        lambda user_id, conversation_id, file_path: conversation_file,
    )

    session = open_workspace_office_session(7, "conv-1", "budget.csv")
    parsed = OpenWorkspaceOfficeSessionRead.model_validate(session)

    assert session["source_blob"] == base64.b64encode(conversation_file.read_bytes()).decode("ascii")
    assert session["source_mime_type"] == "text/csv"
    assert session["source_encoding"] == "base64"
    assert parsed.snapshot is not None
    assert session["snapshot"] == {
        "kind": "sheet",
        "sheets": [
            {
                "name": "budget",
                "rows": {},
                "cols": {},
                "cells": {
                    "0:0": {"v": "Item", "t": "s"},
                    "0:1": {"v": "Amount", "t": "s"},
                    "1:0": {"v": "Tea", "t": "s"},
                    "1:1": {"v": "18", "t": "s"},
                },
                "merges": [],
                "freeze": None,
            }
        ],
        "styles": {},
    }
    assert session["warnings"] == ["CSV 会以单个工作表打开，且不包含工作簿级能力。"]
    assert session["capabilities"] == {
        "can_edit": False,
        "can_save": False,
        "supports_styles": False,
        "supports_merges": False,
        "supports_freeze": False,
    }

def test_close_workspace_office_session_cleans_up_session(monkeypatch, tmp_path: Path):
    conversation_file = tmp_path / "spec.docx"
    document = Document()
    document.add_paragraph("docx-bytes")
    document.save(conversation_file)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_workspace_file_path",
        lambda user_id, conversation_id, file_path: conversation_file,
    )

    session = open_workspace_office_session(7, "conv-1", "spec.docx")
    closed = close_workspace_office_session(7, "conv-1", session["session_id"])

    assert closed["closed"] is True


def test_close_workspace_office_session_survives_process_local_cache_loss(monkeypatch, tmp_path: Path):
    conversation_file = tmp_path / "spec.docx"
    document = Document()
    document.add_paragraph("docx-bytes")
    document.save(conversation_file)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_workspace_file_path",
        lambda user_id, conversation_id, file_path: conversation_file,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_conversation_dir",
        lambda user_id, conversation_id: tmp_path / "conversation",
    )

    session = open_workspace_office_session(7, "conv-1", "spec.docx")
    office_session_service._OFFICE_SESSIONS.clear()

    closed = close_workspace_office_session(7, "conv-1", session["session_id"])

    assert closed == {
        "session_id": session["session_id"],
        "closed": True,
    }


def test_cleanup_expired_workspace_office_sessions_removes_abandoned_records(monkeypatch, tmp_path: Path):
    conversation_file = tmp_path / "spec.docx"
    document = Document()
    document.add_paragraph("docx-bytes")
    document.save(conversation_file)

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_workspace_file_path",
        lambda user_id, conversation_id, file_path: conversation_file,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.office_session_service.get_conversation_dir",
        lambda user_id, conversation_id: tmp_path / "conversation",
    )

    old_session = open_workspace_office_session(7, "conv-1", "spec.docx")
    current_session = open_workspace_office_session(7, "conv-1", "spec.docx")
    session_dir = tmp_path / "conversation" / ".agent" / "office_sessions"
    old_record_path = session_dir / f"{old_session['session_id']}.json"
    old_record = office_session_service._load_office_session_record(7, "conv-1", old_session["session_id"])
    assert old_record is not None
    old_record["opened_at"] = "2020-01-01T00:00:00+00:00"
    old_record_path.write_text(office_session_service.json.dumps(old_record), encoding="utf-8")

    removed = cleanup_expired_workspace_office_sessions(
        7,
        "conv-1",
        ttl_seconds=60,
        now=office_session_service.datetime.fromisoformat("2020-01-01T00:02:00+00:00"),
    )

    assert removed == 1
    assert not old_record_path.exists()
    assert (session_dir / f"{current_session['session_id']}.json").exists()
    assert old_session["session_id"] not in office_session_service._OFFICE_SESSIONS
