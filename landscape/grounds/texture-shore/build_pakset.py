#!/usr/bin/env python3
"""Bake the hex pakset's shore-transition deliverable from `render.py`.

Thin caller of `hex_synth.bake_pakset` — see that helper for the
shared atlas / .dat / argparse skeleton across synth-overlay
families.  Shore is the first family to use the variable-axis
`iter_entries` plumbing rather than `slope_keyed_entries`: cells
live on a `(slope, water_mask)` grid where the realisable second-
axis values depend on the slope (see HEADER_DOC below for the
realisability rule).

Run:
    python3 build_pakset.py [--w 128] [--cols 12] [--out-dir <dir>]

Re-running this script should produce a byte-identical diff
against the committed PNG/.dat (CI's lint workflow enforces it).
"""

from __future__ import annotations

from pathlib import Path

import render
from render import hex_synth


HEADER_DOC = """\
One Image[<slope_t>][<water_mask>] entry per (slope, water_corner_mask)
combination realisable on real terrain.  The engine's
`grund.cc::display` builds `water_corners` by walking each hex corner
and setting bit `ci` when one of the corner's three vertex-owners is
the water climate AND the home-tile vertex height matches.  A water
tile is flat at sea level with all corners at h==0, and per-vertex
height is shared between neighbours, so a water neighbour can border
us only across an edge whose *both* endpoints are at h==0.  A wet edge
therefore sets a 2-bit corner pair in the mask; single-bit masks can't
appear on real terrain and aren't emitted.

The .dat indexes by raw `slope_t` (base-4 per corner: E=1, SE=4, SW=16,
W=64, NW=256, NE=1024) and the 6-bit water mask (E=1, SE=2, SW=4, W=8,
NW=16, NE=32) so the engine's hex-aware shore lookup can call
`transition_water_texture->get_image(slope, water_corners)` directly.

The atlas stays packed (sequential cell positions); the index space is
sparse — invalid `slope_t` values, the empty mask, masks with lifted
corners, and masks with an isolated wet bit never appear, and the
engine reads them as IMG_EMPTY.  Those combinations can't appear on
real terrain so the lookup never requests them.

Sparsity: {n_entries} populated entries out of {n_slots} declared image
slots × 64 mask values.

The engine's `draw_alpha` reads only the **red channel** (`ALPHA_RED`,
mask 0x7c00), so RED = water shows; BLUE (or any non-red colour) =
water suppressed (climate texture wins).  A position-deterministic
hashed dither at the wet/dry boundary preserves the gritty soft-edge
look of the legacy `texture-shore.png`.

Per-line comment carries the per-corner height tuple and the per-
corner water-flag tuple, both as (E SE SW W NW NE).
"""


def _shore_entries(geom):
    """Yield `(slope, water_mask, render_args, comment)` for every
    realisable shore cell — see HEADER_DOC for the engine reasoning
    behind the predicate.
    """
    n = hex_synth.CORNER_COUNT
    for slope in hex_synth.iter_valid_slopes():
        ch = hex_synth.decode_corner_heights(slope)
        for water_mask in range(1, 1 << n):
            wets = [(water_mask >> i) & 1 for i in range(n)]
            # Each wet corner must sit at h=0 (water tile is flat at
            # sea level) AND have a wet neighbour mod 6 (a wet edge
            # sets both endpoints, never one alone).
            if any(w and (ch[i] != 0
                          or not (wets[(i - 1) % n] or wets[(i + 1) % n]))
                   for i, w in enumerate(wets)):
                continue

            comment = (
                f"corners=(E={ch[hex_synth.E]} SE={ch[hex_synth.SE]} "
                f"SW={ch[hex_synth.SW]} W={ch[hex_synth.W_C]} "
                f"NW={ch[hex_synth.NW]} NE={ch[hex_synth.NE]}) "
                f"water=(E={wets[hex_synth.E]} SE={wets[hex_synth.SE]} "
                f"SW={wets[hex_synth.SW]} W={wets[hex_synth.W_C]} "
                f"NW={wets[hex_synth.NW]} NE={wets[hex_synth.NE]})"
            )
            yield slope, water_mask, (slope, water_mask), comment


if __name__ == "__main__":
    hex_synth.bake_pakset(
        script_path=Path(__file__).resolve(),
        asset_name="texture-shore",
        obj_name="ShoreTrans",
        header_doc=HEADER_DOC,
        render_cell=lambda slope, water_mask, geom: render.render_shore(
            slope, water_mask, geom=geom),
        iter_entries=_shore_entries,
    )
