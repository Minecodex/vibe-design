from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.agent_harness.capabilities.tools.analyze_image import AnalyzeImageParams, AnalyzeImageTool, _workspace_path_to_data_uri


class _FakeAnalyzeImageContext:
    def __init__(self, conversation_dir: Path):
        self.conversation_dir = conversation_dir
        self.code_dir = conversation_dir / "code"

    def resolve_workspace_path(self, relative: str, *, default_scope: str = "code", allow_fallback_to_files: bool = False):
        return self.code_dir / relative


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n-\xb4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def test_analyze_image_resolves_project_prefixed_critique_ref(tmp_path: Path) -> None:
    ctx = _FakeAnalyzeImageContext(tmp_path)
    image_path = tmp_path / "critique" / "review-1" / "evidence" / "desktop-1440x900.png"
    _write_png(image_path)

    plain = _workspace_path_to_data_uri("critique/review-1/evidence/desktop-1440x900.png", ctx)  # type: ignore[arg-type]
    prefixed = _workspace_path_to_data_uri("project/critique/review-1/evidence/desktop-1440x900.png", ctx)  # type: ignore[arg-type]

    assert plain and plain.startswith("data:image/png;base64,")
    assert prefixed == plain


def test_analyze_image_rejects_unsafe_project_prefixed_escape(tmp_path: Path) -> None:
    ctx = _FakeAnalyzeImageContext(tmp_path)
    outside = tmp_path.parent / "outside.png"
    _write_png(outside)

    assert _workspace_path_to_data_uri("project/../outside.png", ctx) is None  # type: ignore[arg-type]
    assert _workspace_path_to_data_uri(str(outside), ctx) is None  # type: ignore[arg-type]


class _FakeStreamingContext:
    user_id = 7
    conversation_id = "conv-1"
    run_id = "run-1"
    parent_usage_log_id = None
    runtime_gateway = object()

    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def get_tool_stream_scope(self) -> dict:
        return {
            "tool_call_id": "call-1",
            "message_key": "message-1",
            "parent_block_key": "media-call-1",
        }

    def run_output_anchor_payload(self) -> dict:
        return {}

    async def emit_tool_stream_event(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))

    def record_billing(self, **_kwargs) -> None:
        return None


class _FakeDbSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return False


class _FakeMultimodalService:
    last_stream_usage: dict = {}
    last_stream_amount_cents = 0

    def __init__(self, _db) -> None:
        pass

    async def chat_stream(self, **_kwargs):
        for char in ("x" * 70):
            yield char


@pytest.mark.asyncio
async def test_analyze_image_stream_delta_flushes_in_batches(monkeypatch) -> None:
    import app.services.agent_harness.capabilities.tools.analyze_image as analyze_image_module

    monkeypatch.setattr(analyze_image_module, "MultimodalService", _FakeMultimodalService)
    monkeypatch.setattr(analyze_image_module, "get_harness_db_session_factory", lambda: _FakeDbSession)
    monkeypatch.setattr(analyze_image_module, "get_default_image_analysis_model", lambda: "GPT-5.5")
    monkeypatch.setattr(analyze_image_module, "get_default_image_analysis_provider", lambda: "ollama")

    ctx = _FakeStreamingContext()
    result = await AnalyzeImageTool().execute(
        AnalyzeImageParams(
            image_url="data:image/png;base64,AA==",
            question="describe",
        ),
        ctx,  # type: ignore[arg-type]
    )

    assert not result.is_error
    assert json.loads(result.output)["analysis"] == "x" * 70

    deltas = [
        event_payload["payload"]["delta"]
        for event_type, event_payload in ctx.events
        if event_type == "presentation.block.delta"
    ]
    assert deltas == ["x" * 70]


@pytest.mark.asyncio
async def test_analyze_image_stream_delta_respects_configured_char_threshold(monkeypatch) -> None:
    import app.services.agent_harness.capabilities.tools.analyze_image as analyze_image_module

    monkeypatch.setattr(analyze_image_module, "MultimodalService", _FakeMultimodalService)
    monkeypatch.setattr(analyze_image_module, "get_harness_db_session_factory", lambda: _FakeDbSession)
    monkeypatch.setattr(analyze_image_module, "get_default_image_analysis_model", lambda: "GPT-5.5")
    monkeypatch.setattr(analyze_image_module, "get_default_image_analysis_provider", lambda: "ollama")
    monkeypatch.setattr(analyze_image_module, "HARNESS_ANALYZE_IMAGE_STREAM_DELTA_FLUSH_CHARS", 64)
    monkeypatch.setattr(analyze_image_module, "HARNESS_ANALYZE_IMAGE_STREAM_DELTA_FLUSH_INTERVAL_SECONDS", 60.0)

    ctx = _FakeStreamingContext()
    result = await AnalyzeImageTool().execute(
        AnalyzeImageParams(
            image_url="data:image/png;base64,AA==",
            question="describe",
        ),
        ctx,  # type: ignore[arg-type]
    )

    assert not result.is_error
    deltas = [
        event_payload["payload"]["delta"]
        for event_type, event_payload in ctx.events
        if event_type == "presentation.block.delta"
    ]
    assert deltas == ["x" * 64, "x" * 6]
