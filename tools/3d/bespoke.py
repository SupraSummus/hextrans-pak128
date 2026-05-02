"""Shared plumbing for bespoke 3D assets (vehicles, bridges, buildings, …).

Counterpart to `hex_synth.bake_pakset`, which is specific to slope-keyed
parametric ground bakers (`Obj=ground` .dat header, `Image[<slope>][k]`
keys).  Bespoke assets ship a hand-written .dat that already references
sheet cells by row/col; the renderer's job is just to compose
per-entry RGBA renders into a flat one-row atlas the .dat points at.

A scene file's `bake_pakset()` reduces to:

    HEX_ENTRIES = [
        ("BackImage[NS][0]", lambda: render_segment("NS", "hex")[0]),
        ...
    ]

    def bake_pakset() -> None:
        bake_atlas(out_png=HERE.parent / "rail_060_bridge_hex.png",
                   entries=HEX_ENTRIES, repo_root=REPO_ROOT)
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

import numpy as np
from PIL import Image

CellFn = Callable[[], np.ndarray]


def bake_atlas(*, out_png: Path, entries: Iterable[tuple[str, CellFn]],
               repo_root: Path | None = None) -> None:
    """Render each entry's RGBA cell, place them left-to-right in one
    atlas row, write `out_png`, print a per-cell bbox summary.

    `entries`: iterable of `(label, cell_fn)`.  `label` is the .dat key
    the cell maps to (e.g. `"BackImage[NS][0]"`); used only for the
    summary printout.  `cell_fn()` returns an HxWx4 uint8 RGBA array;
    every cell must have the same shape.
    """
    entries = list(entries)
    if not entries:
        raise ValueError("bake_atlas: empty entries")
    cells = [fn() for _label, fn in entries]
    h, w = cells[0].shape[:2]

    atlas = np.zeros((h, w * len(cells), 4), dtype=np.uint8)
    for col, cell in enumerate(cells):
        atlas[:, col * w:(col + 1) * w] = cell

    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(atlas, mode="RGBA").save(out_png)

    label_w = max(len(label) for label, _ in entries)
    rel = out_png.relative_to(repo_root) if repo_root else out_png
    print(f"wrote {rel} "
          f"({atlas.shape[1]}x{atlas.shape[0]} px, {len(cells)} cells)")
    for col, ((label, _), cell) in enumerate(zip(entries, cells)):
        m = cell[..., 3] > 0
        if m.any():
            ys, xs = np.where(m)
            bbox = (f"bbox=({int(xs.min())},{int(ys.min())})-"
                    f"({int(xs.max())},{int(ys.max())}) px={int(m.sum())}")
        else:
            bbox = "EMPTY"
        print(f"  col {col:2d}: {label:<{label_w}s} {bbox}")
