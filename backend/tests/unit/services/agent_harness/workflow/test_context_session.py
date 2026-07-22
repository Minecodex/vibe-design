from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.agent_harness.runtime.model_context import build_model_context
from app.services.agent_harness.workflow.context_session import (
    ContextProjector,
    ContextSessionManager,
    _stable_tool_schemas,
    tool_schemas_for_phase,
    validate_context_session_integrity,
)
from app.services.agent_harness.workflow.gateway import _sync_runtime_contract_into_state
from app.services.agent_harness.workflow.runtime_preparation import prepare_execution_runtime_context


class _Ctx:
    def __init__(self, tmp_path: Path) -> None:
        self.user_id = 7
        self.conversation_id = "conv-1"
        self.run_id = "run-1"
        self.language = "zh"
        self.conversation_dir = tmp_path
        self.skill_dir = tmp_path / "skill"
        self.active_skill_dir = self.skill_dir
        self.skill_runtime_dir = self.skill_dir
        self.work_dir = tmp_path
        self.multimodal_model = "GPT-5.4"

    def ensure_dirs(self) -> None:
        self.skill_dir.mkdir(parents=True, exist_ok=True)


class _Skill:
    id = "xlsx"
    skill_dir = "skills/xlsx"
    system_prompt = "zh skill"
    system_prompt_en = "en skill"
    tools = ["tool_b", "tool_a"]
    disabled_tools: list[str] = []


def _schema_names(schemas: list[dict]) -> set[str]:
    return {str((schema.get("function") or {}).get("name") or schema.get("name") or "") for schema in schemas}


def _fake_partitions(system: str, **extra: object) -> dict[str, object]:
    return {
        "stable_system": system,
        "context_snapshot_blocks": list(extra.get("context_snapshot_blocks") or []),
        "turn_append_blocks": list(extra.get("turn_append_blocks") or []),
        "trace": {},
    }


def test_tool_schemas_for_planning_phase_exclude_execution_tools():
    from app.services.agent_harness.capabilities.tools import create_harness_registry

    registry = create_harness_registry(web_search_enabled=True)
    planning_names = _schema_names(tool_schemas_for_phase(registry, phase="planning", language="zh"))
    execution_names = _schema_names(
        tool_schemas_for_phase(
            registry,
            phase="executing",
            language="zh",
            skill_tool_names=["write_file", "exec_command", "register_artifact", "publish_output"],
        )
    )

    assert "request_plan_approval" in planning_names
    assert "write_file" not in planning_names
    assert "exec_command" not in planning_names
    assert "register_artifact" not in planning_names
    assert "publish_output" not in planning_names
    assert {"write_file", "exec_command", "register_artifact", "publish_output"}.issubset(execution_names)


def test_tool_schemas_for_phase_respects_skill_disabled_tools():
    from app.services.agent_harness.capabilities.tools import create_harness_registry

    registry = create_harness_registry(web_search_enabled=True)
    names = _schema_names(
        tool_schemas_for_phase(
            registry,
            phase="executing",
            language="zh",
            skill_tool_names=["analyze_image", "generate_image", "prepare_ecommerce_generation"],
            disabled_tool_names=["ask_user"],
        )
    )

    assert "ask_user" not in names
    assert {"analyze_image", "generate_image", "prepare_ecommerce_generation"}.issubset(names)


def test_context_session_static_hash_excludes_created_at_and_sorts_tools(monkeypatch, tmp_path):
    prepare_calls = []

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.create_workflow_context",
        lambda **_kwargs: _Ctx(tmp_path),
    )
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.get_skill", lambda _skill_id: _Skill())
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.create_harness_registry", lambda **_kwargs: object())
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.tool_schemas_for_phase",
        lambda *_args, **_kwargs: [
            {"type": "function", "function": {"name": "tool_b"}},
            {"type": "function", "function": {"name": "tool_a"}},
        ],
    )
    monkeypatch.setattr(
        "app.services.agent_harness.authoring.prompt.context_builder.render_main_turn_prompt_partitions",
        lambda **_kwargs: _fake_partitions("stable system"),
    )

    def fake_prepare_execution_runtime_context(**_kwargs):
        prepare_calls.append(1)
        return {
            "runtime_contract": {"active_skill_context": {"source_digest": "digest-1"}},
            "workspace_runtime_session": {"active_entry": "workbook.xlsx"},
            "prepared_workspace": {"artifact_work_root": "project", "entry_file": "workbook.xlsx"},
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.prepare_execution_runtime_context",
        fake_prepare_execution_runtime_context,
    )

    session = ContextSessionManager().build(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        payload={},
        conversation={"id": "conv-1", "skill_id": "xlsx", "artifact_mode": "document"},
    )
    changed_created_at = {**session, "created_at": "2099-01-01T00:00:00+00:00"}

    assert prepare_calls == [1]
    assert [schema["function"]["name"] for schema in session["tool_schemas"]] == ["tool_a", "tool_b"]
    assert session["runtime_preparation_fingerprint"] == session["fingerprint"]
    assert validate_context_session_integrity(changed_created_at)[0] is True


