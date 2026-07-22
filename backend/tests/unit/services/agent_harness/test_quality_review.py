from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from app.db.harness_session import harness_sync_session_scope
from app.models.harness_session import HarnessAgentRun, HarnessConversation
from app.services.agent_harness.capabilities.subagents.types import SubagentResult
from app.services.agent_harness.capabilities.tools.capture_artifact_evidence import (
    CaptureArtifactEvidenceInput,
    CaptureArtifactEvidenceTool,
)
from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.runtime.critique.quality_review import (
    QUALITY_REVIEW_DIMENSIONS,
    _build_review_packet,
    _parse_review_output,
    _render_quality_review_prompt,
    ensure_quality_review_authorized,
)
from app.services.agent_harness.runtime.critique.repository import (
    create_run,
    finalize_run,
    insert_round,
    list_rounds,
    update_run_payload,
)


def _active_design_system_context() -> dict:
    tokens_css = """
:root {
  --bg: #FFFFFF;
  --surface: #F8FAFC;
  --fg: #0F172A;
  --muted: #64748B;
  --border: #CBD5E1;
  --accent: #2563EB;
  --font-display: Inter, sans-serif;
  --font-body: Inter, sans-serif;
  --focus-ring: 0 0 0 3px rgba(37, 99, 235, 0.35);
  --text-sm: 0.875rem;
  --radius-sm: 4px;
  --container-md: 960px;
}
""".strip()
    return {
        "kind": "active_design_system_context",
        "id": "test-blue",
        "name": "Test Blue",
        "tokens_css": tokens_css,
    }


def _design_system_html() -> str:
    return """<!doctype html>
<html>
<head>
<style>
:root {
  --bg: #FFFFFF;
  --surface: #F8FAFC;
  --fg: #0F172A;
  --muted: #64748B;
  --border: #CBD5E1;
  --accent: #2563EB;
  --font-display: Inter, sans-serif;
  --font-body: Inter, sans-serif;
  --focus-ring: 0 0 0 3px rgba(37, 99, 235, 0.35);
  --text-sm: 0.875rem;
  --radius-sm: 4px;
  --container-md: 960px;
}
body { background: var(--bg); color: var(--fg); font-family: var(--font-body); }
.cta { background: var(--accent); color: var(--bg); }
</style>
</head>
<body><main><h1>Artifact</h1><button class="cta">Go</button></main></body>
</html>"""


def _ctx(tmp_path: Path, *, run_id: str = "run-quality") -> HarnessContext:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-quality",
        run_id=run_id,
        workspace_root=tmp_path,
        runtime_profile="home",
        artifact_mode="web",
        skill_id="web",
    )
    ctx.ensure_dirs()
    ctx.artifact_work_root = "web-prepared"
    (ctx.project_dir / "web-prepared").mkdir(parents=True, exist_ok=True)
    (ctx.project_dir / "web-prepared" / "index.html").write_text(
        "<!doctype html><html><body><main><h1>Artifact</h1></main></body></html>",
        encoding="utf-8",
    )
    return ctx


def _write_design_system_artifact(ctx: HarnessContext) -> None:
    (ctx.project_dir / "web-prepared" / "index.html").write_text(_design_system_html(), encoding="utf-8")


def _manifest() -> dict:
    return {
        "version": 1,
        "kind": "web",
        "entry": "web-prepared/index.html",
        "title": "Artifact",
        "renderer": "html",
        "exports": ["html"],
        "status": "complete",
        "supporting_files": [],
        "validation": {"status": "passed", "details": {"kind": "html_bundle"}},
    }


def _agent_run(ctx: HarnessContext) -> None:
    with harness_sync_session_scope() as session:
        session.merge(
            HarnessConversation(
                conversation_id=ctx.conversation_id,
                user_id=ctx.user_id,
                title="Quality review",
                runtime_profile=ctx.runtime_profile,
                skill_id=ctx.skill_id,
                artifact_mode=ctx.artifact_mode,
                status="active",
                runtime_status="running",
            )
        )
        session.add(
            HarnessAgentRun(
                run_id=ctx.run_id,
                user_id=ctx.user_id,
                conversation_id=ctx.conversation_id,
                kind="message",
                status="running",
                input_json={},
                runtime_snapshot_json={"phase": "model_turn"},
                idempotency_key=ctx.run_id,
            )
        )


