from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services.agent_harness.core.context import HarnessContext
from app.models.harness_session import HarnessAgentRun
from app.services.agent_harness.runtime.critique.publish_guard import (
    CritiquePublishSelection,
    check_critique_publish_guard,
    prepare_critique_publish_selection,
)
from app.services.agent_harness.runtime.critique.repository import create_run, finalize_run, insert_round


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    HarnessAgentRun.metadata.create_all(engine, tables=[HarnessAgentRun.__table__])
    return Session(engine)


def _agent_run(session: Session) -> None:
    session.add(
        HarnessAgentRun(
            run_id="run-1",
            user_id=1,
            conversation_id="conversation-1",
            kind="message",
            status="running",
            input_json={},
            runtime_snapshot_json={},
            idempotency_key="run-1",
        )
    )
    session.flush()


def test_guard_rejects_publish_until_selected_snapshot_is_authorized():
    with _session() as session:
        _agent_run(session)
        create_run(
            session,
            critique_run_id="critique-1",
            harness_run_id="run-1",
            conversation_id="conversation-1",
            user_id=1,
            artifact_mode="html",
            artifact_work_root="web-prepared",
        )
        assert check_critique_publish_guard(
            session, harness_run_id="run-1", manifest_entry="web-prepared/index.html"
        ).reason_code == "critique_in_progress"
        insert_round(
            session,
            critique_run_id="critique-1",
            round_number=1,
            active_entry="web-prepared/index.html",
            snapshot_relpath="critique/critique-1/round-1",
            composite=8.5,
            must_fix_count=0,
            findings=[],
        )
        assert finalize_run(
            session,
            critique_run_id="critique-1",
            status="shipped",
            best_round=1,
            score=8.5,
            selected_snapshot_relpath="critique/critique-1/round-1",
        )

        assert check_critique_publish_guard(
            session, harness_run_id="run-1", manifest_entry="web-prepared/index.html"
        ) is None
        assert check_critique_publish_guard(
            session, harness_run_id="run-1", manifest_entry="web-prepared/other.html"
        ).reason_code == "critique_manifest_mismatch"


def test_guard_allows_quality_failed_publish_without_selected_snapshot():
    with _session() as session:
        _agent_run(session)
        create_run(
            session,
            critique_run_id="critique-1",
            harness_run_id="run-1",
            conversation_id="conversation-1",
            user_id=1,
            artifact_mode="html",
            artifact_work_root="web-prepared",
        )
        assert finalize_run(
            session,
            critique_run_id="critique-1",
            status="failed",
            best_round=None,
            score=None,
            selected_snapshot_relpath=None,
        )

        assert check_critique_publish_guard(
            session, harness_run_id="run-1", manifest_entry="web-prepared/index.html"
        ) is None


def test_guard_allows_degraded_fail_open_publish_without_selected_snapshot():
    with _session() as session:
        _agent_run(session)
        create_run(
            session,
            critique_run_id="critique-1",
            harness_run_id="run-1",
            conversation_id="conversation-1",
            user_id=1,
            artifact_mode="html",
            artifact_work_root="web-prepared",
        )
        assert finalize_run(
            session,
            critique_run_id="critique-1",
            status="degraded",
            best_round=None,
            score=None,
            selected_snapshot_relpath=None,
            reason="quality_review_internal_error",
        )

        assert check_critique_publish_guard(
            session, harness_run_id="run-1", manifest_entry="web-prepared/index.html"
        ) is None


def test_guard_reports_missing_selected_round_before_manifest_mismatch():
    with _session() as session:
        _agent_run(session)
        create_run(
            session,
            critique_run_id="critique-1",
            harness_run_id="run-1",
            conversation_id="conversation-1",
            user_id=1,
            artifact_mode="html",
            artifact_work_root="web-prepared",
        )
        assert finalize_run(
            session,
            critique_run_id="critique-1",
            status="shipped",
            best_round=None,
            score=8.5,
            selected_snapshot_relpath="critique/critique-1/round-1",
        )

        failure = check_critique_publish_guard(
            session, harness_run_id="run-1", manifest_entry="web-prepared/index.html"
        )
        assert failure is not None
        assert failure.reason_code == "critique_selected_round_missing"


