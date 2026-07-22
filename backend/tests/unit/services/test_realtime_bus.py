from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.redis_coordination import InProcessRedisCoordinator
from app.services.realtime_bus import (
    REALTIME_KIND_NOTIFY,
    RealtimeBus,
    RealtimeEnvelope,
    RealtimeResource,
    RealtimeScope,
    publish_notification,
)


def test_realtime_topic_hashes_scope_without_leaking_resource_values():
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    bus = RealtimeBus(coordinator, namespace="test-app")

    topic = bus.topic(
        kind=REALTIME_KIND_NOTIFY,
        name="asset.preview.updated",
        scope=RealtimeScope(user_id=7, project_id=12, conversation_id="conversation-secret"),
    )

    assert topic.startswith("test-app:rt:v2:notify:asset.preview.updated:")
    assert "conversation-secret" not in topic
    assert "project_id" not in topic


def test_realtime_envelope_rejects_paths_and_token_like_values():
    # Token-like values are blocked anywhere in the payload (deep walk).
    with pytest.raises(ValueError):
        RealtimeEnvelope(
            kind=REALTIME_KIND_NOTIFY,
            name="asset.preview.updated",
            scope=RealtimeScope(user_id=7),
            resource=RealtimeResource(type="asset", id="sk-real-token"),
        ).to_payload()

    # Free-text reason is still strictly checked: no paths/URLs, no tokens.
    with pytest.raises(ValueError):
        RealtimeEnvelope(
            kind=REALTIME_KIND_NOTIFY,
            name="asset.preview.updated",
            scope=RealtimeScope(user_id=7),
            reason="sk-real-token",
        ).to_payload()

    with pytest.raises(ValueError):
        RealtimeEnvelope(
            kind=REALTIME_KIND_NOTIFY,
            name="asset.preview.updated",
            scope=RealtimeScope(user_id=7),
            reason="C:/secret/file.png",
        ).to_payload()


def test_realtime_envelope_allows_paths_in_non_reason_fields():
    # Resource ids/versions may legitimately contain `/` (e.g. object keys),
    # so the deep walk should not reject them outright.
    payload = RealtimeEnvelope(
        kind=REALTIME_KIND_NOTIFY,
        name="asset.preview.updated",
        scope=RealtimeScope(user_id=7),
        resource=RealtimeResource(type="asset", id="bucket/object/123.png", version="v1"),
    ).to_payload()

    assert payload["resource"]["id"] == "bucket/object/123.png"


def test_realtime_envelope_carries_sanitized_metadata():
    payload = RealtimeEnvelope(
        kind=REALTIME_KIND_NOTIFY,
        name="conversation.event.appended",
        scope=RealtimeScope(user_id=7, conversation_id="conversation-secret"),
        metadata={"lane": "user", "Bad Key!": "value"},
    ).to_payload()

    assert payload["metadata"] == {"lane": "user", "bad-key": "value"}


@pytest.mark.asyncio
async def test_realtime_publish_degrades_without_blocking_business_path():
    class FailingCoordinator:
        async def publish(self, *_args, **_kwargs):
            raise RuntimeError("redis unavailable")

    result = await publish_notification(
        "asset.preview.updated",
        scope=RealtimeScope(user_id=7),
        resource=RealtimeResource(type="asset", id="123", version="1"),
        reason="preview_ready",
        bus=RealtimeBus(FailingCoordinator(), namespace="test-app"),
    )

    assert result["published"] is False
    assert result["degraded"] is True