class _Cfg:
    score_scale = 10
    score_threshold = 8.0
    max_rounds = 2
    fallback_policy = "ship_best"


class _EventGateway:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def append_event(self, spec):
        self.events.append(spec)
        return {"event_type": spec.event_type, "payload": spec.payload}


def _role(role: str, score: float, *, must_fix: list[str] | None = None) -> dict:
    dimension_name = next(item["key"] for item in QUALITY_REVIEW_DIMENSIONS if item["role"] == role)
    return {
        "score": score,
        "summary": f"{role} summary",
        "must_fix": list(must_fix or []),
        "dimensions": [
            {
                "role": role,
                "name": dimension_name,
                "score": score,
                "note": f"{role} note",
            }
        ],
    }


def _review_json(*, review_id: str, must_fix: list[str] | None = None, score: float = 9.0) -> str:
    payload = {
        "review_id": review_id,
        "artifact_entry": "web-prepared/index.html",
        "designer_notes": "Reviewed source and controlled evidence.",
        "critic": _role("critic", score, must_fix=must_fix),
        "brand": _role("brand", score),
        "a11y": _role("a11y", score),
        "copy": _role("copy", score),
        "must_fix": list(must_fix or []),
        "repair_instruction": "Fix the blocking issues, then publish again." if must_fix else "",
        "evidence": [{"kind": "source", "path": "web-prepared/index.html", "note": "Read the active entry."}],
        "warnings": [],
    }
    return json.dumps(payload)


