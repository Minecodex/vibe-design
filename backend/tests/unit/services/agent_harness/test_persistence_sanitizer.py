from pathlib import Path

import pytest


def test_sanitizer_redacts_nested_data_uri_and_base64_keys():
    from app.core.persistence_sanitizer import sanitize_persistent_payload

    sanitized = sanitize_persistent_payload(
        {
            "safe": "hello",
            "image": "data:image/jpeg;base64,YWJj",
            "nested": [{"b64_json": "YWJjZA=="}],
        }
    )

    assert sanitized["safe"] == "hello"
    assert sanitized["image"] == "[omitted-data-uri:image/jpeg;base64_chars=4]"
    assert sanitized["nested"][0]["b64_json"] == "[omitted-base64:chars=8]"


def test_agent_persistence_redacts_base64_from_messages_events_and_runtime(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.conversation_events import load_conversation_events
    from app.services.agent_harness.runtime.eventing.event_log import append_event
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
    from app.services.agent_harness.workspace.conversation.conversation_message_store import (
        load_messages,
    )
    from app.services.agent_harness.workspace.session_v2.db_store import (
        append_message_record as append_message,
    )
    from app.services.agent_harness.workspace.session_v2.service import patch_runtime_state

    conversation = create_conversation(7, title="Redact base64")
    data_uri = "data:image/png;base64,ZmFrZS1pbWFnZQ=="

    append_message(
        7,
        conversation["id"],
        {
            "role": "user",
            "content": data_uri,
            "attachments": [{"image_url": {"url": data_uri}}],
            "metadata": {"b64_json": "ZmFrZQ=="},
        },
    )
    event = append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="debug_payload",
        payload={"image_url": {"url": data_uri}, "source_blob": "ZmFrZQ=="},
    )
    updated = patch_runtime_state(
        7,
        conversation["id"],
        {"runtime_state": {"model_session_state": {"active_history": [{"content": data_uri}]}}},
    )

    stored_messages = load_messages(7, conversation["id"])
    stored_events = load_conversation_events(7, conversation["id"])
    serialized = str(
        {
            "messages": stored_messages,
            "event": event,
            "events": stored_events,
            "runtime_state": updated.get("runtime_state"),
        }
    )

    assert "ZmFrZS1pbWFnZQ" not in serialized
    assert "data:image/png;base64" not in serialized
    assert "[omitted-data-uri:image/png;base64_chars=16]" in serialized
    assert "[omitted-base64:chars=8]" in serialized


@pytest.mark.asyncio
async def test_usage_log_params_redact_base64(db_session):
    from app.models.user import User
    from app.services.billing_service import BillingService

    user = User(
        email="redact-usage@example.test",
        username="redact-usage",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    log = await BillingService(db_session).create_usage_log(
        user_id=user.id,
        task_id=None,
        model_name="agent",
        task_type="agent_run",
        amount_cents=0,
        params={
            "conversation_id": "conv-redact",
            "image": "data:image/png;base64,ZmFrZQ==",
            "source_blob": "ZmFrZQ==",
        },
        task_status="success",
    )

    assert log.params["image"] == "[omitted-data-uri:image/png;base64_chars=8]"
    assert log.params["source_blob"] == "[omitted-base64:chars=8]"


@pytest.mark.asyncio
async def test_usage_and_generation_repositories_redact_params(db_session):
    from app.models.billing import UsageLog
    from app.models.generation import GenerationTask
    from app.models.user import User
    from app.repositories.billing_repository import UsageLogRepository
    from app.repositories.generation_repository import GenerationTaskRepository

    user = User(
        email="redact-repo@example.test",
        username="redact-repo",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    data_uri = "data:image/png;base64,ZmFrZQ=="

    usage_repo = UsageLogRepository(db_session)
    usage = await usage_repo.create(
        UsageLog(
            user_id=user.id,
            model_name="agent",
            model_label="agent",
            task_type="agent_run",
            amount_cents=0,
            amount_cents_original=0,
            status="pending",
            params={"image": data_uri},
        )
    )
    usage = await usage_repo.update(usage, {"params": {"source_blob": "ZmFrZQ=="}})

    task_repo = GenerationTaskRepository(db_session)
    task = await task_repo.create(
        GenerationTask(
            user_id=user.id,
            project_id=None,
            task_type="text2image",
            provider_code="builtin",
            model_name="nano-banana-2",
            prompt="test",
            params={"image": data_uri},
            status="pending",
        )
    )
    task = await task_repo.update(task, {"params": {"b64_json": "ZmFrZQ=="}})

    assert usage.params["source_blob"] == "[omitted-base64:chars=8]"
    assert task.params["b64_json"] == "[omitted-base64:chars=8]"