def test_context_session_allows_true_informational_turn_without_skill(monkeypatch, tmp_path):
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.create_workflow_context",
        lambda **_kwargs: _Ctx(tmp_path),
    )
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.get_skill", lambda _skill_id: None)

    def fake_render_main_turn_prompt_partitions(**kwargs):
        seen["skill"] = kwargs["skill"]
        seen["tool_schemas"] = kwargs["tool_schemas"]
        return _fake_partitions("answering system")

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.prompt.context_builder.render_main_turn_prompt_partitions",
        fake_render_main_turn_prompt_partitions,
    )

    session = ContextSessionManager().build(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        payload={},
        conversation={
            "id": "conv-1",
            "runtime_profile": "home",
            "artifact_mode": "web",
            "phase": "executing",
            "skill_id": None,
            "resolved_skill_id": None,
            "turn_route": {
                "route_kind": "informational_turn",
                "activity": "answering",
                "requires_skill_selection": False,
            },
        },
    )

    expected_tools = {
        "analyze_image",
        "ask_user",
        "fetch_webpage",
        "generate_image",
        "generate_video",
        "glob_files",
        "grep_files",
        "list_files",
        "read_file",
        "search_harness_history",
        "web_search",
        "workspace_map",
    }
    seen_tool_names = _schema_names(seen["tool_schemas"])

    assert seen["skill"] is None
    assert seen_tool_names == expected_tools
    assert "register_artifact" not in seen_tool_names
    assert session["skill_id"] == ""
    assert _schema_names(session["tool_schemas"]) == expected_tools
    assert session["runtime_contract"] == {}
    assert validate_context_session_integrity(session)[0] is True


def test_runtime_preparation_reads_contract_from_runtime_snapshot(monkeypatch, tmp_path):
    class _ActiveRuntime:
        prepared_workspace = {}
        runtime_contract_patch = {}
        trace = {}
        events = []

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.runtime_preparation._ACTIVE_SKILL_RUNTIME.prepare",
        lambda **_kwargs: _ActiveRuntime(),
    )

    prepared = prepare_execution_runtime_context(
        ctx=_Ctx(tmp_path),
        conversation={
            "id": "conv-1",
            "runtime_snapshot": {
                "runtime_contract": {
                    "discovery_brief": {"answers": {"output": "Deck"}},
                    "design_system_id": "aurora",
                }
            },
        },
        skill=_Skill(),
    )

    assert prepared["runtime_contract"]["discovery_brief"]["answers"]["output"] == "Deck"
    assert prepared["runtime_contract"]["design_system_id"] == "aurora"


def test_runtime_snapshot_syncs_contract_into_runtime_state():
    snapshot = _sync_runtime_contract_into_state(
        {
            "runtime_state": {
                "runtime_contract": {"active_skill_context": {"skill_id": "xlsx"}},
            },
            "runtime_contract": {
                "discovery_brief": {"answers": {"output": "Deck"}},
            },
        }
    )

    contract = snapshot["runtime_state"]["runtime_contract"]
    assert contract["active_skill_context"] == {"skill_id": "xlsx"}
    assert contract["discovery_brief"]["answers"]["output"] == "Deck"


def test_model_context_includes_hidden_interaction_submission(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.assembler.load_latest_boundary_v2",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.assembler.latest_conversation_event_sequence",
        lambda *_args, **_kwargs: 0,
    )

    bundle = build_model_context(
        7,
        "conv-1",
        transcript_messages=[
            {
                "id": "interaction-submission",
                "role": "user",
                "content": json.dumps(
                    {
                        "type": "interaction_submission",
                        "kind": "ask_user",
                        "answers": {"brand_name": {"value": "Acme"}},
                    }
                ),
                "metadata": {
                    "message_kind": "agent_context",
                    "agent_context_kind": "interaction_submission",
                    "model_visible": True,
                    "ui_visible": False,
                },
            }
        ],
    )

    assert bundle.messages == [
        {
            "role": "user",
            "content": '{"type": "interaction_submission", "kind": "ask_user", "answers": {"brand_name": {"value": "Acme"}}}',
            "metadata": {
                "message_kind": "agent_context",
                "agent_context_kind": "interaction_submission",
            },
        }
    ]


