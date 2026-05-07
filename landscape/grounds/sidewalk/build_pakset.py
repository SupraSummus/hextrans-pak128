#!/usr/bin/env python3
"""Bake the hex sidewalk (city-road pavement) deliverable from `render.py`.

Thin caller of `hex_synth.bake_pakset` — see that helper for the
shared atlas / .dat / argparse skeleton across the parametric ground
family.  This file carries only the sidewalk-specific bits: the
`render_cell` callback (which delegates to `render.render_sidewalk`)
and the per-asset doc paragraph that goes into the .dat header.

Run:
    python3 -m landscape.grounds.sidewalk.build_pakset

Re-running this script should produce a byte-identical diff against
the committed PNG/.dat (a future CI check will enforce that).
"""

from __future__ import annotations

from pathlib import Path

from . import render
from tools.threed import hex_synth


HEADER_DOC = """\
One Image[<slope_t>][0] entry per way-buildable hex slope (i.e.
the subset of valid slopes for which `slope_t::is_way` is true,
about half of the 141 valid shapes).  The .dat index is the **raw
slope_t value itself** (base-4 per corner: E=1, SE=4, SW=16, W=64,
NW=256, NE=1024) so the engine's ground-tile lookup
(`ground_desc_t::sidewalk->get_image(slope_t::lower_min_corner(slope))`,
mirroring `borders` and `marker`) lands on this cell directly
without a compact-index translation table.  Slopes a way can't
cross are absent from the atlas; the engine never asks for a
sidewalk on those tiles (city roads can't be built there).

Replaces upstream pak128's `Obj=misc Sidewalk` descriptor that was
keyed by the legacy 4-corner sprite index — see
`landscape/grounds/sidewalk/src/` for the upstream art kept as
reference.

Per-line comment carries the per-corner height tuple (E SE SW W NW NE).
"""


if __name__ == "__main__":
    hex_synth.bake_pakset(
        script_path=Path(__file__).resolve(),
        asset_name="sidewalk",
        obj_name="Sidewalk",
        header_doc=HEADER_DOC,
        render_cell=lambda slope, half, geom: render.render_sidewalk(slope, geom=geom),
        iter_entries=hex_synth.slope_keyed_entries(halves=1,
                                                   slope_filter=hex_synth.slope_is_way),
    )
