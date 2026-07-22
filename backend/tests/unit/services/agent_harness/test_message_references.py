import pytest

from app.services.agent_harness.references import InvalidMessageReferenceError, resolve_upload_attachment_references
from app.services.agent_harness.references import resolve_message_references


def test_resolve_upload_attachment_references_resolves_safe_upload_path():
    references = [
        {
            "id": "safe",
            "kind": "upload_attachment",
            "media_type": "image",
            "source": {"type": "harness_input", "path": "references/inputs/upload_001/source.png"},
        },
    ]

    resolved = resolve_upload_attachment_references(
        references,
        attachments=[
            {
                "type": "image",
                "url": "references/inputs/upload_001/source.png",
                "name": "source.png",
            }
        ],
    )

    assert [item["id"] for item in resolved] == ["safe"]
    assert resolved[0]["tool_reference"] == "references/inputs/upload_001/source.png"


@pytest.mark.parametrize(
    "reference",
    [
        {
            "id": "traversal",
            "kind": "upload_attachment",
            "media_type": "image",
            "source": {"type": "harness_input", "path": "references/inputs/../secret.png"},
        },
        {
            "id": "unattached",
            "kind": "upload_attachment",
            "media_type": "image",
            "source": {"type": "harness_input", "path": "references/inputs/upload_999/source.png"},
        },
    ],
)
def test_resolve_upload_attachment_references_rejects_unsafe_or_unattached_paths(reference):
    with pytest.raises(InvalidMessageReferenceError):
        resolve_upload_attachment_references(
            [reference],
            attachments=[
                {
                    "type": "image",
                    "url": "references/inputs/upload_001/source.png",
                    "name": "source.png",
                }
            ],
        )


def test_resolve_message_references_resolves_home_asset_and_workspace_file_references():
    resolved = resolve_message_references(
        [
            {
                "id": "home-asset:https://cdn.example.com/library.png",
                "kind": "home_asset",
                "media_type": "image",
                "display_name": "library.png",
                "source": {
                    "type": "home_asset",
                    "url": "https://cdn.example.com/library.png",
                },
            },
            {
                "id": "workspace-file:references/generated/generated_image_001/original.png",
                "kind": "workspace_file",
                "media_type": "image",
                "display_name": "generated.png",
                "source": {
                    "type": "workspace_file",
                    "path": "references/generated/generated_image_001/original.png",
                },
            },
        ],
        attachments=[
            {
                "type": "image",
                "url": "https://cdn.example.com/library.png",
                "name": "library.png",
            },
            {
                "type": "image",
                "url": "references/generated/generated_image_001/original.png",
                "name": "generated.png",
            },
        ],
    )

    assert resolved == [
        {
            "id": "home-asset:https://cdn.example.com/library.png",
            "kind": "home_asset",
            "media_type": "image",
            "display_name": "library.png",
            "tool_reference": "https://cdn.example.com/library.png",
            "source": {
                "type": "home_asset",
                "url": "https://cdn.example.com/library.png",
            },
        },
        {
            "id": "workspace-file:references/generated/generated_image_001/original.png",
            "kind": "workspace_file",
            "media_type": "image",
            "display_name": "generated.png",
            "tool_reference": "references/generated/generated_image_001/original.png",
            "source": {
                "type": "workspace_file",
                "path": "references/generated/generated_image_001/original.png",
            },
        },
    ]


@pytest.mark.parametrize(
    "reference",
    [
        {
            "id": "home-asset:missing",
            "kind": "home_asset",
            "source": {"type": "home_asset", "url": "https://cdn.example.com/missing.png"},
        },
        {
            "id": "workspace-file:traversal",
            "kind": "workspace_file",
            "source": {"type": "workspace_file", "path": "references/generated/../secret.png"},
        },
    ],
)
def test_resolve_message_references_rejects_invalid_home_references(reference):
    with pytest.raises(InvalidMessageReferenceError):
        resolve_message_references(
            [reference],
            attachments=[
                {
                    "type": "image",
                    "url": "https://cdn.example.com/library.png",
                    "name": "library.png",
                }
            ],
        )


def test_resolve_message_references_resolves_canvas_local_upload_item():
    resolved = resolve_message_references(
        [
            {
                "id": "canvas:img-local-1",
                "kind": "canvas_item",
                "media_type": "image",
                "display_name": "本地上传图",
                "source": {"type": "canvas_item", "item_id": "canvas:img-local-1"},
            }
        ],
        canvas_items=[
            {
                "id": "img-local-1",
                "type": "image",
                "name": "本地上传图",
                "url": "/api/v1/uploads/canvas/88/source.png",
                "asset_origin": "local_upload",
            }
        ],
        project_id=88,
    )

    assert resolved == [
        {
            "id": "canvas:img-local-1",
            "kind": "canvas_item",
            "media_type": "image",
            "display_name": "本地上传图",
            "tool_reference": "/api/v1/uploads/canvas/88/source.png",
            "source": {
                "type": "canvas_item",
                "item_id": "img-local-1",
            },
        }
    ]