def test_quality_review_packet_contains_frozen_artifact_context(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    packet = _build_review_packet(
        ctx,
        cfg=_Cfg(),
        manifest=_manifest(),
        manifest_entry="web-prepared/index.html",
        artifact_work_root="web-prepared",
        artifact_fingerprint="fingerprint-1",
    )

    assert packet["review_id"].startswith("critique-")
    assert packet["artifact"]["manifest"]["entry"] == "web-prepared/index.html"
    assert packet["artifact"]["active_entry"] == "web-prepared/index.html"
    assert packet["artifact"]["artifact_work_root"] == "web-prepared"
    assert packet["artifact"]["fingerprint"] == "fingerprint-1"
    assert packet["rubric"]["weights"] == {"critic": 0.4, "brand": 0.2, "a11y": 0.2, "copy": 0.2}
    assert [item["key"] for item in packet["rubric"]["fixed_dimensions"]] == [item["key"] for item in QUALITY_REVIEW_DIMENSIONS]
    assert len(packet["rubric"]["fixed_dimensions"]) == 15
    assert packet["evidence_request"]["tool"] == "capture_artifact_evidence"
    assert "critic|brand|a11y|copy" in packet["output_schema"]
    assert packet["response_language"] == "zh"


def test_quality_review_prompt_requires_response_language(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    ctx.language = "en"
    packet = _build_review_packet(
        ctx,
        cfg=_Cfg(),
        manifest=_manifest(),
        manifest_entry="web-prepared/index.html",
        artifact_work_root="web-prepared",
        artifact_fingerprint="fingerprint-1",
    )

    prompt = _render_quality_review_prompt(packet)

    assert "response_language='en'" in prompt
    assert "must_fix" in prompt
    assert "repair_instruction" in prompt
    assert "Keep JSON field names in English" in prompt
    assert "rubric.fixed_dimensions" in prompt
    assert "Do not invent, rename" in prompt


@pytest.mark.asyncio
async def test_capture_artifact_evidence_validates_packet_entry_and_writes_sidechain_only(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    review_id = "critique-test"
    ctx.quality_review_packet = {
        "review_id": review_id,
        "artifact": {"active_entry": "web-prepared/index.html"},
    }
    tool = CaptureArtifactEvidenceTool()

    mismatch = tool.validate_input(
        CaptureArtifactEvidenceInput(review_id=review_id, entry="web-prepared/other.html", viewport="desktop"),
        ctx,
    )
    assert mismatch is not None

    result = await tool.execute(
        CaptureArtifactEvidenceInput(review_id=review_id, entry="web-prepared/index.html", viewport="mobile"),
        ctx,
    )

    payload = json.loads(result.output)
    evidence_path = ctx.conversation_dir / payload["evidence_ref"]
    assert result.is_error is False
    assert evidence_path.is_file()
    assert evidence_path.relative_to(ctx.conversation_dir)
    assert "critique/critique-test/evidence" in payload["evidence_ref"]
    assert payload["screenshot_ref"] is None
    assert payload["warnings"][0]["code"] == "screenshot_unavailable"
    assert not (ctx.project_dir / "web-prepared" / "evidence.jsonl").exists()


@pytest.mark.asyncio
async def test_capture_artifact_evidence_returns_mocked_screenshot_ref(tmp_path: Path, monkeypatch) -> None:
    from app.services.agent_harness.runtime.critique.evidence_renderer import ScreenshotEvidence

    ctx = _ctx(tmp_path)
    review_id = "critique-shot"
    ctx.quality_review_packet = {
        "review_id": review_id,
        "artifact": {"active_entry": "web-prepared/index.html"},
    }

    async def fake_capture(*, ctx, entry, viewport, evidence_dir):
        screenshot_path = evidence_dir / f"{viewport}.png"
        screenshot_path.write_bytes(b"png")
        return ScreenshotEvidence(
            screenshot_ref=screenshot_path.relative_to(ctx.conversation_dir).as_posix(),
        )

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.capture_artifact_evidence.capture_artifact_screenshot",
        fake_capture,
    )

    result = await CaptureArtifactEvidenceTool().execute(
        CaptureArtifactEvidenceInput(review_id=review_id, entry="web-prepared/index.html", viewport="desktop"),
        ctx,
    )

    payload = json.loads(result.output)
    assert result.is_error is False
    assert payload["screenshot_ref"].endswith("/desktop.png")
    assert (ctx.conversation_dir / payload["screenshot_ref"]).is_file()
    assert payload["warnings"] == []


@pytest.mark.asyncio
async def test_capture_artifact_evidence_reports_screenshot_palette_drift(tmp_path: Path, monkeypatch) -> None:
    from app.services.agent_harness.runtime.critique.evidence_renderer import ScreenshotEvidence

    ctx = _ctx(tmp_path)
    _write_design_system_artifact(ctx)
    review_id = "critique-drift"
    ctx.quality_review_packet = {
        "review_id": review_id,
        "artifact": {
            "active_entry": "web-prepared/index.html",
            "active_design_system_context": _active_design_system_context(),
        },
    }

    async def fake_capture(*, ctx, entry, viewport, evidence_dir):
        screenshot_path = evidence_dir / f"{viewport}.png"
        Image.new("RGB", (64, 64), "#FF00FF").save(screenshot_path)
        return ScreenshotEvidence(
            screenshot_ref=screenshot_path.relative_to(ctx.conversation_dir).as_posix(),
        )

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.capture_artifact_evidence.capture_artifact_screenshot",
        fake_capture,
    )

    result = await CaptureArtifactEvidenceTool().execute(
        CaptureArtifactEvidenceInput(review_id=review_id, entry="web-prepared/index.html", viewport="desktop"),
        ctx,
    )

    payload = json.loads(result.output)
    compliance = payload["design_system_compliance"]
    assert result.is_error is False
    assert compliance["blocks_publish"] is True
    assert compliance["p0_count"] == 1
    assert compliance["findings"][0]["id"] == "design-system-screenshot-palette-drift"


def test_quality_review_output_rejects_malformed_scores_and_missing_dimensions() -> None:
    packet = {
        "review_id": "critique-1",
        "artifact": {"active_entry": "web-prepared/index.html"},
    }
    valid = json.loads(_review_json(review_id="critique-1"))
    valid["critic"]["score"] = 11
    with pytest.raises(ValueError, match="critic score out of range"):
        _parse_review_output(json.dumps(valid), packet=packet, cfg=_Cfg())

    valid = json.loads(_review_json(review_id="critique-1"))
    valid["brand"]["dimensions"] = []
    with pytest.raises(ValueError, match="brand dimensions are required"):
        _parse_review_output(json.dumps(valid), packet=packet, cfg=_Cfg())

    valid = json.loads(_review_json(review_id="critique-1"))
    valid["critic"]["dimensions"][0]["name"] = "made-up-dimension"
    with pytest.raises(ValueError, match="dimension name is not in fixed rubric"):
        _parse_review_output(json.dumps(valid), packet=packet, cfg=_Cfg())


@pytest.mark.asyncio
async def test_quality_review_pass_recomputes_score_and_finalizes_shipped(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_CRITIQUE_ENABLED", True)
    ctx = _ctx(tmp_path, run_id="run-quality-pass")
    gateway = _EventGateway()
    ctx.runtime_gateway = gateway  # type: ignore[assignment]
    _agent_run(ctx)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.critique.quality_review.read_artifact_manifest",
        lambda *_args, **_kwargs: _manifest(),
    )

    async def handler(request, parent_ctx):
        assert request.subagent_type == "QualityReview"
        packet = parent_ctx.quality_review_packet
        return SubagentResult(
            task_id=request.task_id,
            status="completed",
            summary="review complete",
            result={"assistant_text": _review_json(review_id=packet["review_id"], score=9.0)},
        )

    ctx.run_subagent_handler = handler

    failure = await ensure_quality_review_authorized(ctx=ctx, manifest_entry="web-prepared/index.html")

    assert failure is None
    with harness_sync_session_scope() as session:
        row = session.query(HarnessAgentRun).filter_by(run_id=ctx.run_id).one()
        critique = row.runtime_snapshot_json["critique"]
    assert critique["status"] == "shipped"
    assert critique["score"] == 9.0
    assert critique["selected_round"] == 1
    assert critique["artifact_fingerprint"]
    assert critique["packet_hash"]
    assert critique["subagent_task_id"].startswith("quality-review-")
    shipped_event = next(event for event in gateway.events if getattr(event, "event_type", "") == "critique.shipped")
    assert shipped_event.payload["subagent_task_id"] == critique["subagent_task_id"]


@pytest.mark.asyncio
async def test_quality_review_must_fix_returns_repair_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_CRITIQUE_ENABLED", True)
    ctx = _ctx(tmp_path, run_id="run-quality-fix")
    _agent_run(ctx)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.critique.quality_review.read_artifact_manifest",
        lambda *_args, **_kwargs: _manifest(),
    )

    async def handler(request, parent_ctx):
        packet = parent_ctx.quality_review_packet
        return SubagentResult(
            task_id=request.task_id,
            status="completed",
            summary="review complete",
            result={"assistant_text": _review_json(review_id=packet["review_id"], must_fix=["a11y contrast must improve"], score=7.0)},
        )

    ctx.run_subagent_handler = handler

    failure = await ensure_quality_review_authorized(ctx=ctx, manifest_entry="web-prepared/index.html")

    assert failure is not None
    assert failure.reason_code == "critique_not_authorized"
    assert failure.metadata["repair_instruction"] == "Fix the blocking issues, then publish again."
    assert failure.metadata["must_fix"] == ["a11y contrast must improve"]
    with harness_sync_session_scope() as session:
        row = session.query(HarnessAgentRun).filter_by(run_id=ctx.run_id).one()
        critique = row.runtime_snapshot_json["critique"]
    assert critique["status"] == "running"
    assert critique["must_fix_count"] == 1
    assert critique["composite"] == 7.0


