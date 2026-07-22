from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.agent_harness.workspace.conversation.turns import preflight_billing


def test_preflight_billing_key_stable_with_provider_request_id():
    usage = {"input_tokens": 50, "output_tokens": 20, "oneapi_request_id": "rid-abc"}
    key_a = preflight_billing._preflight_billing_key(
        turn_idempotency_key="message:conv1:abcdef",
        conversation_id="conv1",
        kind="skill_resolution",
        index=0,
        usage=usage,
        model_name="gpt-4o-mini",
    )
    # A retry of the same logical call yields the same key.
    key_b = preflight_billing._preflight_billing_key(
        turn_idempotency_key="message:conv1:abcdef",
        conversation_id="conv1",
        kind="skill_resolution",
        index=0,
        usage=usage,
        model_name="gpt-4o-mini",
    )
    assert key_a == key_b
    assert key_a is not None
    assert "rid-abc" in key_a
    assert key_a.startswith("preflight:message:conv1:abcdef:skill_resolution:0:")


def test_preflight_billing_key_distinct_across_calls_and_kinds():
    usage_a = {"input_tokens": 1, "output_tokens": 1, "oneapi_request_id": "ra"}
    usage_b = {"input_tokens": 1, "output_tokens": 1, "oneapi_request_id": "rb"}

    key_call0 = preflight_billing._preflight_billing_key(
        turn_idempotency_key="message:conv1:k",
        conversation_id="conv1",
        kind="skill_resolution",
        index=0,
        usage=usage_a,
        model_name="m",
    )
    key_call1 = preflight_billing._preflight_billing_key(
        turn_idempotency_key="message:conv1:k",
        conversation_id="conv1",
        kind="skill_resolution",
        index=1,
        usage=usage_b,
        model_name="m",
    )
    key_other_kind = preflight_billing._preflight_billing_key(
        turn_idempotency_key="message:conv1:k",
        conversation_id="conv1",
        kind="home_turn_router",
        index=0,
        usage=usage_a,
        model_name="m",
    )
    assert len({key_call0, key_call1, key_other_kind}) == 3


def test_preflight_billing_key_falls_back_to_shape_hash_without_request_id():
    usage = {"input_tokens": 100, "output_tokens": 30}
    key_a = preflight_billing._preflight_billing_key(
        turn_idempotency_key="message:conv1:abc",
        conversation_id="conv1",
        kind="skill_resolution",
        index=0,
        usage=usage,
        model_name="gpt-4o-mini",
    )
    key_b = preflight_billing._preflight_billing_key(
        turn_idempotency_key="message:conv1:abc",
        conversation_id="conv1",
        kind="skill_resolution",
        index=0,
        usage=usage,
        model_name="gpt-4o-mini",
    )
    assert key_a == key_b
    assert key_a is not None


def test_preflight_billing_key_none_without_turn_idempotency_key():
    usage = {"input_tokens": 1, "output_tokens": 1, "oneapi_request_id": "rid"}
    assert (
        preflight_billing._preflight_billing_key(
            turn_idempotency_key=None,
            conversation_id="conv1",
            kind="skill_resolution",
            index=0,
            usage=usage,
            model_name="m",
        )
        is None
    )
    assert (
        preflight_billing._preflight_billing_key(
            turn_idempotency_key="",
            conversation_id="conv1",
            kind="skill_resolution",
            index=0,
            usage=usage,
            model_name="m",
        )
        is None
    )


