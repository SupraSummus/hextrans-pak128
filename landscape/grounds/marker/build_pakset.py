#!/usr/bin/env python3
"""Bake the hex pakset's marker deliverable from `render.py`.

Thin caller of `hex_synth.bake_pakset` — see that helper for the
shared atlas / .dat / argparse skeleton across synth-overlay
families.  Marker is the only family that uses `halves=2` (front +
back), which the helper handles by emitting `Image[<slope>][k]`
with `k=0` for front and `k=1` for back.

Run:
    python3 build_pakset.py [--w 128] [--cols 12] [--out-dir <dir>]

Re-running this script should produce a byte-identical diff
against the committed PNG/.dat (a future CI check will enforce
that).
"""

from __future__ import annotations

import sys
from pathlib import Path

import render
from render import hex_synth


HEADER_DOC = """\
Two Image[<slope_t>][k] entries per normalised hex slope shape.  k=0 is
the front half (3 south-side edges, drawn after tile content); k=1 is
the back half (3 north-side edges, drawn before tile content).  The
two halves bracket vehicles / buildings so the cursor silhouette wraps
around them.  The .dat index is the **raw slope_t value itself** (base-4
per corner: E=1, SE=4, SW=16, W=64, NW=256, NE=1024) so the engine's
hex-aware marker lookup can call `marker->get_image(slope - hgt_shift,
background)` directly without a compact-index translation table.  The
atlas stays packed (sequential cell positions, fronts first then backs),
but the index space is sparse: invalid slope_t values (per-edge delta
> 1 or min(corner_heights) != 0) don't appear and the engine reads them
as IMG_EMPTY — those encodings can't appear on real terrain so the
lookup never requests them.  Sparsity: {n_entries} populated slopes
× {halves} halves out of {n_slots} declared image slots × {halves} halves.

Per-line comment carries the per-corner height tuple (E SE SW W NW NE).
"""


if __name__ == "__main__":
    hex_synth.bake_pakset(
        script_path=Path(__file__).resolve(),
        asset_name="marker",
        obj_name="Marker",
        header_doc=HEADER_DOC,
        render_cell=lambda slope, half, geom: render.render_marker(
            slope, background=(half == 1), geom=geom),
        halves=2,
    )
