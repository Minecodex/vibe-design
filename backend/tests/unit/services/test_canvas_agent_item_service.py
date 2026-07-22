import pytest
from PIL import Image
from sqlalchemy import select

from app.models.project import Project
from app.models.project_asset import ProjectAsset
from app.models.project_user_canvas import ProjectUserCanvas
from app.models.user import User
from app.services.canvas_agent_item_service import CanvasAgentItemService


@pytest.mark.asyncio
async def test_agent_canvas_upsert_is_idempotent_by_agent_media_key(db_session):
    user = User(email="agent-canvas@example.com", username="agent_canvas", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    project = Project(user_id=user.id, title="Agent Canvas")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    service = CanvasAgentItemService(db_session)
    item = {
        "id": "agent-generated-one",
        "type": "image_generator",
        "task_id": "task-1",
        "artifact_ref": "artifact_ref:one",
        "agent_media_key": "artifact_ref:one",
        "agent_conversation_id": "conv-1",
        "status": "generating",
        "url": "",
    }

    first = await service.upsert_agent_generation_item(project, user.id, item, "generating")
    second = await service.upsert_agent_generation_item(project, user.id, item, "generating")

    canvas = await db_session.scalar(select(ProjectUserCanvas).where(ProjectUserCanvas.project_id == project.id))
    assert canvas is not None
    assert len(canvas.canvas_data) == 1
    assert canvas.canvas_data[0]["agent_media_key"] == "artifact_ref:one"
    assert second.canvas_revision == first.canvas_revision


@pytest.mark.asyncio
async def test_agent_canvas_completion_preserves_user_layout_and_syncs_asset(db_session):
    user = User(email="agent-complete@example.com", username="agent_complete", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    project = Project(user_id=user.id, title="Agent Complete")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    db_session.add(ProjectUserCanvas(
        project_id=project.id,
        user_id=user.id,
        canvas_revision=1,
        canvas_data=[{
            "id": "agent-generated-one",
            "type": "image_generator",
            "url": "",
            "x": 120,
            "y": 240,
            "width": 640,
            "height": 480,
            "z_index": 9,
            "groupId": "group-1",
            "task_id": "task-1",
            "artifact_ref": "artifact_ref:one",
            "agent_media_key": "artifact_ref:one",
            "agent_group_order": 3,
            "status": "generating",
        }],
        canvas_meta=None,
    ))
    await db_session.commit()

    result = await CanvasAgentItemService(db_session).upsert_agent_generation_item(
        project,
        user.id,
        {
            "id": "agent-generated-one",
            "type": "image",
            "task_id": "task-1",
            "artifact_ref": "artifact_ref:one",
            "agent_media_key": "artifact_ref:one",
            "status": "completed",
            "url": "/api/v1/uploads/canvas/1/final.png",
        },
        "completed",
        result_url="/api/v1/uploads/canvas/1/final.png",
    )

    assert result.canvas_item["type"] == "image"
    assert result.canvas_item["status"] == "completed"
    assert result.canvas_item["url"] == "/api/v1/uploads/canvas/1/final.png"
    assert result.canvas_item["x"] == 120
    assert result.canvas_item["y"] == 240
    assert result.canvas_item["width"] == 640
    assert result.canvas_item["height"] == 480
    assert result.canvas_item["z_index"] == 9
    assert result.canvas_item["groupId"] == "group-1"
    assert result.canvas_item["agent_group_order"] == 3
    asset = await db_session.scalar(select(ProjectAsset).where(ProjectAsset.canvas_item_id == "agent-generated-one"))
    assert asset is not None
    assert asset.url == "/api/v1/uploads/canvas/1/final.png"


@pytest.mark.asyncio
async def test_agent_canvas_completion_uses_actual_image_dimensions(db_session, tmp_path):
    user = User(email="agent-size@example.com", username="agent_size", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    project = Project(user_id=user.id, title="Agent Size")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    result_path = tmp_path / "references" / "generated" / "image.png"
    result_path.parent.mkdir(parents=True)
    Image.new("RGB", (1663, 945), color=(255, 255, 255)).save(result_path)

    db_session.add(ProjectUserCanvas(
        project_id=project.id,
        user_id=user.id,
        canvas_revision=1,
        canvas_data=[{
            "id": "agent-generated-sized",
            "type": "image_generator",
            "url": "",
            "x": 120,
            "y": 240,
            "width": 2880,
            "height": 2880,
            "media_display_size_source": "placeholder",
            "task_id": "task-sized",
            "artifact_ref": "artifact_ref:sized",
            "agent_media_key": "artifact_ref:sized",
            "status": "generating",
        }],
        canvas_meta=None,
    ))
    await db_session.commit()

    result = await CanvasAgentItemService(db_session).upsert_agent_generation_item(
        project,
        user.id,
        {
            "id": "agent-generated-sized",
            "type": "image",
            "task_id": "task-sized",
            "artifact_ref": "artifact_ref:sized",
            "agent_media_key": "artifact_ref:sized",
            "status": "completed",
            "url": "references/generated/image.png",
        },
        "completed",
        result_url="references/generated/image.png",
        workspace_root=tmp_path,
    )

    assert result.canvas_item["width"] == 1663
    assert result.canvas_item["height"] == 945
    assert result.canvas_item["media_display_size_source"] == "intrinsic"
    assert result.canvas_item["x"] == 120
    assert result.canvas_item["y"] == 240


@pytest.mark.asyncio
async def test_agent_canvas_completion_keeps_user_resized_dimensions(db_session, tmp_path):
    user = User(email="agent-user-size@example.com", username="agent_user_size", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    project = Project(user_id=user.id, title="Agent User Size")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    result_path = tmp_path / "references" / "generated" / "image.png"
    result_path.parent.mkdir(parents=True)
    Image.new("RGB", (1663, 945), color=(255, 255, 255)).save(result_path)

    db_session.add(ProjectUserCanvas(
        project_id=project.id,
        user_id=user.id,
        canvas_revision=1,
        canvas_data=[{
            "id": "agent-generated-user-sized",
            "type": "image_generator",
            "url": "",
            "x": 120,
            "y": 240,
            "width": 400,
            "height": 300,
            "media_display_size_source": "user",
            "task_id": "task-user-sized",
            "artifact_ref": "artifact_ref:user-sized",
            "agent_media_key": "artifact_ref:user-sized",
            "status": "generating",
        }],
        canvas_meta=None,
    ))
    await db_session.commit()

    result = await CanvasAgentItemService(db_session).upsert_agent_generation_item(
        project,
        user.id,
        {
            "id": "agent-generated-user-sized",
            "type": "image",
            "task_id": "task-user-sized",
            "artifact_ref": "artifact_ref:user-sized",
            "agent_media_key": "artifact_ref:user-sized",
            "status": "completed",
            "url": "references/generated/image.png",
        },
        "completed",
        result_url="references/generated/image.png",
        workspace_root=tmp_path,
    )

    assert result.canvas_item["width"] == 400
    assert result.canvas_item["height"] == 300
    assert result.canvas_item["media_display_size_source"] == "user"


@pytest.mark.asyncio
async def test_agent_canvas_groups_multiple_images_by_group_key(db_session):
    user = User(email="agent-group@example.com", username="agent_group", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    project = Project(user_id=user.id, title="Agent Group")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    service = CanvasAgentItemService(db_session)

    last_result = None
    for index in range(3):
        last_result = await service.upsert_agent_generation_item(
            project,
            user.id,
            {
                "id": f"agent-generated-{index}",
                "type": "image_generator",
                "task_id": f"task-{index}",
                "artifact_ref": f"artifact_ref:{index}",
                "agent_media_key": f"artifact_ref:{index}",
                "agent_group_key": "ecommerce_white_background",
                "agent_conversation_id": "conv-1",
                "status": "generating",
                "url": "",
            },
            "generating",
        )

    canvas = await db_session.scalar(select(ProjectUserCanvas).where(ProjectUserCanvas.project_id == project.id))
    groups = [item for item in canvas.canvas_data if item["type"] == "group"]
    images = [item for item in canvas.canvas_data if item["type"] != "group"]
    assert len(groups) == 1
    assert groups[0]["group_layout_mode"] == "agent_grid"
    assert [item["groupId"] for item in images] == [groups[0]["id"]] * 3
    assert [item["agent_group_order"] for item in images] == [0, 1, 2]
    third = next(item for item in images if item["id"] == "agent-generated-2")
    assert last_result.canvas_item["x"] == third["x"]
    assert last_result.canvas_item["groupId"] == groups[0]["id"]


@pytest.mark.asyncio
async def test_agent_canvas_explicit_group_key_crosses_messages(db_session):
    user = User(email="agent-explicit-group@example.com", username="agent_explicit_group", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    project = Project(user_id=user.id, title="Agent Explicit Group")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    service = CanvasAgentItemService(db_session)

    for index, message_id in enumerate(["message-1", "message-2"]):
        await service.upsert_agent_generation_item(
            project,
            user.id,
            {
                "id": f"agent-generated-cross-message-{index}",
                "type": "image_generator",
                "task_id": f"task-cross-{index}",
                "artifact_ref": f"artifact_ref:cross-{index}",
                "agent_media_key": f"artifact_ref:cross-{index}",
                "agent_group_key": "explicit-pack",
                "agent_conversation_id": "conv-1",
                "agent_message_id": message_id,
                "status": "generating",
                "url": "",
            },
            "generating",
        )

    canvas = await db_session.scalar(select(ProjectUserCanvas).where(ProjectUserCanvas.project_id == project.id))
    groups = [item for item in canvas.canvas_data if item["type"] == "group"]
    images = [item for item in canvas.canvas_data if item["type"] != "group"]
    assert len(groups) == 1
    assert {item["agent_message_id"] for item in images} == {"message-1", "message-2"}
    assert {item["groupId"] for item in images} == {groups[0]["id"]}


@pytest.mark.asyncio
async def test_agent_canvas_deleted_key_wins(db_session):
    user = User(email="agent-delete@example.com", username="agent_delete", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    project = Project(user_id=user.id, title="Agent Delete")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    db_session.add(ProjectUserCanvas(
        project_id=project.id,
        user_id=user.id,
        canvas_revision=2,
        canvas_data=[],
        canvas_meta={"id": "global_state", "deletedAgentMediaKeys": ["artifact_ref:deleted"]},
    ))
    await db_session.commit()

    result = await CanvasAgentItemService(db_session).upsert_agent_generation_item(
        project,
        user.id,
        {
            "id": "agent-generated-deleted",
            "type": "image",
            "task_id": "task-deleted",
            "artifact_ref": "artifact_ref:deleted",
            "agent_media_key": "artifact_ref:deleted",
            "status": "completed",
            "url": "/api/v1/uploads/canvas/1/deleted.png",
        },
        "completed",
        result_url="/api/v1/uploads/canvas/1/deleted.png",
    )

    canvas = await db_session.scalar(select(ProjectUserCanvas).where(ProjectUserCanvas.project_id == project.id))
    assert result.canvas_item is None
    assert canvas.canvas_data == []
