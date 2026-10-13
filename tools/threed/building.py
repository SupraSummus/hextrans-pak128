"""Multi-tile buildings on the hex grid: one model, one image per tile.

A building `Dims=W,H` covers the axial tiles `(x, y)` for `x < W`,
`y < H` from its origin, the tile `BackImage[layout][y][x][h]` is
drawn on.  Each tile's image is the model clipped to that tile's hex
prism, drawn from the tile's centre.  The engine draws a southern tile
after a northern one that shares screen columns with it, which is the
order the camera sees the prisms in, so the clipped images composite
back into the whole model.  Heights stack one raster width apart.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .hex_synth import HexGeom
from .render import HexCamera, Model, render

SQRT3 = math.sqrt(3)
# Axial steps to the six neighbours.
NEIGHBOURS = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))
CLIMATE_PNG = (Path(__file__).resolve().parents[2]
               / "landscape/grounds/texture-climate.png")
TEMPERATE = 4  # climate index in texture-climate.dat
SKY = (231, 255, 255)


def tile_centre(x: int, y: int) -> tuple[float, float]:
    """World centre of axial tile `(x, y)`: +x is SE, +y is S."""
    return 1.5 * x, -SQRT3 * (x / 2 + y)


def footprint(dims: tuple[int, int]) -> list[tuple[int, int]]:
    return [(x, y) for y in range(dims[1]) for x in range(dims[0])]


def render_tiles(model: Model, dims: tuple[int, int], *, levels: int = 4,
                 **camera) -> dict[tuple[int, int], list[np.ndarray]]:
    """Per tile, the stack of cell images from the ground up, without
    empty cells on top.  The engine stops at the first empty height,
    so an empty cell under a drawn one is an error."""
    out = {}
    for x, y in footprint(dims):
        im = render(model, HexCamera(centre=tile_centre(x, y),
                                     levels=levels, **camera))
        w = im.shape[1]
        cells = [im[im.shape[0] - (h + 1) * w:im.shape[0] - h * w]
                 for h in range(levels)]
        drawn = [c[..., 3].any() for c in cells]
        n = max((h + 1 for h, d in enumerate(drawn) if d), default=0)
        if not all(drawn[:n]):
            raise ValueError(f"tile {(x, y)}: empty height under a drawn one")
        if drawn[-1]:
            raise ValueError(f"tile {(x, y)}: model reaches the top of "
                             f"{levels} levels; pass more")
        out[(x, y)] = cells[:n]
    return out


def ground_cell(geom: HexGeom) -> Image.Image:
    """Temperate grass cut to one hex, grown a pixel so neighbouring
    cells overlap instead of leaving gaps along the slanted edges."""
    climate = Image.open(CLIMATE_PNG).convert("RGBA")
    grass = climate.crop((TEMPERATE * 128, 0,
                          TEMPERATE * 128 + geom.w, geom.h))
    mask = Image.new("L", grass.size, 0)
    ImageDraw.Draw(mask).polygon(
        [(geom.vx[i], geom.vy_base[i]) for i in range(6)], fill=255)
    cell = Image.new("RGBA", grass.size, (0, 0, 0, 0))
    cell.paste(grass, (0, 0), mask.filter(ImageFilter.MaxFilter(3)))
    return cell


def composite(tiles, ground=None) -> Image.Image:
    """Cell stacks per axial tile, drawn as the engine draws them: back
    to front, heights a cell apart, on `ground` cells over the tiles and
    their neighbours.  For previews."""
    w = next(iter(tiles.values()))[0].shape[1]
    u = w // 4
    area = {(x + dx, y + dy) for x, y in tiles
            for dx, dy in ((0, 0),) + NEIGHBOURS}
    xs = [3 * u * x for x, y in area]
    ys = [u * x + 2 * u * y for x, y in area]
    top = max(len(c) for c in tiles.values()) * w
    ox, oy = -min(xs), -min(ys) + top
    canvas = Image.new("RGBA", (max(xs) + ox + w, max(ys) + oy + w),
                       SKY + (255,))
    order = sorted(area, key=lambda t: (t[0] + 2 * t[1], t[0]))
    if ground is not None:
        for x, y in order:
            canvas.alpha_composite(ground, (3 * u * x + ox,
                                            u * x + 2 * u * y + oy - w))
    for x, y in order:
        for h, cell in enumerate(tiles.get((x, y), [])):
            canvas.alpha_composite(Image.fromarray(cell),
                                   (3 * u * x + ox,
                                    u * x + 2 * u * y + oy - w - h * w))
    return canvas
