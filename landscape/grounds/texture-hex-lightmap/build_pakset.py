#!/usr/bin/env python3
"""Bake the hex pakset's ground deliverable from `render.py`.

Thin caller of `hex_synth.bake_pakset` — see that helper for the
shared atlas / .dat / argparse skeleton across synth-overlay
families.  This file carries only the lightmap-specific bits: the
`render_cell` callback (which delegates to
`render.render_lightmap`) and the per-asset doc paragraph that
appears in the .dat header.

Climate texture is not regenerated: pak128's existing
`landscape/grounds/texture-climate.png` is biome art with no tile
geometry baked in, so we reuse it unchanged.  The runtime path
is `create_textured_tile(hex_lightmap[slope], climate_texture[c])`.

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
One Image[<slope_t>][0] entry per normalised hex slope shape.  The .dat
index is the **raw slope_t value itself** (base-4 per corner: E=1, SE=4,
SW=16, W=64, NW=256, NE=1024) so the engine's hex-aware ground lookup can
call `get_image_ptr(slope - hgt_shift)` directly without a compact-index
translation table.  The atlas stays packed (sequential cell positions),
but the index space is sparse: invalid slope_t values (per-edge delta > 1
or min(corner_heights) != 0) don't appear and the engine reads them as
IMG_EMPTY — those encodings can't appear on real terrain so the lookup
never requests them.  Sparsity: {n_entries} populated entries out of
{n_slots} declared image slots.

Per-line comment carries the per-corner height tuple (E SE SW W NW NE).
"""


if __name__ == "__main__":
    hex_synth.bake_pakset(
        script_path=Path(__file__).resolve(),
        asset_name="texture-hex-lightmap",
        obj_name="LightTexture",
        header_doc=HEADER_DOC,
        render_cell=lambda slope, half, geom: render.render_lightmap(slope, geom=geom),
    )
