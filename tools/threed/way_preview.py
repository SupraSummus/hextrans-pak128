#!/usr/bin/env python3
"""Contact sheet of way tiers: hex bake laid out as a small network on
grass, next to the tier's legacy pak128 cells.

    python3 -m tools.threed.way_preview infrastructure/roads \
        road_030 road_040 ... -o sheet.png

Each row is one tier.  Left: the legacy square cells named in
`LEGACY_CELLS` (straight, curve, crossing).  Right: the tier's
`<name>_hex.png` cells composited onto temperate ground in the same
draw order the engine uses (back to front), so tile-to-tile joins,
bends of both angles and junctions are visible at once.  The point is
comparing tiers with each other and with pak128, not checking one
cell, so every row shares the same network.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .building import SKY, composite, ground_cell
from .hex_synth import HexGeom

# Hex directions in `.dat` key order; axial offsets with +q = SE, +r = S.
DIRS = ("se", "s", "sw", "nw", "n", "ne")
STEP = {"se": (1, 0), "s": (0, 1), "sw": (-1, 1),
        "nw": (-1, 0), "n": (0, -1), "ne": (1, -1)}

# Paths of consecutive tiles; ways connect along each path only, as
# built in game (a side branch on hex touches two spine tiles, so
# connecting by adjacency would invent junctions).  Covers straights,
# both bend angles, a 4-way and a 3-way junction, and dead ends.
NETWORK = [
    [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)],      # N-S spine
    [(-1, 2), (0, 2)],                             # 4-way at (0, 2)
    [(0, 2), (1, 2), (2, 2), (3, 1), (3, 0)],      # gentle bends
    [(2, 2), (2, 3)],                              # 3-way at (2, 2)
    [(0, 4), (-1, 5), (-2, 5), (-2, 6)],           # gentle + sharp bend
]

# Legacy square cells per tier sheet: straight, curve, crossing.
LEGACY_CELLS = ((1, 5), (2, 5), (1, 7))


def dat_cells(dat: Path, png_stem: str) -> dict[str, tuple[int, int]]:
    """`Image[<ribi>]` → (row, col) in `<png_stem>.png`, from the .dat."""
    cells = {}
    for line in dat.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("Image[") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        if not val.startswith(png_stem + "."):
            continue
        ribi = key[len("Image["):key.index("]")]
        row, col = val[len(png_stem) + 1:].split(".")[:2]
        cells.setdefault(ribi, (int(row), int(col)))
    return cells


def _network_ribis() -> dict[tuple[int, int], set[str]]:
    by_step = {v: k for k, v in STEP.items()}
    ribis: dict[tuple[int, int], set[str]] = {}
    for path in NETWORK:
        for a, b in zip(path, path[1:]):
            d = by_step[(b[0] - a[0], b[1] - a[1])]
            back = by_step[(a[0] - b[0], a[1] - b[1])]
            ribis.setdefault(a, set()).add(d)
            ribis.setdefault(b, set()).add(back)
    return ribis


def render_network(atlas: Image.Image, cells: dict, geom: HexGeom,
                   ground: Image.Image) -> Image.Image:
    tiles = {}
    for (q, r), ribi in _network_ribis().items():
        key = "_".join(d for d in DIRS if d in ribi)
        if key in cells:
            row, col = cells[key]
            tiles[(q, r)] = [np.asarray(atlas.crop((
                col * geom.w, row * geom.h,
                (col + 1) * geom.w, (row + 1) * geom.h)))]
    return composite(tiles, ground)


def legacy_strip(png: Path) -> Image.Image | None:
    if not png.exists():
        return None
    im = Image.open(png).convert("RGB")
    out = Image.new("RGB", (128 * len(LEGACY_CELLS), 96), SKY)
    for i, (r, c) in enumerate(LEGACY_CELLS):
        cell = im.crop((c * 128, r * 128 + 32, c * 128 + 128, r * 128 + 128))
        # pak128 key colour (231, 255, 255) already matches SKY.
        out.paste(cell, (i * 128, 0))
    return out


def build_sheet(way_dir: Path, names: list[str]) -> Image.Image:
    geom = HexGeom()
    ground = ground_cell(geom)

    rows = []
    for name in names:
        dat = way_dir / f"{name}.dat"
        atlas = Image.open(way_dir / f"{name}_hex.png").convert("RGBA")
        net = render_network(atlas, dat_cells(dat, f"{name}_hex"),
                             geom, ground)
        legacy = legacy_strip(way_dir / f"{name}.png")
        rows.append((name, legacy, net))

    lw = 128 * len(LEGACY_CELLS)
    nw = max(n.width for _, _, n in rows)
    nh = max(n.height for _, _, n in rows)
    sheet = Image.new("RGB", (lw + nw + 24, len(rows) * (nh + 20)), SKY)
    d = ImageDraw.Draw(sheet)
    for i, (name, legacy, net) in enumerate(rows):
        y = i * (nh + 20)
        d.text((4, y + 2), name, fill=(0, 0, 0))
        if legacy is not None:
            sheet.paste(legacy, (0, y + 20 + (nh - 96) // 2))
        sheet.paste(net.convert("RGB"), (lw + 24, y + 20))
    return sheet


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("way_dir", type=Path)
    ap.add_argument("names", nargs="+")
    ap.add_argument("-o", "--out", type=Path, default=Path("way_preview.png"))
    ap.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args()
    sheet = build_sheet(a.way_dir, a.names)
    if a.scale != 1.0:
        sheet = sheet.resize((int(sheet.width * a.scale),
                              int(sheet.height * a.scale)), Image.NEAREST)
    sheet.save(a.out)


if __name__ == "__main__":
    main()