def test_context_session_uses_planning_phase_for_tool_schemas_and_prompt(monkeypatch, tmp_path):
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.create_workflow_context",
        lambda **_kwargs: _Ctx(tmp_path),
    )
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.get_skill", lambda _skill_id: _Skill())
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.create_harness_registry", lambda **_kwargs: object())

    def fake_tool_schemas_for_phase(_registry, **kwargs):
        seen["tool_phase"] = kwargs["phase"]
        return [
            {"type": "function", "function": {"name": "request_plan_approval"}},
            {"type": "function", "function": {"name": "read_file"}},
        ]

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.tool_schemas_for_phase",
        fake_tool_schemas_for_phase,
    )

    def fake_render_main_turn_prompt_partitions(**kwargs):
        seen["prompt_phase"] = kwargs["conversation"]["phase"]
        return _fake_partitions("planning system")

    monkeypatch.setattr(
        "app.services.agent_harness.authoring.prompt.context_builder.render_main_turn_prompt_partitions",
        fake_render_main_turn_prompt_partitions,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.prepare_execution_runtime_context",
        lambda **_kwargs: {
            "runtime_contract": {"active_skill_context": {"source_digest": "digest-1"}},
            "workspace_runtime_session": {},
            "prepared_workspace": {},
        },
    )

    session = ContextSessionManager().build(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        payload={},
        conversation={
            "id": "conv-1",
            "phase": "planning",
            "skill_id": "xlsx",
            "artifact_mode": "spreadsheet",
        },
    )

    assert seen == {"tool_phase": "planning", "prompt_phase": "planning"}
    assert session["phase"] == "planning"
    assert [schema["function"]["name"] for schema in session["tool_schemas"]] == ["read_file", "request_plan_approval"]
    assert validate_context_session_integrity(session)[0] is True


def test_context_session_hides_ask_user_during_plan_execution(monkeypatch, tmp_path):
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.create_workflow_context",
        lambda **_kwargs: _Ctx(tmp_path),
    )
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.get_skill", lambda _skill_id: _Skill())
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.create_harness_registry", lambda **_kwargs: object())

    def fake_tool_schemas_for_phase(_registry, **kwargs):
        seen["tool_phase"] = kwargs["phase"]
        seen["hide_ask_user"] = kwargs["hide_ask_user"]
        return [{"type": "function", "function": {"name": "write_file"}}]

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.tool_schemas_for_phase",
        fake_tool_schemas_for_phase,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.authoring.prompt.context_builder.render_main_turn_prompt_partitions",
        lambda **_kwargs: _fake_partitions("executing system"),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.prepare_execution_runtime_context",
        lambda **_kwargs: {
            "runtime_contract": {"active_skill_context": {"source_digest": "digest-1"}},
            "workspace_runtime_session": {},
            "prepared_workspace": {},
        },
    )

    session = ContextSessionManager().build(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        payload={},
        conversation={
            "id": "conv-1",
            "phase": "executing",
            "skill_id": "xlsx",
            "artifact_mode": "spreadsheet",
            "plan_state": {
                "status": "in_progress",
                "outline_state": {"status": "executing"},
                "execution_state": {"status": "in_progress"},
            },
        },
    )

    assert seen == {"tool_phase": "executing", "hide_ask_user": True}
    assert session["phase"] == "executing"
    assert [schema["function"]["name"] for schema in session["tool_schemas"]] == ["write_file"]
    assert validate_context_session_integrity(session)[0] is True


def test_static_system_context_preserves_confirmation_phase(monkeypatch, tmp_path):
    from app.services.agent_harness.authoring.prompt import context_builder

    seen: dict[str, object] = {}

    class _Bundle:
        rendered_system = "phase system"

    class _Runtime:
        def build_bundle(self, spec):
            seen["phase"] = spec.phase_value
            seen["conversation_phase"] = spec.conversation.get("phase")
            return _Bundle()

        def build_partitions(self, spec):
            self.build_bundle(spec)

            class _Partitions:
                stable_system_text = "phase system"
                context_snapshot_blocks = []
                turn_append_blocks = []
                trace = {}

            return _Partitions()

    monkeypatch.setattr(context_builder, "_PROMPT_RUNTIME", _Runtime())
    monkeypatch.setattr(context_builder, "_cached_mode_contract", lambda *_args, **_kwargs: "mode contract")
    monkeypatch.setattr(context_builder, "build_active_skill_manifest", lambda **_kwargs: {})

    rendered = context_builder.render_static_system_context(
        language="zh",
        conversation={
            "id": "conv-1",
            "phase": "planning",
            "runtime_profile": "home",
            "artifact_mode": "spreadsheet",
        },
        model_name="GPT-5.4",
        skill=_Skill(),
        skill_prompt="zh skill",
        artifact_mode="spreadsheet",
        skill_id="xlsx",
        skill_runtime_dir=tmp_path / "skill",
        prepared_workspace=None,
        workspace_runtime_session={},
        runtime_contract={},
        tool_schemas=[{"type": "function", "function": {"name": "request_plan_approval"}}],
    )

    assert rendered == "phase system"
    assert seen == {"phase": "planning", "conversation_phase": "planning"}