@pytest.mark.asyncio
async def test_record_turn_preflight_forwards_billing_key_per_call(monkeypatch):
    captured: list[dict] = []

    async def _fake_record_preflight_model_billing(_engine, **kwargs):
        captured.append(kwargs)
        return True

    monkeypatch.setattr(
        preflight_billing,
        "_field",
        preflight_billing._field,
    )
    # Patch the lazily-imported symbols inside the function.
    import app.services.agent_harness.runtime.execution_support.billing_controller as billing_controller_mod

    monkeypatch.setattr(
        billing_controller_mod,
        "record_preflight_model_billing",
        _fake_record_preflight_model_billing,
    )

    def _fake_create_context(**kwargs):
        return SimpleNamespace(parent_usage_log_id=999, **kwargs)

    import app.services.agent_harness.core.context as core_context_mod

    monkeypatch.setattr(core_context_mod, "create_context", _fake_create_context)
    monkeypatch.setattr(
        billing_controller_mod,
        "has_billable_usage",
        lambda usage: bool(usage),
    )

    conversation = {"id": "conv-x", "artifact_mode": "web"}
    model_calls = [
        {
            "model_name": "gpt-4o-mini",
            "usage": {"input_tokens": 5, "output_tokens": 2, "oneapi_request_id": "r0"},
            "elapsed_ms": 12,
            "kind": "skill_resolution",
        },
        {
            "model_name": "gpt-4o-mini",
            "usage": {"input_tokens": 3, "output_tokens": 4, "oneapi_request_id": "r1"},
            "elapsed_ms": 8,
            "kind": "home_turn_router",
        },
    ]

    parent_id = await preflight_billing.record_turn_preflight_model_calls(
        user_id=7,
        conversation=conversation,
        artifact_mode="web",
        run_id="run-x",
        preflight_model_calls=model_calls,
        turn_idempotency_key="message:conv-x:abc",
    )

    assert parent_id == 999
    assert len(captured) == 2
    assert captured[0]["billing_key"] != captured[1]["billing_key"]
    assert all(call["billing_key"] is not None for call in captured)
    assert all(
        call["billing_key"].startswith("preflight:message:conv-x:abc:")
        for call in captured
    )

    # Re-running with the same inputs must yield the same billing keys.
    captured.clear()
    await preflight_billing.record_turn_preflight_model_calls(
        user_id=7,
        conversation=conversation,
        artifact_mode="web",
        run_id="run-x-2",
        preflight_model_calls=model_calls,
        turn_idempotency_key="message:conv-x:abc",
    )
    second_keys = [call["billing_key"] for call in captured]
    # Replay yields identical keys despite the run_id changing — that's the
    # whole point: DB-level dedup catches the retry.
    assert second_keys[0].startswith("preflight:message:conv-x:abc:skill_resolution:0:")
    assert second_keys[1].startswith("preflight:message:conv-x:abc:home_turn_router:1:")


@pytest.mark.asyncio
async def test_record_turn_preflight_omits_billing_key_when_no_turn_key(monkeypatch):
    captured: list[dict] = []

    async def _fake_record_preflight_model_billing(_engine, **kwargs):
        captured.append(kwargs)
        return True

    import app.services.agent_harness.runtime.execution_support.billing_controller as billing_controller_mod

    monkeypatch.setattr(
        billing_controller_mod,
        "record_preflight_model_billing",
        _fake_record_preflight_model_billing,
    )

    def _fake_create_context(**kwargs):
        return SimpleNamespace(parent_usage_log_id=1, **kwargs)

    import app.services.agent_harness.core.context as core_context_mod

    monkeypatch.setattr(core_context_mod, "create_context", _fake_create_context)
    monkeypatch.setattr(
        billing_controller_mod,
        "has_billable_usage",
        lambda usage: bool(usage),
    )

    await preflight_billing.record_turn_preflight_model_calls(
        user_id=7,
        conversation={"id": "c"},
        artifact_mode="web",
        run_id="r",
        preflight_model_calls=[
            {
                "model_name": "m",
                "usage": {"input_tokens": 1, "output_tokens": 1, "oneapi_request_id": "x"},
                "elapsed_ms": 0,
                "kind": "k",
            }
        ],
        # No turn_idempotency_key provided -> legacy non-dedup behavior.
    )
    assert captured and captured[0]["billing_key"] is None


@pytest.mark.asyncio
async def test_record_turn_preflight_skips_ollama_model_calls(monkeypatch):
    captured: list[dict] = []

    async def _fake_record_preflight_model_billing(_engine, **kwargs):
        captured.append(kwargs)
        return True

    import app.services.agent_harness.runtime.execution_support.billing_controller as billing_controller_mod

    monkeypatch.setattr(
        billing_controller_mod,
        "record_preflight_model_billing",
        _fake_record_preflight_model_billing,
    )

    def _fake_create_context(**kwargs):
        return SimpleNamespace(parent_usage_log_id=1, **kwargs)

    import app.services.agent_harness.core.context as core_context_mod

    monkeypatch.setattr(core_context_mod, "create_context", _fake_create_context)
    monkeypatch.setattr(
        billing_controller_mod,
        "has_billable_usage",
        lambda usage: bool(usage),
    )

    parent_id = await preflight_billing.record_turn_preflight_model_calls(
        user_id=7,
        conversation={"id": "c"},
        artifact_mode="web",
        run_id="r",
        preflight_model_calls=[
            {
                "model_name": "local-vision",
                "provider_code": "ollama",
                "usage": {"input_tokens": 1, "output_tokens": 1, "provider_code": "ollama"},
                "elapsed_ms": 0,
                "kind": "home_turn_router",
            }
        ],
        turn_idempotency_key="message:c:k",
    )

    assert parent_id == 1
    assert captured == []

