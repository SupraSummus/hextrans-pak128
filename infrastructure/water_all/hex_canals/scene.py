"""The two canal tiers for the hex grid, painted like the roads.

A canal is a road tier's painted cross-section with water for the
carriageway: `CanalSurface` reuses `RoadSurface` (centreline field,
bands, junction bevels) and paints rippled water between banks, stone
for `canal_030` and earth and reeds for the older `canal_020`.  The bake
writes the same three atlases as a road (`tools/threed/way_bake.py`) and
the `.dat` image block of `road_030.dat`, without the double slopes a
canal never takes.

    python3 -m infrastructure.water_all.hex_canals.scene
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from infrastructure.roads.road_params import (
    CLEAN, SIDEWALK, ROADS_DIR, RoadParams, RoadSurface)
from tools.threed.building_kit import edit_dat
from tools.threed.way_bake import bake_way_atlases

WATER_DIR = Path(__file__).resolve().parent.parent
WATER = (56, 84, 124)

CANAL_020 = RoadParams(
    name="canal_020", surface="water", surface_color=WATER,
    half_w=0.3, verge=CLEAN,
)
CANAL_030 = RoadParams(
    name="canal_030", surface="water", surface_color=WATER,
    half_w=0.32, verge=SIDEWALK, verge_color=(150, 140, 124),
    verge_half_w=0.42,
)
EARTH = (122, 100, 70)
REED = (96, 120, 58)


class CanalSurface(RoadSurface):
    """Water between banks; no markings."""

    def _material(self, f, noise, *, junction):
        n1, n2, _ = noise
        rgb = np.empty(f.d.shape + (3,))
        rgb[:] = WATER
        # Ripples across the flow.
        ripple = np.sin(f.s * 60 + 3 * n1) > 0.85
        rgb *= (0.94 + 0.1 * n2)[:, None]
        rgb[ripple] *= 1.12
        # Darker deep water down the middle.
        rgb[np.abs(f.v) < self.params.half_w * 0.5] *= 0.92
        return rgb

    def _verge(self, f, noise, rgb):
        p = self.params
        if p.verge == SIDEWALK:
            keep = super()._verge(f, noise, rgb)
            # A coping stone along the water's edge.
            edge = (f.d >= p.half_w) & (f.d < p.half_w + 0.03)
            rgb[edge] = np.array((196, 188, 172)) * \
                (0.94 + 0.1 * noise[0][edge])[:, None]
            return keep
        # Earth bank, reeds along the water.
        n1, n2, n3 = noise
        bank = (f.d >= p.half_w - 0.04) & (f.d < p.half_w + 0.05)
        rgb[bank] = np.array(EARTH) * (0.85 + 0.3 * n1[bank])[:, None]
        reed = bank & (n3 > 0.55)
        rgb[reed] = np.array(REED) * (0.8 + 0.4 * n2[reed])[:, None]
        return f.d < p.half_w + 0.03 + 0.03 * n3

    def _markings(self, f, noise, rgb, legs):
        pass


def image_lines(name: str) -> list[str]:
    """`road_030.dat`'s hex image block for `name`, without the double
    slopes."""
    lines = []
    for line in (ROADS_DIR / "road_030.dat").read_text().splitlines():
        if not re.match(r"Image(Up)?\[[a-z_]+\]\[0\]=road_030_hex", line):
            continue
        if "double" in line:
            continue
        lines.append(line.replace("road_030_hex", f"{name}_hex"))
    return lines


IMAGE_LINE = re.compile(
    r"^\s*(Image|ImageUp|FrontImageUp|Diagonal|FrontDiagonal)\[", re.I)


def rewrite_dat(path: Path, name: str) -> None:
    """Replace the way's image lines, keeping `Image[-]`, the icon and
    the commented-out bridge."""
    def edit(lines):
        idx = {i for i, line in enumerate(lines)
               if IMAGE_LINE.match(line) and not line.startswith("Image[-]")}
        out = [line for i, line in enumerate(lines) if i not in idx]
        out[min(idx):min(idx)] = image_lines(name)
        return out
    edit_dat(path, edit)


def bake_pakset() -> None:
    for params in (CANAL_020, CANAL_030):
        bake_way_atlases(CanalSurface(params), out_dir=WATER_DIR,
                         name=params.name)
        rewrite_dat(WATER_DIR / f"{params.name}.dat", params.name)


if __name__ == "__main__":
    bake_pakset()