def test_context_session_integrity_detects_fingerprint_change():
    schemas = _stable_tool_schemas([{"type": "function", "function": {"name": "tool_a"}}])
    session = {
        "version": 1,
        "phase": "executing",
        "language": "zh",
        "model": "GPT-5.4",
        "skill_id": "xlsx",
        "artifact_mode": "document",
        "system_prompt": "stable system",
        "tool_schemas": schemas,
        "runtime_contract": {"active_skill_context": {"source_digest": "digest-1"}},
        "workspace_runtime_session": {},
        "prepared_workspace": {},
    }
    ok, diagnostics = validate_context_session_integrity(
        {
            **session,
            "fingerprint": "wrong",
            "static_context_hash": "wrong",
        }
    )

    assert ok is False
    assert diagnostics["expected_fingerprint"] != "wrong"


def test_agent_context_messages_are_model_visible_but_not_transcript_visible():
    from app.services.agent_harness.runtime.message_visibility import (
        is_model_session_message,
        is_transcript_visible_message,
    )

    message = {
        "role": "system",
        "content": "<agent_context kind=\"runtime_time\">Current runtime time</agent_context>",
        "metadata": {
            "message_kind": "agent_context",
            "model_visible": True,
            "ui_visible": False,
        },
    }

    assert is_model_session_message(message) is True
    assert is_transcript_visible_message(message) is False


def test_agent_context_messages_are_not_indexed_by_recall_sidecar():
    from app.services.agent_harness.runtime.recall_sidecar import _message_text

    assert (
        _message_text(
            {
                "role": "system",
                "content": "<agent_context kind=\"runtime_time\">Current runtime time</agent_context>",
                "metadata": {"message_kind": "agent_context"},
            }
        )
        == ""
    )


def test_context_session_with_critique_payload_remains_reusable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.create_workflow_context",
        lambda **_kwargs: _Ctx(tmp_path),
    )
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.get_skill", lambda _skill_id: _Skill())
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.create_harness_registry", lambda **_kwargs: object())
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.tool_schemas_for_phase",
        lambda *_args, **_kwargs: [{"type": "function", "function": {"name": "write_file"}}],
    )
    monkeypatch.setattr(
        "app.services.agent_harness.authoring.prompt.context_builder.render_main_turn_prompt_partitions",
        lambda **_kwargs: _fake_partitions("executing system"),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.prepare_execution_runtime_context",
        lambda **_kwargs: {
            "runtime_contract": {"active_skill_context": {"source_digest": "digest-1"}},
            "workspace_runtime_session": {"active_entry": "index.html"},
            "prepared_workspace": {"artifact_work_root": "project", "entry_file": "index.html"},
        },
    )
    # Critique runtime payload is dynamic and must stay out of the static hash.
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.context_session.critique_runtime_payload",
        lambda **_kwargs: {"critique_run_id": "critique-abc123", "status": "running"},
    )

    session = ContextSessionManager().build(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        payload={},
        conversation={
            "id": "conv-1",
            "phase": "executing",
            "skill_id": "xlsx",
            "artifact_mode": "slides",
        },
    )

    assert session["critique"]["critique_run_id"] == "critique-abc123"
    # The critique blob is dynamic and must not break reuse of the context session.
    assert validate_context_session_integrity(session)[0] is True


def test_render_context_includes_tool_result_and_agent_context_tail(monkeypatch):
    messages = [
        {"_seq": 1, "role": "user", "content": "make xlsx"},
        {
            "_seq": 2,
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "name": "write_file", "arguments": "{}"}],
        },
        {
            "_seq": 3,
            "role": "tool",
            "content": "{\"status\":\"completed\"}",
            "tool_call_id": "call-1",
            "tool_name": "write_file",
            "metadata": {"model_visible": True},
        },
    ]

    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_messages", lambda *_args: messages)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_latest_boundary_v2", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.latest_conversation_event_sequence", lambda *_args: 9)
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.compact_if_needed", lambda *_args, **_kwargs: None)

    rendered = ContextProjector().render(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        context_session={
            "system_prompt": "stable system",
            "context_snapshot_blocks": [{"id": "state.plan", "content": "Plan state payload:\n{}"}],
            "tool_schemas": [],
            "model": "GPT-5.4",
            "language": "zh",
        },
        previous_checkpoint={"message_seq_end": 2, "event_seq_end": 8},
    )

    messages_out = rendered["turn_context"]["messages"]
    assert messages_out[2]["role"] == "tool"
    assert messages_out[2]["tool_call_id"] == "call-1"
    assert messages_out[-1]["content"].startswith("<agent_context kind=\"context_init\"")
    assert rendered["turn_context"]["system"] == "stable system"
    assert "Current runtime time:" not in rendered["turn_context"]["system"]
    assert rendered["turn_context"]["prompt_cache_key"] == "agent:conv-1"
    assert len(rendered["persist_messages"]) == 1
    assert rendered["checkpoint"]["message_seq_end"] == 3
    assert rendered["checkpoint"]["event_seq_end"] == 9
    assert rendered["checkpoint"]["previous_message_seq_end"] == 2
    assert rendered["checkpoint"]["summary_message"] is None
    context_metadata = rendered["persist_messages"][-1]["metadata"]
    assert context_metadata["agent_context_kind"] == "context_init"
    assert rendered["diagnostics"]["runtime_time_included"] is False


