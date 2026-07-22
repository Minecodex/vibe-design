from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CanvasTileGeometry:
    source_width: int
    source_height: int
    z: int
    x: int
    y: int
    tile_size: int
    scale: float
    level_width: int
    level_height: int
    columns: int
    rows: int
    tile_width: int
    tile_height: int
    source_left: int
    source_top: int
    source_width_crop: int
    source_height_crop: int


def build_canvas_tile_geometry(
    *,
    source_width: int,
    source_height: int,
    z: int,
    x: int,
    y: int,
    tile_size: int,
) -> CanvasTileGeometry | None:
    if source_width <= 0 or source_height <= 0:
        return None
    if z < 0 or x < 0 or y < 0 or tile_size <= 0:
        return None

    max_dimension = max(source_width, source_height)
    scale = min(1.0, (tile_size * (2 ** z)) / max_dimension)
    level_width = max(1, math.ceil(source_width * scale))
    level_height = max(1, math.ceil(source_height * scale))
    columns = max(1, math.ceil(level_width / tile_size))
    rows = max(1, math.ceil(level_height / tile_size))

    if x >= columns or y >= rows:
        return None

    level_left = x * tile_size
    level_top = y * tile_size
    tile_width = min(tile_size, level_width - level_left)
    tile_height = min(tile_size, level_height - level_top)

    source_left = math.floor(level_left / scale)
    source_top = math.floor(level_top / scale)
    source_right = min(source_width, math.ceil((level_left + tile_width) / scale))
    source_bottom = min(source_height, math.ceil((level_top + tile_height) / scale))

    return CanvasTileGeometry(
        source_width=source_width,
        source_height=source_height,
        z=z,
        x=x,
        y=y,
        tile_size=tile_size,
        scale=scale,
        level_width=level_width,
        level_height=level_height,
        columns=columns,
        rows=rows,
        tile_width=tile_width,
        tile_height=tile_height,
        source_left=source_left,
        source_top=source_top,
        source_width_crop=max(1, source_right - source_left),
        source_height_crop=max(1, source_bottom - source_top),
    )
