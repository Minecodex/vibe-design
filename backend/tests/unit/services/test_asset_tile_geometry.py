from app.services.asset_tile_geometry import build_canvas_tile_geometry


def test_canvas_tile_geometry_scales_from_single_overview_tile_to_level_tiles():
    overview = build_canvas_tile_geometry(
        source_width=1024,
        source_height=512,
        z=0,
        x=0,
        y=0,
        tile_size=256,
    )
    assert overview is not None
    assert overview.scale == 0.25
    assert overview.level_width == 256
    assert overview.level_height == 128
    assert overview.columns == 1
    assert overview.rows == 1
    assert overview.source_width_crop == 1024
    assert overview.source_height_crop == 512

    tile = build_canvas_tile_geometry(
        source_width=1024,
        source_height=512,
        z=2,
        x=3,
        y=1,
        tile_size=256,
    )
    assert tile is not None
    assert tile.scale == 1.0
    assert tile.columns == 4
    assert tile.rows == 2
    assert tile.source_left == 768
    assert tile.source_top == 256
    assert tile.source_width_crop == 256
    assert tile.source_height_crop == 256


def test_canvas_tile_geometry_rejects_out_of_range_coordinates():
    assert build_canvas_tile_geometry(
        source_width=1024,
        source_height=512,
        z=1,
        x=2,
        y=0,
        tile_size=256,
    ) is None
    assert build_canvas_tile_geometry(
        source_width=1024,
        source_height=512,
        z=-1,
        x=0,
        y=0,
        tile_size=256,
    ) is None