@pytest.mark.asyncio
async def test_quality_review_does_not_reopen_after_max_rounds(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_CRITIQUE_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.HARNESS_CRITIQUE_MAX_ROUNDS", 2)
    ctx = _ctx(tmp_path, run_id="run-quality-maxed")
    _agent_run(ctx)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.critique.quality_review.read_artifact_manifest",
        lambda *_args, **_kwargs: _manifest(),
    )
    with harness_sync_session_scope() as session:
        create_run(
            session,
            critique_run_id="critique-maxed",
            harness_run_id=ctx.run_id,
            conversation_id=ctx.conversation_id,
            user_id=ctx.user_id,
            artifact_mode=ctx.artifact_mode,
            artifact_work_root="web-prepared",
            max_rounds=2,
        )
        insert_round(
            session,
            critique_run_id="critique-maxed",
            round_number=1,
            active_entry="web-prepared/index.html",
            snapshot_relpath="critique/critique-maxed/round-1",
            composite=7.0,
            must_fix_count=1,
            findings=[],
        )
        insert_round(
            session,
            critique_run_id="critique-maxed",
            round_number=2,
            active_entry="web-prepared/index.html",
            snapshot_relpath="critique/critique-maxed/round-2",
            composite=7.5,
            must_fix_count=1,
            findings=[],
        )
        assert finalize_run(
            session,
            critique_run_id="critique-maxed",
            status="below_threshold",
            best_round=2,
            score=7.5,
            selected_snapshot_relpath="critique/critique-maxed/round-2",
        )
        update_run_payload(
            session,
            critique_run_id="critique-maxed",
            values={"artifact_fingerprint": "previous-fingerprint"},
        )

    async def handler(_request, _parent_ctx):
        pytest.fail("quality review subagent should not run after max rounds")

    ctx.run_subagent_handler = handler
    (ctx.project_dir / "web-prepared" / "index.html").write_text(
        "<!doctype html><html><body><main><h1>Changed after max rounds</h1></main></body></html>",
        encoding="utf-8",
    )

    failure = await ensure_quality_review_authorized(ctx=ctx, manifest_entry="web-prepared/index.html")

    assert failure is None
    with harness_sync_session_scope() as session:
        row = session.query(HarnessAgentRun).filter_by(run_id=ctx.run_id).one()
        critique = row.runtime_snapshot_json["critique"]
        rounds = list_rounds(session, "critique-maxed")
    assert critique["status"] == "below_threshold"
    assert critique["best_round"] == 2
    assert len(rounds) == 2


