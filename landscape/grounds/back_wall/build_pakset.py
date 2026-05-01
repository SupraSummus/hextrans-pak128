#!/usr/bin/env python3
"""Bake the hex pakset's back-wall (cliff-face) deliverable from `render.py`.

Emits two ground descriptors in lockstep, one per palette flavor,
under the legacy pak128 `Slopes` / `Basement` namespace -- replaces
the upstream Fabio Gonella rock-photo deliverables of the same name
(kept for reference under `src/`):

  * `slopes.{png,dat}`    - Name=Slopes    (natural cliff faces)
  * `basement.{png,dat}`  - Name=Basement  (man-made fundament platform)

Both share the same `(wall, index)` key space (3 walls x 10 indices
= 30 cells per atlas) and the same geometry; only the palette
differs.  Engine consumption:
    `(artificial ? fundament : slopes)->get_image(wall, index)`
in `ground_desc_t::get_back_wall_image` and
`get_back_wall_extension_image`.  Index 0 (= "no cliff") is not
emitted; the engine treats the absent slot as IMG_EMPTY.

Re-running this script should produce a byte-identical diff against
the committed PNGs/.dats (a future CI check will enforce that).
"""

from __future__ import annotations

from pathlib import Path

import render
from render import hex_synth, WALL_COUNT, IMAGE_COUNT


HEADER_DOC_TEMPLATE = """\
Cliff-face sprites attached to the tile's three north-side edges --
wall 0 = NW edge, wall 1 = N edge, wall 2 = NE edge.  One
`Image[<wall>][<index>]` entry per (wall, index) cell, with `index in
1..{}` under the `index = h1 + 3*h2` encoding produced by
`get_back_image_from_diff` in the engine's `grund.cc`: 1..8 are the
single-step `(h1, h2)` shapes and 9..10 are placeholder half-cliffs
for the missing double-height notch (see hextrans `TODO.md`).  Index 0
is "no cliff" and is not emitted; the engine treats the absent slot
as IMG_EMPTY.

The same `(wall, index)` table doubles as the source for
`get_back_wall_extension_image`: indices 4 and 8 already encode the
single-step / double-step uniform-height cliffs the multi-step
extension reuses, so no separate atlas axis is needed.

{flavor_doc}
""".format(IMAGE_COUNT - 1, flavor_doc="{flavor_doc}")


def _wall_index_entries(artificial: bool):
    """`iter_entries` for back-wall: yield `(wall, index)` cells.

    Wall-major emission order so each atlas row carries one wall.
    """
    def gen(_geom):
        for wall in range(WALL_COUNT):
            for index in range(1, IMAGE_COUNT):
                h1, h2 = render._decode_index(index)
                yield wall, index, (wall, index, artificial), \
                      f"wall={wall} h1={h1} h2={h2}"
    return gen


def _bake_flavor(*, asset_name: str, obj_name: str, artificial: bool,
                 flavor_doc: str) -> None:
    hex_synth.bake_pakset(
        script_path=Path(__file__).resolve(),
        asset_name=asset_name,
        obj_name=obj_name,
        header_doc=HEADER_DOC_TEMPLATE.replace("{flavor_doc}", flavor_doc),
        render_cell=lambda wall, index, art, geom: render.render_back_wall(
            wall, index, artificial=art, geom=geom),
        iter_entries=_wall_index_entries(artificial),
        default_cols=IMAGE_COUNT - 1,  # one row per wall
    )


if __name__ == "__main__":
    _bake_flavor(asset_name="slopes", obj_name="Slopes",
                 artificial=False,
                 flavor_doc="Natural cliff palette: drab brown shaded "
                            "per wall.  Companion descriptor: Basement.")
    _bake_flavor(asset_name="basement", obj_name="Basement",
                 artificial=True,
                 flavor_doc="Man-made fundament-platform palette: drab grey "
                            "shaded per wall.  Companion descriptor: Slopes.")