def test_render_context_omits_context_update_when_snapshot_matches(monkeypatch):
    messages = [
        {"_seq": 1, "role": "user", "content": "make xlsx"},
        {"_seq": 2, "role": "assistant", "content": "ok"},
        {
            "_seq": 3,
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "name": "write_file", "arguments": "{}"}],
        },
        {
            "_seq": 4,
            "role": "tool",
            "content": "{\"status\":\"completed\"}",
            "tool_call_id": "call-1",
            "tool_name": "write_file",
            "metadata": {"model_visible": True},
        },
    ]

    context_block = {"id": "state.plan", "content": "Plan state payload:\n{}"}
    context_hash = __import__("hashlib").sha256(
        __import__("json").dumps(
            {"id": "state.plan", "content": "Plan state payload:\n{}"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_messages", lambda *_args: messages)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_latest_boundary_v2", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.latest_conversation_event_sequence", lambda *_args: 12)
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.compact_if_needed", lambda *_args, **_kwargs: None)

    rendered = ContextProjector().render(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        context_session={
            "system_prompt": "stable system",
            "context_snapshot_blocks": [context_block],
            "tool_schemas": [],
            "model": "GPT-5.4",
            "language": "zh",
        },
        conversation={
            "runtime_snapshot_json": {
                "agent_prompt_context_v2": {
                    "version": 2,
                    "stable_system_hash": __import__("hashlib").sha256(b"stable system").hexdigest(),
                    "context_blocks": {"state.plan": context_hash},
                }
            }
        },
    )

    assert rendered["persist_messages"] == []
    assert rendered["turn_context"]["messages"][-1]["role"] == "tool"
    assert rendered["diagnostics"]["runtime_time_included"] is False
    assert rendered["checkpoint"]["message_seq_end"] == 4
    assert rendered["checkpoint"]["event_seq_end"] == 12
    assert rendered["checkpoint"]["summary_message"] is None


def test_render_context_agent_context_keys_include_render_turn_and_context_hash(monkeypatch):
    messages = [{"_seq": 1, "role": "user", "content": "make xlsx"}]

    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_messages", lambda *_args: messages)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_latest_boundary_v2", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.latest_conversation_event_sequence", lambda *_args: 2)
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.compact_if_needed", lambda *_args, **_kwargs: None)

    base_session = {
        "system_prompt": "stable system",
        "context_snapshot_blocks": [{"id": "state.plan", "content": "Plan state payload:\n{\"v\":1}"}],
        "turn_append_blocks": [{"id": "delta.planning", "content": "temporary planning instruction"}],
        "tool_schemas": [],
        "model": "GPT-5.4",
        "language": "zh",
    }
    first = ContextProjector().render(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        render_step_id="step-render-a",
        turn=0,
        attempt=1,
        context_session=base_session,
        include_runtime_time=True,
    )
    second = ContextProjector().render(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        render_step_id="step-render-b",
        turn=1,
        attempt=1,
        context_session=base_session,
        include_runtime_time=True,
        conversation={"runtime_snapshot_json": {"agent_prompt_context_v2": first["runtime_patch"]["agent_prompt_context_v2"]}},
    )
    updated = ContextProjector().render(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        render_step_id="step-render-c",
        turn=2,
        attempt=1,
        context_session={
            **base_session,
            "context_snapshot_blocks": [{"id": "state.plan", "content": "Plan state payload:\n{\"v\":2}"}],
        },
        include_runtime_time=True,
        conversation={"runtime_snapshot_json": {"agent_prompt_context_v2": first["runtime_patch"]["agent_prompt_context_v2"]}},
    )

    first_kinds = [message["metadata"]["agent_context_kind"] for message in first["persist_messages"]]
    assert first_kinds == ["context_init", "runtime_time", "turn_append"]
    assert [message["metadata"]["agent_context_kind"] for message in second["persist_messages"]] == [
        "runtime_time",
        "turn_append",
    ]
    assert [message["metadata"]["agent_context_kind"] for message in updated["persist_messages"]][:1] == [
        "context_update"
    ]
    first_runtime_key = next(
        message["metadata"]["idempotency_key"]
        for message in first["persist_messages"]
        if message["metadata"]["agent_context_kind"] == "runtime_time"
    )
    second_runtime_key = next(
        message["metadata"]["idempotency_key"]
        for message in second["persist_messages"]
        if message["metadata"]["agent_context_kind"] == "runtime_time"
    )
    update_message = updated["persist_messages"][0]
    assert first_runtime_key != second_runtime_key
    assert "render:step-render-a:turn:0" in first_runtime_key
    assert "render:step-render-b:turn:1" in second_runtime_key
    assert update_message["metadata"]["context_hash"][:16] in update_message["metadata"]["idempotency_key"]


def test_render_context_includes_current_user_in_context_without_persisting_visible_message(monkeypatch):
    messages = [{"_seq": 1, "role": "assistant", "content": "ready"}]

    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_messages", lambda *_args: messages)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_latest_boundary_v2", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.latest_conversation_event_sequence", lambda *_args: 2)
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.compact_if_needed", lambda *_args, **_kwargs: None)

    rendered = ContextProjector().render(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        render_step_id="step-render-user",
        turn=0,
        attempt=1,
        context_session={
            "system_prompt": "stable system",
            "context_snapshot_blocks": [{"id": "state.plan", "content": "Plan state payload:\n{}"}],
            "tool_schemas": [],
            "model": "GPT-5.4",
            "language": "zh",
        },
        current_user_message={
            "role": "user",
            "content": "生成一个表格",
            "attachments": [{"type": "image", "url": "references/inputs/a.png"}],
            "created_at": "2026-06-04T00:00:00+00:00",
            "metadata": {"references": [{"id": "ref-1"}], "idempotency_key": "user-msg-1"},
        },
    )

    persist_roles = [message["role"] for message in rendered["persist_messages"]]
    assert persist_roles == ["system", "system", "user"]
    user_intent = rendered["persist_messages"][-1]
    assert user_intent["content"] == "生成一个表格"
    assert user_intent["attachments"] == [{"type": "image", "url": "references/inputs/a.png"}]
    assert user_intent["metadata"]["message_kind"] == "agent_context"
    assert user_intent["metadata"]["agent_context_kind"] == "user_intent"
    assert user_intent["metadata"]["ui_visible"] is False
    assert user_intent["metadata"]["model_visible"] is True
    assert user_intent["metadata"]["idempotency_key"] == "user-msg-1:agent-context:user-intent"
    assert user_intent["metadata"]["source_message_id"] == "user-msg-1"
    assert [message["role"] for message in rendered["turn_context"]["messages"][-3:]] == ["system", "system", "user"]
    assert rendered["turn_context"]["messages"][-1]["content"].startswith("生成一个表格")
    assert "references/inputs/a.png" in rendered["turn_context"]["messages"][-1]["content"]
    assert "analyze_image.image_url" in rendered["turn_context"]["messages"][-1]["content"]
    assert rendered["turn_context"]["messages"][-1]["metadata"]["idempotency_key"] == "user-msg-1"


def test_render_context_keeps_persisted_hidden_user_intent_model_visible_after_tool(monkeypatch):
    messages = [
        {
            "_seq": 1,
            "role": "user",
            "content": "分析下这张图片内容",
            "attachments": [{"type": "image", "url": "references/inputs/upload_001/source.jpg"}],
            "metadata": {
                "message_kind": "agent_context",
                "agent_context_kind": "user_intent",
                "ui_visible": False,
                "model_visible": True,
                "idempotency_key": "user-msg-1:agent-context:user-intent",
            },
        },
        {
            "_seq": 2,
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "name": "analyze_image", "arguments": "{}"}],
        },
        {
            "_seq": 3,
            "role": "tool",
            "content": "{\"analysis\":\"图片里是一张产品图\"}",
            "tool_call_id": "call-1",
            "tool_name": "analyze_image",
            "metadata": {"model_visible": True},
        },
    ]

    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_messages", lambda *_args: messages)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_latest_boundary_v2", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.latest_conversation_event_sequence", lambda *_args: 4)
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.compact_if_needed", lambda *_args, **_kwargs: None)

    rendered = ContextProjector().render(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        render_step_id="step-render-after-tool",
        turn=1,
        attempt=1,
        context_session={
            "system_prompt": "stable system",
            "tool_schemas": [],
            "model": "GPT-5.4",
            "language": "zh",
        },
    )

    messages_out = rendered["turn_context"]["messages"]
    assert messages_out[0]["role"] == "user"
    assert messages_out[0]["content"].startswith("分析下这张图片内容")
    assert "references/inputs/upload_001/source.jpg" in messages_out[0]["content"]
    assert "analyze_image.image_url" in messages_out[0]["content"]
    assert messages_out[0]["metadata"]["agent_context_kind"] == "user_intent"
    assert messages_out[1]["role"] == "assistant"
    assert messages_out[2]["role"] == "tool"


def test_render_context_budget_uses_ollama_provider_window(monkeypatch):
    from app.core.config import settings

    messages = [{"_seq": 1, "role": "user", "content": "make xlsx"}]

    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_MODEL", "GPT-5.4")
    monkeypatch.setattr(settings, "OLLAMA_MAX_INPUT_TOKENS", 1_000_000)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_messages", lambda *_args: messages)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_latest_boundary_v2", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.latest_conversation_event_sequence", lambda *_args: 2)
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.compact_if_needed", lambda *_args, **_kwargs: None)

    rendered = ContextProjector().render(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        context_session={
            "system_prompt": "stable system",
            "tool_schemas": [],
            "model": "GPT-5.4",
            "multimodal_provider": "ollama",
            "language": "zh",
        },
    )

    diagnostics = rendered["diagnostics"]
    assert diagnostics["model_provider"] == "ollama"
    assert diagnostics["configured_max_input_tokens"] == 1_000_000
    assert diagnostics["fallback_budget_used"] is False
    assert diagnostics["message_token_budget"] > 900_000


def test_render_context_budget_uses_builtin_model_window(monkeypatch):
    messages = [{"_seq": 1, "role": "user", "content": "make xlsx"}]

    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_messages", lambda *_args: messages)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_latest_boundary_v2", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.latest_conversation_event_sequence", lambda *_args: 2)
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.compact_if_needed", lambda *_args, **_kwargs: None)

    rendered = ContextProjector().render(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        context_session={
            "system_prompt": "stable system",
            "tool_schemas": [],
            "model": "glm-5.1",
            "multimodal_provider": "builtin",
            "language": "zh",
        },
    )

    diagnostics = rendered["diagnostics"]
    assert diagnostics["model_provider"] == "builtin"
    assert diagnostics["configured_max_input_tokens"] == 204_800
    assert diagnostics["fallback_budget_used"] is False
    assert 190_000 < diagnostics["message_token_budget"] < 204_800


def test_render_context_budget_falls_back_for_unknown_model(monkeypatch):
    messages = [{"_seq": 1, "role": "user", "content": "make xlsx"}]

    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_messages", lambda *_args: messages)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_latest_boundary_v2", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.latest_conversation_event_sequence", lambda *_args: 2)
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.compact_if_needed", lambda *_args, **_kwargs: None)

    rendered = ContextProjector().render(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        context_session={
            "system_prompt": "stable system",
            "tool_schemas": [],
            "model": "unknown-model",
            "multimodal_provider": "builtin",
            "language": "zh",
        },
    )

    diagnostics = rendered["diagnostics"]
    assert diagnostics["model_provider"] == "builtin"
    assert diagnostics["configured_max_input_tokens"] == 100_000
    assert diagnostics["fallback_budget_used"] is True
    assert 90_000 < diagnostics["message_token_budget"] < 100_000


def _render_prompt_debug_fixture(monkeypatch, tmp_path, *, enabled: bool, full: bool = False, run_id: str = "run-1"):
    from app.core.config import settings

    messages = [
        {"_seq": 1, "role": "user", "content": "secret user prompt"},
        {"_seq": 2, "role": "assistant", "content": "ok"},
    ]
    meta_dir = tmp_path / ".meta"

    monkeypatch.setattr(settings, "HARNESS_PROMPT_CACHE_DEBUG", enabled)
    monkeypatch.setattr(settings, "HARNESS_PROMPT_CACHE_DEBUG_FULL", full)
    monkeypatch.setattr(settings, "HARNESS_WORKSPACE_ROOT", str(tmp_path / "harness"))
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.ensure_harness_meta", lambda *_args: meta_dir)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_messages", lambda *_args: messages)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.load_latest_boundary_v2", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.runtime.model_context.assembler.latest_conversation_event_sequence", lambda *_args: 3)
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.compact_if_needed", lambda *_args, **_kwargs: None)

    rendered = ContextProjector().render(
        user_id=7,
        conversation_id="conv-1",
        run_id=run_id,
        context_session={
            "system_prompt": "stable system secret",
            "context_snapshot_blocks": [{"id": "state.plan", "content": "Plan state payload:\n{}"}],
            "tool_schemas": [{"type": "function", "function": {"name": "write_file", "description": "tool secret"}}],
            "model": "GPT-5.4",
            "language": "zh",
        },
    )
    return rendered, meta_dir


