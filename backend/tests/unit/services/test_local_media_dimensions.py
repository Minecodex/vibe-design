from PIL import Image

from app.services.local_media_dimensions import (
    read_local_image_dimensions,
    resolve_local_media_path,
)


def test_read_local_image_dimensions_resolves_upload_url_under_configured_root(tmp_path):
    uploads_root = tmp_path / "uploads"
    image_path = uploads_root / "canvas" / "7" / "result.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (321, 123), color=(255, 255, 255)).save(image_path)

    dimensions = read_local_image_dimensions(
        "/api/v1/uploads/canvas/7/result.png",
        uploads_root=uploads_root,
    )

    assert dimensions == (321, 123)


def test_read_local_image_dimensions_resolves_absolute_path_under_upload_root(tmp_path):
    uploads_root = tmp_path / "uploads"
    image_path = uploads_root / "canvas" / "7" / "absolute.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (640, 480), color=(255, 255, 255)).save(image_path)

    dimensions = read_local_image_dimensions(
        str(image_path),
        uploads_root=uploads_root,
    )

    assert dimensions == (640, 480)


def test_read_local_image_dimensions_resolves_workspace_relative_path(tmp_path):
    image_path = tmp_path / "references" / "generated" / "image.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (1663, 945), color=(255, 255, 255)).save(image_path)

    dimensions = read_local_image_dimensions(
        "references/generated/image.png",
        workspace_root=tmp_path,
    )

    assert dimensions == (1663, 945)


def test_resolve_local_media_path_rejects_upload_traversal(tmp_path):
    uploads_root = tmp_path / "uploads"
    uploads_root.mkdir()
    outside_path = tmp_path / "secret.png"
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(outside_path)

    resolved = resolve_local_media_path(
        "/api/v1/uploads/../secret.png",
        uploads_root=uploads_root,
    )

    assert resolved is None