def test_guard_reports_missing_round_snapshot_before_manifest_mismatch():
    with _session() as session:
        _agent_run(session)
        create_run(
            session,
            critique_run_id="critique-1",
            harness_run_id="run-1",
            conversation_id="conversation-1",
            user_id=1,
            artifact_mode="html",
            artifact_work_root="web-prepared",
        )
        assert finalize_run(
            session,
            critique_run_id="critique-1",
            status="shipped",
            best_round=2,
            score=8.5,
            selected_snapshot_relpath="critique/critique-1/round-2",
        )

        failure = check_critique_publish_guard(
            session, harness_run_id="run-1", manifest_entry="web-prepared/index.html"
        )
        assert failure is not None
        assert failure.reason_code == "critique_round_snapshot_missing"


def test_guard_allows_artifact_not_critiqueable_fallback_publish():
    with _session() as session:
        _agent_run(session)
        create_run(
            session,
            critique_run_id="critique-1",
            harness_run_id="run-1",
            conversation_id="conversation-1",
            user_id=1,
            artifact_mode="html",
            artifact_work_root="web-prepared",
        )
        assert finalize_run(
            session,
            critique_run_id="critique-1",
            status="failed",
            best_round=None,
            score=None,
            selected_snapshot_relpath=None,
        )

        assert check_critique_publish_guard(
            session, harness_run_id="run-1", manifest_entry="web-prepared/deck.pptx"
        ) is None


def test_prepare_publish_selection_restores_selected_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessConversation

    ctx = HarnessContext(
        user_id=1,
        conversation_id="conversation-1",
        run_id="run-1",
        workspace_root=tmp_path,
        runtime_profile="home",
        artifact_mode="web",
        skill_id="web",
    )
    ctx.ensure_dirs()
    ctx.artifact_work_root = "web-prepared"
    (ctx.project_dir / "web-prepared").mkdir(parents=True, exist_ok=True)
    (ctx.project_dir / "web-prepared" / "index.html").write_text("round 3", encoding="utf-8")
    snapshot = ctx.conversation_dir / "critique" / "critique-1" / "round-2"
    (snapshot / "artifact-work-root").mkdir(parents=True, exist_ok=True)
    (snapshot / "artifact-work-root" / "index.html").write_text("round 2", encoding="utf-8")
    (snapshot / "artifact_manifest.json").write_text(
        '{"entry":"web-prepared/index.html","kind":"web","renderer":"html","exports":["html"]}',
        encoding="utf-8",
    )
    (snapshot / "round.json").write_text(
        '{"artifact_work_root":"web-prepared","active_entry":"web-prepared/index.html"}',
        encoding="utf-8",
    )

    with harness_sync_session_scope() as session:
        session.merge(
            HarnessConversation(
                conversation_id=ctx.conversation_id,
                user_id=ctx.user_id,
                title="Critique publish",
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
                runtime_snapshot_json={},
                idempotency_key=ctx.run_id,
            )
        )
    with harness_sync_session_scope() as session:
        create_run(
            session,
            critique_run_id="critique-1",
            harness_run_id=ctx.run_id,
            conversation_id=ctx.conversation_id,
            user_id=ctx.user_id,
            artifact_mode="web",
            artifact_work_root="web-prepared",
        )
        insert_round(
            session,
            critique_run_id="critique-1",
            round_number=2,
            active_entry="web-prepared/index.html",
            snapshot_relpath="critique/critique-1/round-2",
            composite=8.0,
            must_fix_count=8,
            findings=[],
        )
        assert finalize_run(
            session,
            critique_run_id="critique-1",
            status="below_threshold",
            best_round=2,
            score=8.0,
            selected_snapshot_relpath="critique/critique-1/round-2",
        )

    selection = prepare_critique_publish_selection(ctx, manifest_entry="web-prepared/index.html")

    assert isinstance(selection, CritiquePublishSelection)
    assert selection.restored_snapshot is True
    assert selection.selected_round == 2
    assert (ctx.project_dir / "web-prepared" / "index.html").read_text(encoding="utf-8") == "round 2"
