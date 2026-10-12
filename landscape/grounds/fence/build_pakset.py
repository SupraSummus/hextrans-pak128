#!/usr/bin/env python3
"""Bake the hex pakset's fence deliverable from `render.py`.

Emits `fences.{png,dat}` -- `Obj=ground / Name=Fence`, 14 cells: the 7
non-empty edge subsets for natural ground, then the same 7 for
artificial ground.  Replaces the square-era Fabio Gonella deliverable
of the same name (3 natural + 3 building cells for the two square back
walls) and keeps its filename; engine consumption is in
`display_boden`, `ground_desc_t::fences->get_image(typ)`.

Re-running this script should produce a byte-identical diff against
the committed PNG/.dat (`tools/bake_all.py`, checked by `lint.yml`).
"""

from __future__ import annotations

from pathlib import Path

from tools.threed import hex_synth
from . import render
from .render import EDGE_NAMES, MASK_COUNT


def _mask_label(mask: int) -> str:
    return "+".join(EDGE_NAMES[wall] for wall in render.mask_walls(mask))


def _encoding_table() -> str:
    rows = [f"  {'mask':<5} {'edges':<9} {'natural':<8} artificial"]
    for mask in range(1, MASK_COUNT + 1):
        rows.append(f"  {mask:<5} {_mask_label(mask):<9} "
                    f"{mask - 1:<8} {mask - 1 + MASK_COUNT}")
    return "\n".join(rows)


HEADER_DOC = """\
Fence sprites for the tile's three north-side edges (the engine's
back-wall slots).  The engine puts a fence on an edge when the
neighbour behind a level edge lies lower and the tile shows no cliff
face; one whole-tile cell carries every fence of the tile.
`calc_back_image` in the engine's `grund.cc` builds

    mask = [NW edge] + 2 * [N edge] + 4 * [NE edge]      (1..{count})

and `display_boden` draws `Image[mask - 1]` for natural ground, or
`Image[mask - 1 + {count}]` for artificial ground (a building
foundation or an artificial slope):

{table}

The cell is the flat tile; the engine lifts it by the higher of the
NW and NE corner heights.  A fence stands on its edge line and is
drawn before the tile's ground, so the cell keeps everything on or
below the edge line empty and starts one pixel above it.

Natural ground gets a one-pixel dark-olive line along the edge,
artificial ground a low brown wooden fence (posts at {posts} equal
steps along each edge, two rails).  Colours, height and rail layout
follow the legacy Fabio Gonella fences this descriptor replaces.
""".format(table=_encoding_table(), count=MASK_COUNT,
           posts=render.ARTIFICIAL.posts)


def _fence_entries(geom):
    """`iter_entries` for fence: yield `(index, 0, (mask, artificial), ...)`.

    Natural cells first, then artificial, so the atlas row is the
    flavor and the column is `mask - 1`.
    """
    for artificial in (False, True):
        for mask in range(1, MASK_COUNT + 1):
            index = mask - 1 + (MASK_COUNT if artificial else 0)
            flavor = "artificial" if artificial else "natural"
            yield index, 0, (mask, artificial), \
                  f"{flavor} {_mask_label(mask)}"


if __name__ == "__main__":
    hex_synth.bake_pakset(
        script_path=Path(__file__).resolve(),
        asset_name="fences",
        obj_name="Fence",
        header_doc=HEADER_DOC,
        render_cell=render.render_fence,
        iter_entries=_fence_entries,
        default_cols=MASK_COUNT,  # one row per flavor
    )