def test_resolve_message_references_prefers_canvas_generated_artifact_ref_over_url():
    resolved = resolve_message_references(
        [
            {
                "id": "canvas:generated-1",
                "kind": "canvas_item",
                "media_type": "image",
                "display_name": "生成图",
                "source": {"type": "canvas_item", "item_id": "generated-1"},
            }
        ],
        canvas_items=[
            {
                "id": "generated-1",
                "type": "image",
                "name": "生成图",
                "url": "/api/v1/uploads/canvas/88/generated-preview.png",
                "asset_origin": "ai_generated",
                "artifact_ref": "artifact_ref:generated-image-1",
            }
        ],
        project_id=88,
    )

    assert resolved == [
        {
            "id": "canvas:generated-1",
            "kind": "canvas_item",
            "media_type": "image",
            "display_name": "生成图",
            "tool_reference": "artifact_ref:generated-image-1",
            "source": {
                "type": "canvas_item",
                "item_id": "generated-1",
                "origin": "generated_artifact",
                "artifact_ref": "artifact_ref:generated-image-1",
            },
        }
    ]


def test_resolve_message_references_falls_back_to_canvas_url_when_artifact_ref_is_unavailable():
    resolved = resolve_message_references(
        [
            {
                "id": "canvas:generated-1",
                "kind": "canvas_item",
                "media_type": "image",
                "display_name": "生成图",
                "source": {"type": "canvas_item", "item_id": "generated-1"},
            }
        ],
        canvas_items=[
            {
                "id": "generated-1",
                "type": "image",
                "name": "生成图",
                "url": "/api/v1/uploads/canvas/88/generated-preview.png",
                "asset_origin": "ai_generated",
                "artifact_ref": "artifact_ref:missing-image-1",
            }
        ],
        project_id=88,
        is_artifact_reference_available=lambda _artifact_ref: False,
    )

    assert resolved == [
        {
            "id": "canvas:generated-1",
            "kind": "canvas_item",
            "media_type": "image",
            "display_name": "生成图",
            "tool_reference": "/api/v1/uploads/canvas/88/generated-preview.png",
            "source": {
                "type": "canvas_item",
                "item_id": "generated-1",
                "origin": "canvas_url_fallback",
            },
        }
    ]


def test_resolve_message_references_keeps_canvas_artifact_ref_when_available():
    resolved = resolve_message_references(
        [
            {
                "id": "canvas:generated-1",
                "kind": "canvas_item",
                "media_type": "image",
                "display_name": "生成图",
                "source": {"type": "canvas_item", "item_id": "generated-1"},
            }
        ],
        canvas_items=[
            {
                "id": "generated-1",
                "type": "image",
                "name": "生成图",
                "url": "/api/v1/uploads/canvas/88/generated-preview.png",
                "asset_origin": "ai_generated",
                "artifact_ref": "artifact_ref:generated-image-1",
            }
        ],
        project_id=88,
        is_artifact_reference_available=lambda artifact_ref: artifact_ref == "artifact_ref:generated-image-1",
    )

    assert resolved[0]["tool_reference"] == "artifact_ref:generated-image-1"
    assert resolved[0]["source"]["artifact_ref"] == "artifact_ref:generated-image-1"


def test_resolve_message_references_resolves_canvas_mark_source_image():
    resolved = resolve_message_references(
        [
            {
                "id": "canvas-mark:mark-1",
                "kind": "canvas_mark",
                "media_type": "image",
                "display_name": "葡萄",
                "source": {
                    "type": "canvas_mark",
                    "mark_id": "mark-1",
                    "image_item_id": "img-local-1",
                },
                "mark": {
                    "id": "mark-1",
                    "image_item_id": "img-local-1",
                    "number": 1,
                    "label": "葡萄",
                    "position": {"x": 0.42, "y": 0.61},
                },
            }
        ],
        canvas_items=[
            {
                "id": "img-local-1",
                "type": "image",
                "name": "本地上传图",
                "url": "/api/v1/uploads/canvas/88/source.png",
                "asset_origin": "local_upload",
            }
        ],
        project_id=88,
    )

    assert resolved == [
        {
            "id": "canvas-mark:mark-1",
            "kind": "canvas_mark",
            "media_type": "image",
            "display_name": "葡萄",
            "tool_reference": "/api/v1/uploads/canvas/88/source.png",
            "source": {
                "type": "canvas_mark",
                "mark_id": "mark-1",
                "image_item_id": "img-local-1",
                "image_source": {
                    "type": "canvas_item",
                    "item_id": "img-local-1",
                },
            },
            "mark": {
                "id": "mark-1",
                "image_item_id": "img-local-1",
                "number": 1,
                "label": "葡萄",
                "position": {"x": 0.42, "y": 0.61},
            },
        }
    ]