def test_prompt_cache_debug_disabled_does_not_write_trace(monkeypatch, tmp_path):
    _render_prompt_debug_fixture(monkeypatch, tmp_path, enabled=False)

    assert not (tmp_path / ".meta" / "prompt_cache_debug").exists()


def test_prompt_cache_debug_writes_redacted_fingerprint_trace(monkeypatch, tmp_path):
    _render_prompt_debug_fixture(monkeypatch, tmp_path, enabled=True, full=False, run_id="run-1")
    debug_dir = tmp_path / ".meta" / "prompt_cache_debug"
    (debug_dir / "usage-latest.json").write_text(
        json.dumps({"trace_type": "prompt_cache_usage", "trace_file": "usage-latest.json"}),
        encoding="utf-8",
    )
    _render_prompt_debug_fixture(monkeypatch, tmp_path, enabled=True, full=False, run_id="run-2")

    trace_paths = sorted(path for path in debug_dir.glob("*.json") if not path.name.startswith("usage-"))
    assert len(trace_paths) == 2

    first = json.loads(trace_paths[0].read_text(encoding="utf-8"))
    second = json.loads(trace_paths[1].read_text(encoding="utf-8"))

    assert first["full_content_included"] is False
    assert "system" not in first
    assert "tools" not in first
    assert all("content" not in message for message in first["messages"])
    assert first["system_hash"]
    assert first["tools_hash"]
    assert first["message_fingerprints"]
    assert "secret user prompt" not in trace_paths[0].read_text(encoding="utf-8")
    assert "stable system secret" not in trace_paths[0].read_text(encoding="utf-8")
    assert "tool secret" not in trace_paths[0].read_text(encoding="utf-8")
    assert second["prefix_diff"]["previous_trace"] == first["trace_file"]
    assert second["prefix_diff"]["same_system"] is True
    assert second["prefix_diff"]["same_tools"] is True
    assert second["prefix_diff"]["common_prefix_message_count"] >= 2
    assert second["wire_prefix_diff"]["same_system"] is True
    assert second["wire_prefix_diff"]["same_tools"] is True
    assert second["wire_prefix_diff"]["common_prefix_message_count"] == len(first["wire_message_fingerprints"])
    assert second["wire_prefix_diff"]["first_changed_reason"] in {None, "message_count_changed"}
    agent_context_entries = [
        message for message in first["messages"] if message.get("message_kind") == "agent_context"
    ]
    assert agent_context_entries
    assert agent_context_entries[0]["agent_context_kind"] == "context_init"
    assert agent_context_entries[0]["context_hash"]
    assert agent_context_entries[0]["metadata_hash"]
    assert agent_context_entries[0]["idempotency_key_hash"]
    assert "run:run-1:agent-context" not in trace_paths[0].read_text(encoding="utf-8")


