from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.models.harness_session import HarnessAgentRun
from app.services.agent_harness.runtime.critique.repository import (
    create_run,
    finalize_run,
    get_run,
    insert_round,
    list_rounds,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    HarnessAgentRun.metadata.create_all(engine, tables=[HarnessAgentRun.__table__])
    return Session(engine)


def _agent_run(session: Session) -> HarnessAgentRun:
    row = HarnessAgentRun(
        run_id="run-1",
        user_id=1,
        conversation_id="conversation-1",
        kind="message",
        status="running",
        input_json={},
        runtime_snapshot_json={"phase": "model_turn"},
        idempotency_key="run-1",
    )
    session.add(row)
    session.flush()
    return row


def test_critique_state_reuses_agent_run_runtime_snapshot_json():
    with _session() as session:
        _agent_run(session)

        run = create_run(
            session,
            critique_run_id="critique-1",
            harness_run_id="run-1",
            conversation_id="conversation-1",
            user_id=1,
            artifact_mode="html",
            artifact_work_root="web-prepared",
        )
        session.commit()

        table_names = inspect(session.get_bind()).get_table_names()
        assert "harness_critique_runs" not in table_names
        assert "harness_critique_rounds" not in table_names
        assert run.critique_run_id == "critique-1"
        assert run.status == "running"
        assert get_run(session, "critique-1").artifact_work_root == "web-prepared"
        snapshot = session.get(HarnessAgentRun, 1).runtime_snapshot_json
        assert snapshot["phase"] == "model_turn"
        assert snapshot["critique"]["critique_run_id"] == "critique-1"


def test_insert_round_is_idempotent_for_round_number_in_runtime_snapshot():
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
        session.commit()

        first = insert_round(
            session,
            critique_run_id="critique-1",
            round_number=1,
            active_entry="web-prepared/index.html",
            snapshot_relpath="critique/critique-1/round-1",
            composite=7.5,
            must_fix_count=1,
            findings=[{"role": "execution", "text": "Fix spacing"}],
            warnings=[{"code": "screenshot_unavailable", "message": "No rendered screenshot evidence was provided."}],
        )
        session.commit()
        second = insert_round(
            session,
            critique_run_id="critique-1",
            round_number=1,
            active_entry="web-prepared/index.html",
            snapshot_relpath="critique/critique-1/round-1",
            composite=9.0,
            must_fix_count=0,
            findings=[],
        )

        assert second.round_number == first.round_number
        assert second.composite == 7.5
        rounds = list_rounds(session, "critique-1")
        assert len(rounds) == 1
        assert rounds[0].warnings_json == [
            {"code": "screenshot_unavailable", "message": "No rendered screenshot evidence was provided."}
        ]


def test_insert_round_persists_open_design_style_warning_codes():
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

        insert_round(
            session,
            critique_run_id="critique-1",
            round_number=1,
            active_entry="web-prepared/index.html",
            snapshot_relpath="critique/critique-1/round-1",
            composite=8.0,
            must_fix_count=0,
            findings=[],
            warnings=[
                {"code": "score_clamped", "message": "A critique score exceeded the configured scale and was clamped."},
                {"code": "composite_mismatch", "message": "Agent-reported composite differed from backend scoring."},
                {"code": "unknown_role", "message": "An unknown critique panelist role was ignored."},
            ],
        )

        assert [item["code"] for item in list_rounds(session, "critique-1")[0].warnings_json] == [
            "score_clamped",
            "composite_mismatch",
            "unknown_role",
        ]


def test_rounds_without_warning_field_read_as_empty_list():
    with _session() as session:
        row = _agent_run(session)
        row.runtime_snapshot_json = {
            "critique": {
                "critique_run_id": "critique-1",
                "harness_run_id": "run-1",
                "conversation_id": "conversation-1",
                "user_id": 1,
                "artifact_mode": "html",
                "artifact_work_root": "web-prepared",
                "status": "running",
                "rounds": [
                    {
                        "round_number": 1,
                        "active_entry": "web-prepared/index.html",
                        "snapshot_relpath": "critique/critique-1/round-1",
                        "composite": 7.5,
                        "must_fix_count": 1,
                        "findings": [],
                    }
                ],
            }
        }
        session.flush()

        rounds = list_rounds(session, "critique-1")

        assert rounds[0].warnings_json == []


def test_terminal_run_cannot_return_to_running():
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
        session.commit()
        assert finalize_run(
            session,
            critique_run_id="critique-1",
            status="below_threshold",
            best_round=1,
            score=7.5,
            selected_snapshot_relpath="critique/critique-1/round-1",
        )
        session.commit()

        assert not finalize_run(
            session,
            critique_run_id="critique-1",
            status="running",
            best_round=None,
            score=None,
            selected_snapshot_relpath=None,
        )
        assert get_run(session, "critique-1").status == "below_threshold"