def test_resolve_message_references_rejects_canvas_mark_not_present_in_final_content():
    with pytest.raises(InvalidMessageReferenceError):
        resolve_message_references(
            [
                {
                    "id": "canvas-mark:mark-1",
                    "kind": "canvas_mark",
                    "media_type": "image",
                    "display_name": "葡萄",
                    "source": {
                        "type": "canvas_mark",
                        "mark_id": "mark-1",
                        "image_item_id": "img-local-1",
                    },
                    "mark": {
                        "id": "mark-1",
                        "image_item_id": "img-local-1",
                        "number": 1,
                        "label": "葡萄",
                        "position": {"x": 0.42, "y": 0.61},
                    },
                }
            ],
            canvas_items=[
                {
                    "id": "img-local-1",
                    "type": "image",
                    "url": "/api/v1/uploads/canvas/88/source.png",
                    "asset_origin": "local_upload",
                }
            ],
            project_id=88,
            content="只调整这一串葡萄",
        )


def test_resolve_message_references_accepts_canvas_mark_present_in_new_token_content():
    resolved = resolve_message_references(
        [
            {
                "id": "canvas-mark:mark-1",
                "kind": "canvas_mark",
                "media_type": "image",
                "display_name": "葡萄",
                "source": {
                    "type": "canvas_mark",
                    "mark_id": "mark-1",
                    "image_item_id": "img-local-1",
                },
                "mark": {
                    "id": "mark-1",
                    "image_item_id": "img-local-1",
                    "number": 1,
                    "label": "葡萄",
                    "position": {"x": 0.42, "y": 0.61},
                },
            }
        ],
        canvas_items=[
            {
                "id": "img-local-1",
                "type": "image",
                "url": "/api/v1/uploads/canvas/88/source.png",
                "asset_origin": "local_upload",
            }
        ],
        project_id=88,
        content="只调整 #[葡萄](canvas-mark:mark-1:image:img-local-1:x:0.42:y:0.61)",
    )

    assert resolved[0]["tool_reference"] == "/api/v1/uploads/canvas/88/source.png"


@pytest.mark.parametrize(
    "reference",
    [
        {
            "id": "canvas-mark:missing-mark",
            "kind": "canvas_mark",
            "source": {"type": "canvas_mark", "mark_id": "", "image_item_id": "img-local-1"},
            "mark": {"id": "", "image_item_id": "img-local-1", "number": 1, "position": {"x": 0.5, "y": 0.5}},
        },
        {
            "id": "canvas-mark:mismatch",
            "kind": "canvas_mark",
            "source": {"type": "canvas_mark", "mark_id": "mark-1", "image_item_id": "img-local-1"},
            "mark": {"id": "mark-1", "image_item_id": "other-image", "number": 1, "position": {"x": 0.5, "y": 0.5}},
        },
        {
            "id": "canvas-mark:bad-position",
            "kind": "canvas_mark",
            "source": {"type": "canvas_mark", "mark_id": "mark-1", "image_item_id": "img-local-1"},
            "mark": {"id": "mark-1", "image_item_id": "img-local-1", "number": 1, "position": {"x": 1.5, "y": 0.5}},
        },
    ],
)
def test_resolve_message_references_rejects_invalid_canvas_mark_references(reference):
    with pytest.raises(InvalidMessageReferenceError):
        resolve_message_references(
            [reference],
            canvas_items=[
                {
                    "id": "img-local-1",
                    "type": "image",
                    "url": "/api/v1/uploads/canvas/88/source.png",
                    "asset_origin": "local_upload",
                }
            ],
            project_id=88,
        )


@pytest.mark.parametrize(
    "canvas_items",
    [
        [],
        [{"id": "img-local-1", "type": "image", "url": "/api/v1/uploads/canvas/89/source.png"}],
        [{"id": "img-local-1", "type": "image", "url": "/api/v1/uploads/canvas/88/../secret.png"}],
    ],
)
def test_resolve_message_references_rejects_invalid_canvas_item_references(canvas_items):
    with pytest.raises(InvalidMessageReferenceError):
        resolve_message_references(
            [
                {
                    "id": "canvas:img-local-1",
                    "kind": "canvas_item",
                    "media_type": "image",
                    "source": {"type": "canvas_item", "item_id": "img-local-1"},
                }
            ],
            canvas_items=canvas_items,
            project_id=88,
        )
