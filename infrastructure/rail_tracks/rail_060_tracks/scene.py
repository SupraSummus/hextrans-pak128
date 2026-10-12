"""3D model of the rail_060 timber rail track (one tile, mid-segment).

Cross-section: a thin dithered gravel bed, cross-ties and twin rails,
matching pak128 cells 1.5 / 1.6 in `rail_060_tracks.png`.  All
tier-specific values live in
`infrastructure/rail_tracks/rail_params.RAIL_060`; the painter is the
shared `RailCrossSection`, emitting into the chord+caps frame from
`tools/threed/way_topology.py::make_slab_emitter`.

Hex deliverable: three atlases written by
`tools.threed.way_bake.bake_way_atlases` next to the sibling
`rail_060_tracks.dat` — see that module for shape details.  Square
verification: `build.py` lays straights via `way_verify` and diffs
against pak128 cells 1.5 / 1.6 (the upstream dimetric NS / EW
straight art).

Coordinate system matches `render.py` and `rail_060_bridge/scene.py`:
world +x = east (lower-right onscreen in square dimetric, screen-right
in hex), world +y = north (upper-right in square, screen-up in hex),
world +z = up.  Track is "back" layer — engine draws track before
vehicles, no front/back split.

Tracks ship no per-image dat offset (unlike `rail_060_bridge`'s `,0,32`),
so we render with world z=0 at the default ground anchor sy=96 (=
IMG_SIZE/2 + 32, the flat-tile bbox midpoint).
"""
from infrastructure.rail_tracks.rail_params import RAIL_060, make_tier

CS, bake_pakset = make_tier(RAIL_060)


if __name__ == "__main__":
    bake_pakset()
