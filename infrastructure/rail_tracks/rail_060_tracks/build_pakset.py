#!/usr/bin/env python3
"""Bake the hex-axis rail_060_tracks pair sprites into a pakset atlas.

Bespoke-pipeline counterpart to the parametric `landscape/grounds/*`
bakers.  Renders the hex pair-direction sprites listed in
`scene.HEX_ENTRIES` (single source of truth — also drives the per-cell
preview side-effect below), packs them column-by-column into a 128 px
atlas, and writes it next to the upstream sheet.  Each cell is rendered
exactly once: the rgba buffer is pasted into the atlas and saved
to `out_hex_<ribi>.png` for reviewer-visible per-cell debug.

The per-direction `Image[<ribi>][0]` and `Image[<ribi>][1]` lines in
`rail_060_tracks.dat` are repointed at this file (winter shares the
summer cells until a hex winter palette lands).  Single-edge stubs,
the no-track `Image[-]`, `ImageUp` slope variants, the icon and the
cursor still reference upstream `rail_060_tracks.png` — see TODO.md
"Track-sprite baker".

Output: `infrastructure/rail_tracks/rail_060_tracks_hex.png` (RGBA;
matches the parametric ground bakers' format).  Re-running this script
must produce a byte-identical PNG.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "3d"))

import scene as scene_mod  # noqa: E402  # adjacent file


CELL = 128


def main() -> None:
    n = len(scene_mod.HEX_ENTRIES)
    atlas = np.zeros((CELL, CELL * n, 4), dtype=np.uint8)
    for col, (ribi, edge_a, edge_b) in enumerate(scene_mod.HEX_ENTRIES):
        rgba = scene_mod.render_hex_cell(edge_a, edge_b)
        if rgba.shape != (CELL, CELL, 4):
            raise RuntimeError(
                f"unexpected hex cell shape {rgba.shape} for {ribi} "
                f"(want ({CELL},{CELL},4))")
        atlas[:, col * CELL:(col + 1) * CELL] = rgba
        Image.fromarray(rgba, mode="RGBA").save(HERE / f"out_hex_{ribi}.png")

    out_png = HERE.parent / "rail_060_tracks_hex.png"
    Image.fromarray(atlas, mode="RGBA").save(out_png)
    print(f"wrote {out_png.relative_to(REPO_ROOT)} "
          f"({atlas.shape[1]}x{atlas.shape[0]} px, {n} cells)")
    for col, (ribi, *_e) in enumerate(scene_mod.HEX_ENTRIES):
        print(f"  col {col}: {ribi}")


if __name__ == "__main__":
    main()
