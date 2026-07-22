from app.services.agent_harness.workspace.conversation.send_message_service import should_auto_resolve_main_skill


def test_should_auto_resolve_main_skill_allows_existing_plan_after_auto_reset():
    assert should_auto_resolve_main_skill(
        conversation={
            "id": "conv-1",
            "skill_id": None,
            "plan_state": {"title": "已有计划"},
        },
        effective_skill_selection_mode="auto",
        explicit_request_skill_id=False,
        turn_route={"route_kind": "artifact_revision", "requires_skill_selection": True},
    ) is True


def test_should_auto_resolve_main_skill_skips_true_informational_turn():
    assert should_auto_resolve_main_skill(
        conversation={"id": "conv-1", "skill_id": None},
        effective_skill_selection_mode="auto",
        explicit_request_skill_id=False,
        turn_route={"route_kind": "informational_turn", "requires_skill_selection": False},
    ) is False