@pytest.mark.asyncio
async def test_quality_review_evidence_design_system_p0_blocks_publish(tmp_path: Path, monkeypatch) -> None:
    from app.services.agent_harness.runtime.critique.evidence_renderer import ScreenshotEvidence

    monkeypatch.setattr("app.core.config.settings.HARNESS_CRITIQUE_ENABLED", True)
    ctx = _ctx(tmp_path, run_id="run-quality-design-system-p0")
    _write_design_system_artifact(ctx)
    _agent_run(ctx)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.critique.quality_review.read_artifact_manifest",
        lambda *_args, **_kwargs: _manifest(),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.critique.quality_review.read_runtime_state_payload",
        lambda *_args, **_kwargs: {
            "runtime_state": {
                "runtime_contract": {
                    "active_design_system_context": _active_design_system_context(),
                },
            },
        },
    )

    async def fake_capture(*, ctx, entry, viewport, evidence_dir):
        screenshot_path = evidence_dir / f"{viewport}.png"
        Image.new("RGB", (64, 64), "#FF00FF").save(screenshot_path)
        return ScreenshotEvidence(
            screenshot_ref=screenshot_path.relative_to(ctx.conversation_dir).as_posix(),
        )

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.capture_artifact_evidence.capture_artifact_screenshot",
        fake_capture,
    )

    async def handler(request, parent_ctx):
        packet = parent_ctx.quality_review_packet
        evidence = await CaptureArtifactEvidenceTool().execute(
            CaptureArtifactEvidenceInput(
                review_id=packet["review_id"],
                entry="web-prepared/index.html",
                viewport="desktop",
            ),
            parent_ctx,
        )
        assert json.loads(evidence.output)["design_system_compliance"]["p0_count"] == 1
        return SubagentResult(
            task_id=request.task_id,
            status="completed",
            summary="review complete",
            result={"assistant_text": _review_json(review_id=packet["review_id"], score=9.5)},
        )

    ctx.run_subagent_handler = handler

    failure = await ensure_quality_review_authorized(ctx=ctx, manifest_entry="web-prepared/index.html")

    assert failure is not None
    assert failure.reason_code == "critique_not_authorized"
    assert "Rendered screenshot colors visibly drift" in failure.metadata["must_fix"][0]
    with harness_sync_session_scope() as session:
        row = session.query(HarnessAgentRun).filter_by(run_id=ctx.run_id).one()
        critique = row.runtime_snapshot_json["critique"]
    assert critique["must_fix_count"] == 1
    assert critique["status"] == "running"


@pytest.mark.asyncio
async def test_quality_review_invalid_subagent_output_degrades_open(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_CRITIQUE_ENABLED", True)
    ctx = _ctx(tmp_path, run_id="run-quality-invalid")
    _agent_run(ctx)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.critique.quality_review.read_artifact_manifest",
        lambda *_args, **_kwargs: _manifest(),
    )

    async def handler(request, parent_ctx):
        return SubagentResult(
            task_id=request.task_id,
            status="completed",
            summary="bad output",
            result={"assistant_text": "not json"},
        )

    ctx.run_subagent_handler = handler

    failure = await ensure_quality_review_authorized(ctx=ctx, manifest_entry="web-prepared/index.html")

    assert failure is None
    with harness_sync_session_scope() as session:
        row = session.query(HarnessAgentRun).filter_by(run_id=ctx.run_id).one()
        critique = row.runtime_snapshot_json["critique"]
    assert critique["status"] == "degraded"
    assert critique["warnings"][0]["code"] == "quality_review_invalid_output"
