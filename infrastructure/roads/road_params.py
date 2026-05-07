"""Road-family parameters (cross-section, materials).

Parallel to `infrastructure/rail_tracks/rail_060_tracks/track_params.py`
for the rail family — shared by every road tier (road_030 ... road_090,
city_road, highway_*) so a sidewalk pass or a centre-line pass lands in
one place.

Per-tier overrides happen in the tier's own `scene.py` (cost,
intro_year, the colour palette of asphalt vs. cobble vs. dirt).  The
defaults below describe `road_040` — the 40 km/h stone city road that
is the first hex bake — so a subsequent tier that imports unchanged
gets stone-city geometry until it overrides.
"""
# --- Material colours --------------------------------------------------------
# Sampled from pak128 `road_040.png` cells 1.5/1.6 (NS / EW straights).
# The pak128 stone city road is two-tone: a dark olive-brown carriageway
# down the middle flanked by lighter cobblestone-grey kerbs.  Asphalt
# tiers (road_070+, highway_*) will override CARRIAGEWAY to a cooler
# dark grey and likely drop the kerb contrast.
CARRIAGEWAY_BROWN = (97, 91, 72)
SIDEWALK_GREY = (157, 167, 151)

# --- Cross-section (perpendicular to the road axis) -------------------------
# 1 world unit = 1 entry-edge length (square tile side, hex edge).  See
# `tools/threed/way.py::HEX_TILE_RADIUS` for why hex world is sized
# this way: `PAVEMENT_HALF_W = 0.5` fills the entry edge exactly under
# either projection.  The kerb spans `[CARRIAGEWAY_HALF_W,
# PAVEMENT_HALF_W]` per side; the carriageway fills the inner band.
PAVEMENT_HALF_W = 0.5
CARRIAGEWAY_HALF_W = 0.38

# Surface heights above ground (z=0).  Carriageway is a hair above the
# kerbs so it wins the z-buffer where the two overlap — at a junction
# one stub's kerb band crosses the perpendicular stub's carriageway,
# and we want the dark surface to read as one continuous intersection
# rather than a cobblestone criss-cross.  The 0.006 gap is invisible
# in oblique views (the visible top-face brightness is the same — sun
# direction unchanged) but unambiguous to the depth test.
SIDEWALK_TOP_Z = 0.008
CARRIAGEWAY_TOP_Z = 0.014

# --- Sidewalk dither --------------------------------------------------------
# Pak128 cobblestone speckle: the kerbs aren't a solid fill but a noisy
# light-on-dark dither.  Keep a fraction of the slab's surface pixels;
# dropped pixels show the dark carriageway / terrain underneath, giving
# the cobble texture seen on the reference.
SIDEWALK_DITHER_KEEP = 0.65