def test_prompt_cache_debug_usage_trace_records_cached_tokens(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.agent_harness.workflow import handlers

    meta_dir = tmp_path / ".meta"
    monkeypatch.setattr(settings, "HARNESS_PROMPT_CACHE_DEBUG", True)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.ensure_harness_meta", lambda *_args: meta_dir)

    handlers._persist_prompt_cache_debug_usage_trace(
        user_id=7,
        conversation_id="conv-1",
        run_id="run-1",
        step_id="step-model",
        turn=3,
        model="GPT-5.4",
        model_provider="ollama",
        prompt_cache_key="agent:conv-1",
        usage={
            "input_tokens": 100,
            "output_tokens": 8,
            "cached_tokens": 64,
            "cache_read_tokens": 32,
            "cache_creation_tokens": 16,
            "request_id": "req-1",
        },
        elapsed_ms=1234,
        render_trace_file="turn-trace.json",
    )

    trace_paths = sorted((meta_dir / "prompt_cache_debug").glob("usage-*.json"))
    assert len(trace_paths) == 1
    trace = json.loads(trace_paths[0].read_text(encoding="utf-8"))
    assert trace["trace_type"] == "prompt_cache_usage"
    assert trace["model_provider"] == "ollama"
    assert trace["prompt_cache_key"] == "agent:conv-1"
    assert trace["render_trace_file"] == "turn-trace.json"
    assert trace["usage"]["input_tokens"] == 100
    assert trace["usage"]["cached_tokens"] == 64
    assert trace["usage"]["cache_read_tokens"] == 32
    assert trace["usage"]["cache_creation_tokens"] == 16
