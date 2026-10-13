#!/usr/bin/env python3
"""A pak128 building as the square engine drew it, stitched from its
tiles: the reference to judge a hex port against.

    python3 -m tools.threed.square_stitch \\
        special_buildings/townhalls/city-townhalls-128.dat 03_CITY \\
        --rev main --png-dir special_buildings/townhalls/src -o ref.png

`--rev` reads the `.dat` from git, since a hex bake rewrites its image
lines; `--png-dir` is where the square sheets live now.  Image keys
are `BackImage[layout][y][x][height][phase][season]`: tile `(x, y)`
sits at screen `((x - y)·64, (x + y)·32)` and each height 128 px
higher.  Draws layout 0, phase 0, season 0, front images included.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

KEY = (231, 255, 255)
IMAGE = re.compile(r"^(Back|Front)Image((?:\[\d+\])+)=(\S+)", re.I)


def _block(dat: str, name: str) -> list[str]:
    for block in re.split(r"^-{3,}.*$", dat, flags=re.M):
        if re.search(rf"^Name={re.escape(name)}\s*$", block, re.M | re.I):
            return block.splitlines()
    raise SystemExit(f"Name={name} not in .dat")


def stitch(dat: str, name: str, png_dir: Path) -> Image.Image:
    layers = []
    for line in _block(dat, name):
        m = IMAGE.match(line.strip())
        if not m or m.group(3) == "-":
            continue
        idx = [int(i) for i in re.findall(r"\d+", m.group(2))] + [0, 0]
        layout, y, x, h, phase, season = idx[:6]
        if layout or phase or season:
            continue
        front = m.group(1).lower() == "front"
        layers.append(((x + y, h, front), (x, y, h), m.group(3)))
    n = 1 + max(max(t[1][0], t[1][1]) for t in layers)
    top = 128 * (1 + max(t[1][2] for t in layers))
    canvas = Image.new("RGBA", (128 * (2 * n), top + 64 * n), (0, 0, 0, 0))
    for _, (x, y, h), ref in sorted(layers):
        png, row, col = ref.rsplit(".", 2)
        sheet = np.asarray(Image.open(png_dir / f"{Path(png).name}.png")
                           .convert("RGBA"))
        r, c = int(row) * 128, int(col) * 128
        cell = sheet[r:r + 128, c:c + 128].copy()
        cell[(cell[..., :3] == KEY).all(-1), 3] = 0
        canvas.alpha_composite(Image.fromarray(cell),
                               (64 * (n - 1) + (x - y) * 64,
                                top - 128 + (x + y) * 32 - 128 * h))
    return canvas.crop(canvas.getbbox())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dat", type=Path)
    ap.add_argument("name")
    ap.add_argument("--rev", help="read the .dat at this git revision")
    ap.add_argument("--png-dir", type=Path)
    ap.add_argument("-o", "--out", type=Path, required=True)
    a = ap.parse_args()
    if a.rev:
        dat = subprocess.run(["git", "show", f"{a.rev}:./{a.dat}"],
                             capture_output=True, text=True,
                             check=True).stdout
    else:
        dat = a.dat.read_text(errors="replace")
    stitch(dat, a.name, a.png_dir or a.dat.parent).save(a.out)


if __name__ == "__main__":
    main()
