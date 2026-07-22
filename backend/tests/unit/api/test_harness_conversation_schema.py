from app.schemas.harness import HarnessConversationDetailRead


def test_harness_conversation_detail_exposes_model_preferences():
    detail = HarnessConversationDetailRead(
        id="conv-model-prefs",
        title="Model prefs",
        model_preferences={
            "image_model": "history-image",
            "image_provider": "builtin",
            "video_model": "history-video",
            "video_provider": "builtin",
            "multimodal_model": "history-chat",
            "multimodal_provider": "builtin",
            "auto": False,
        },
    )

    assert detail.model_dump()["model_preferences"] == {
        "image_model": "history-image",
        "image_provider": "builtin",
        "video_model": "history-video",
        "video_provider": "builtin",
        "multimodal_model": "history-chat",
        "multimodal_provider": "builtin",
        "auto": False,
    }
