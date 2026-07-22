from __future__ import annotations

CANVAS_PREVIEW_WIDTHS = (256, 512, 1024, 2048)
CANVAS_TILE_SIZE = 256
CANVAS_TILE_QUALITY = 80
LIST_PREVIEW_WIDTH = 320


def get_canvas_preview_suffixes() -> tuple[str, ...]:
    return tuple(f"__canvas_{width}.webp" for width in CANVAS_PREVIEW_WIDTHS)
