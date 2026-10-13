# TODO

Running registry of open debt for the pak 3D-modelling work. Plain
paragraphs, not lists — adding or removing one entry produces a
clean diff that doesn't reflow its neighbours. When an entry is
resolved, **delete it in the same commit**: no strikethrough, no
"done" note. Git history is the changelog. Glance at this file
before starting new work; it doubles as a map of where the rough
edges are.

When you notice something wrong while working on something else —
a sketchy pattern, a missing piece, an inconsistency, an
assumption that wants verifying — log it here as a paragraph
rather than fixing it on the spot (scope creep) or leaving it as
an in-code `// TODO` (invisible outside that file). Concrete
enough that someone else can pick it up cold.

## Open

**Way .dat migration to hex ribi keys.** The engine's `way_writer`
now reads a 64-slot flat-image table keyed by hex ribi names
(`Image[se]`, `Image[se_nw]`, …; `_` separator).  Migrated today:
every rail track tier, rail_060 .. rail_400 (each a `RailParams`
instance in `infrastructure/rail_tracks/rail_params.py`), and the
single-layer road family (road_030 / road_040 / road_050 / road_055 /
road_070 / road_090 / cityroad_030 / highway_110, each a `RoadParams`
instance), every tier a parameterised hex bake fed through
`make_tier`.  Still legacy: trams, runways, kanals, narrowgauge,
monorails, maglevs, all elevated / catenary variants, and the two
front-layer highways.  These compile with unknown-key warnings and
every connectivity except `Image[-]` resolves to `IMG_EMPTY` at
runtime, so those ways will be invisible on the map.  Two paths to
migrate per family: a cell-repoint (pak `N` = hex NE etc.) leaves
third-axis combos invisible; a 3D bake of the family's cross-section
through the shared topology produces the full 63-cell set.
highway_130 / highway_200 additionally need a `FrontImage` block —
`bespoke.bake_atlas` only writes a single back atlas today, so a
second-layer pass needs adding before those tiers can migrate.

**Setts change direction at junctions and bends.**
road_040's sett rows follow each leg's own `s`/`v`
(`RoadSurface._material`),
so where legs meet in a junction core the courses switch direction
along the seam between legs, and on arcs the joints fan.
Next move: in junction cells, lay the setts on one fixed grid
keyed to plan coordinates along the hex axis nearest the through
route, and keep per-leg courses only outside the core.

**Platforms break at the joins between stop tiles.**
`hex_stops.platform_poly` runs a platform out to `PLATFORM_OUT`, 0.62,
from the middle of the way;
past 0.5 it crosses the corner of the hex beside the way,
which the stop's image is clipped off,
so a row of road stops, rail stops or parkings
shows a V-shaped gap at each join.
Next move: clip the stop's image to its hex plus the corners it crosses,
and check with `tools/ingame_check` that the neighbour's ground,
drawn later, does not paint over them.
If it does, the gaps stay and this entry goes.

**Two sets of platform parts.**
`hex_platforms` cuts its platforms with `hex_poly`,
the hex between two lines along the track;
`hex_stops` and `hex_rail_stops` use `platform_poly`, a trapezoid inside it,
and the two modules each have their own `reach` and `bench`.
Next move: build `platform_poly` on `hex_poly`,
share one `bench` that takes the platform height,
and rebake the road stops, rail stops and parking.

**Depots still legacy: monorail, air and the through depots.**
`infrastructure/depots_rail_road_tram/hex_depots/scene.py` bakes the road,
rail and tram depots in six layouts, one per hex side.
`ls-depot-monorail` and the air depots are 4-layout,
so NE and SW dead ends show the N and S image.
Next move: a `DepotParams` each
(the monorail shed raised on its pillars, a hangar for the air depots),
with `Dims=1,1,6` as `set_six_layouts` writes.
`depot_train_1936` and the ship depot are 2-layout through depots,
which wait on the engine's 3-axis through depot.

**Townhalls still legacy: the desert set and the two 1-tile ones.**
`special_buildings/townhalls/hex_townhalls/scene.py` bakes 01..05_CITY.
`01_CITY_1`..`04_CITY_1` are `Dims=2,2` too,
in white plaster with blue domes (`city-townhall-2-128.png`);
`rmax-townhall.dat` and `desert-townhall.dat` are 1×1.
Next move: a style switch on `TownhallParams`
(plaster walls, flat roofs with domes, palms for conifers)
on the same triangle-plus-forecourt layout,
and a 1-tile variant without the forecourt.

**The water bridge is still square art.**
`water_bridge` in `infrastructure/water_all/Canals.dat`
draws pak128's square aqueduct over hex canals.
Next move: a `BridgeParams` for it in `tools/threed/bridge.py`,
a stone trough on arches,
with the deck surface painted by `hex_canals/scene.py`'s `CanalSurface`.

**Factories still legacy, except those baked below.**
`factories/hex_mines/scene.py` bakes both shaft coal mines,
`factories/hex_wood/scene.py` the sawmill, furniture factory, paper mill
and printing works,
`factories/hex_industry/scene.py` the cement mill, glass works and textile mill,
`factories/hex_oil/scene.py` the oil field,
`factories/hex_farms/scene.py` the corn, cotton and grain farms,
all from the parts in `tools/threed/factory_kit.py`.
Every other factory is square art cut into `Dims` tiles,
which falls apart on the hex rhombus as the townhalls did.
Next move: the five `Dims=2,2` factories left
(dairy, Concretefactory, food_processing_plant, autoshop3, publisher)
on the same triangle-plus-yard layout.
`Dims=3,3` and larger are 9-hex and bigger rhombi, about 1.7 times as long as wide;
they need a layout decided first,
probably the building on a central hexagon with the corners as yard.

**Farm fields are square diamonds.**
`grain_field`, `corn_field`, `cotton_field` and the other field objects
are pak128's square cells, a diamond on each hex tile round a hex farm.
Next move: a parametric baker for fields in `landscape/` (furrows along
one hex axis, crop colour per field type), written over each field's
`.dat` image lines.

**Bridge generator bypasses way_topology.**
`tools/threed/bridge.py` builds every part along a `length_half`
picked per projection (`length_half()`: chord 1.0 in square, √3 in hex
with `HEX_TILE_RADIUS = 1.0`)
instead of the `StraightPath` chord that the track bakers get from
`way_topology`, which hides that scale inside the chord it builds from
`edge_midpoint`s.
Port `build_segment` / `build_end` to take a `StraightPath` (or a
shared "build along this chord" helper) and derive the length from it,
so square and hex stop needing a separate constant.

**Way-baker shared topology.** `tools/threed/way.py` +
`tools/threed/way_topology.py` carry the asset-agnostic hex topology
(stub / chord / V-bend / junction / axis-slope path builders + a
`CrossSection` painter ABC).  Consumers today:
the rail family (ballast + ties + rails cross-section,
`RailCrossSection` in `infrastructure/rail_tracks/rail_params.py`) and
the road family (`road_030` / `road_040` /
`road_050` / `road_055` / `road_070` / `road_090` / `cityroad_030` /
`highway_110`, all sharing the `RoadSurface` painter in
`infrastructure/roads/road_params.py`, which overrides `paint_edges`
to shade the whole cell from `tools/threed/way_surface.py`) — every one bakes the full
63-cell hex set into `<asset>_hex.png` plus a 6-cell axis-slope
atlas.  Open work: rail wants a buffer-stop short beam at the
centre end of single-edge stubs (currently a clean cut reads as
"track ending mid-air"); the no-way `Image[-]` placeholder still
borrows an upstream pak128 square cell on every baker.

**Way winter art.** Every rail track tier (rail_060 .. rail_400) and
the migrated road family (road_030 / road_040 / road_050 / road_055 /
road_070 / road_090 / cityroad_030 / highway_110) are single-season
now — engine treats `Image[-][1]` absent as year-round summer.  The
rail tiers' legacy .dats had a full `#WINTER` block, dropped by the
migration; the pak128 snow art it pointed at is still in
`rail_*_tracks.png`: rows 5..8, or rows 6..10 for rail_280 and up,
with the NS / EW straights at cells 5.5 / 5.6 (6.5 / 6.6).  Hex
winter art is deferred per family; lands as a colour/material
variant on the same scene parts (rail: ballast + tie palette swap,
sampled by running `measure_tier` on those winter straights; road:
snow-dusted pavement) producing `<asset>_hex_winter.png` and
re-introducing the `[1]` season block.

**Tunnels still legacy: highway_110 and road_070.**  Their .dats still
key `FrontImage[N]` and friends, so under the hex engine they compile
with unknown-key warnings and show no portal on the map.  The other
rail and road tunnels are `TunnelParams` instances
(`infrastructure/tunnel_params.py`) measured by
`infrastructure/measure_tunnel.py`, whose docstring says how.  These
two were left out because their wing walls and trim run past the face,
so the face's top corners cannot be read off the cell.  Next move: pick
a convention for the front panel between the wings (the left and right
columns and the top-edge line of the panel), add `Marks` entries and
check them with `--overlay`, then do for each what the migrated
tunnels got: instance, `scene.py` / `build.py` / `__init__.py` /
`statsignore.conf`, legacy sheet and .dat moved to `<name>/src/`, .dat
rewritten to the 6x2 layout of `rail_060_tunnel.dat`.

**Tunnel portal fidelity.**  A portal is two buttresses, a lintel and a
dark opening; the retaining wings, ring and reveal, trench and the
ground-top of the legacy cells are not modelled, and the opening is a
rectangle the size of the arch's span and crest, measured to about
0.03.  `build.py`'s square diff against the legacy cells therefore
scores low (back-layer IoU about 0.4 and front-layer 0.15 for the
measured tunnels, 0.12 to 0.15 back for the hand-set rail_060) because
pak128 paints the trench and the mountain top into the cell; read it as
a regression check.  Three improvements: (a) arched openings, gated on the renderer
accepting non-axis-aligned quads (the same upgrade unlocks the bridge's
X-bracing entry): `opening_top_z` and `opening_half_w` already are the
crest and the span, a springline height would be the one new field;
(b) a depth-clip front layer, which carves the cliff along the
camera-near plane (per-orientation `front_normal`, as the bridge's
`Orient` does) and needs `add_box` to grow a "split at this plane"
option; (c) the interior is a closed box through the whole mass, so the
`n`, `ne` and `nw` cells, whose portal faces away from the camera, show
its far end as a dark rectangle: end the interior short of the mass's
back face and close the slot with a wall-coloured slab in
`build_portal`, which re-bakes every tunnel, `rail_060_tunnel` included.

**rail_060_tunnel predates measure_tunnel.**  `RAIL_060_TUNNEL` keeps
the hand-set defaults of `TunnelParams` (opening half width 0.10 and
height 0.22), while every measured tunnel has openings from 0.17 half
width and 0.38 high up.  The legacy rail_060 sheet has its own layout
(`rail_060_tunnel/src/`: portal cell 1.0, wing wedge 0.0).  Next move:
add a `MARKS` entry for it, take the measured values into
`RAIL_060_TUNNEL`, and re-bake.

**Tunnel icons and winter art.**  The hex tunnel .dats point `icon`
and `cursor` at the portal's `BackImage[n]` cell (as `rail_060_tunnel`
did), so the build menu no longer shows pak128's speed-sign icon, cell
0.6 of each legacy sheet (cursor: 0.7), in `<name>/src/`.  Next move:
have `make_tunnel`'s bake append a row of those two cells copied from
the legacy sheet and point `icon` / `cursor` at it.  The tunnels are
single-season; the legacy winter cells are row 2 of each
`<name>/src/<name>_tunnel.png` (rows 2 and 3 for rail_060: Front, then
Back), laid out like the summer cells.  Hex winter art lands as a
colour variant of the same portal (a snow-capped top on `wall_color`)
baked to `<name>_winter.png` and a `[1]` season block in the .dat, with
the way winter art above.

**Diagonal members in the bridge generator.**
`Model.add_quad` already takes four arbitrary world corners
and the rasterizer does no back-face culling,
so diagonals need no renderer change, only a part helper:
a `beam(p0, p1, half_w, half_h)` in `tools/threed/bridge.py`
that emits the four long faces and two caps of a prism between two
NS-frame points, each face ordered so its normal points outward
(the shading reads the normal from the vertex order),
rotated and Front/Back-tagged like `_add_oriented_box`.
It unlocks rail_060's trestle X-bracing,
the lattice and truss webs of the steel tiers,
the inclined end posts of rail_100
and the vault facets of rail_400
(TODO "Rail bridge tiers still legacy").

**rail_060_bridge remaining sheet calibration.**
Mid-segments, ramps, starts, start2 and pillars are modelled
(`RAIL_060_BRIDGE` in `infrastructure/rail_bridges/rail_bridge_params.py`)
and `rail_060_bridge/build.py` diffs the square renders against the
pak128 cells.
Ramps and starts are first-pass geometry, not yet fitted to those cells,
and the pillar is a single stone box (`BoxPillar`) where pak128 draws
two rows of timber posts (alpha_iou ≈ 0.15);
replace it with a bent pillar part
and keep the box for the masonry tiers.
Winter is not baked:
the pak128 snow cells are rows 5..8 of `rail_060_bridge.png`,
in the same order as the summer rows 1..4
(the pre-hex `rail_060_bridge.dat`, git history);
add them as a colour variant of the same parts
(`<name>_hex_winter.png` plus the `[1]` season keys)
once the summer set reads right.

**Bridge end-entry calibration.**
Ramps, starts and start2 bake on all 6 hex edges
(`EndProfile` in `tools/threed/bridge.py`),
with rail_060's first-pass ramp grade, landward cut and support depths
as family constants (`RAMP_FOOT_Z`, `START_SUPPORT_Z`,
`START2_SUPPORT_Z`).
Tune them against the square reference diffs of `rail_060_bridge/build.py`.
The ramp profile interpolates the deck *bottom* from `RAMP_FOOT_Z`,
so a tier with a thicker deck than rail_060's 0.03
(the masonry and concrete tiers)
would start its ramp correspondingly higher;
interpolate the deck top instead
when the first such tier lands
(it moves rail_060's ramp cells by float rounding at most, so re-bake
and check).

**Bridge deep supports clip at the image bottom.**
rail_060's `BoxPillar.bottom_z = -0.55` projects to screen-y ≈ 156 under the hex
camera (`hex_anchor_y=106 + 0.55 × HEX_Z_SCALE`), but the hex output
is 128 tall, so all three pillar cells land y_max=127.  Pillar
accessible depth tops out at z ≈ -0.23 — about a third of the
modelled pillar.  Start/start2 end cells also touch y=127 where
their support posts extend below the deck.  The deck-anchor
calibration (`hex_anchor_y` 96→106 to match pak128's deck-vs-tile
offset) tightened this — every px the deck moves down in the cell
trades against pillar head-room.  Either shorten deep supports for
the hex bake (an axis-by-axis check whether the engine actually
composites the full max-depth shape would say if that's safe —
pak128's square cells ship the full depth and the engine clips at
composite time; hex may want the same contract), or extend the hex
output buffer vertically (give the cell a bottom-pad analogous to
HexGeom's existing top_pad for slope room).  Tracks don't hit this
because they sit at z ≥ 0.

**Rail bridge tiers still legacy.**
Only rail_060 is migrated
(`RAIL_060_BRIDGE` in `infrastructure/rail_bridges/rail_bridge_params.py`).
The other 14 `rail_*_bridge.dat` still key their cells
`[NS]/[EW]` and `[N|S|E|W]` with a season suffix,
so `bridge_writer` reads none of them and the bridges are invisible.
By structure (contact sheet of the NS segment, ramp, start and pillar
cells):
steel deck girder, lattice girders under an open-tie deck
(rail_060b, rail_080, whose Image2 is a deeper X-braced girder);
steel through girder, lattice sides above the deck (rail_080b);
steel through truss, X-braced panels
(rail_100 with inclined end posts, rail_120b parallel chords
with top bracing);
masonry or concrete arch viaduct with a ballasted deck and parapet
posts with railing panels
(rail_120 stone, rail_140 brick, rail_160 concrete, rail_180 slim
concrete);
steel deck with lattice parapet girders on a ballasted deck (rail_200);
large lattice through truss (rail_240);
concrete trough with parapet walls (rail_280),
the walls pierced by arched windows (rail_320),
closed over by a vault (rail_400).
Pillars: wall piers across the deck (080, 080b, 100, 120b and the
masonry and concrete tiers), lattice leg pairs (060b, 200, 240).
Next move, per group:
add the parts to `tools/threed/bridge.py` —
`Girder` (chords plus Warren web over a z range, below or above the
deck), `Truss` (chords, verticals, X diagonals, optional inclined end
posts), `Arch` (spandrel strips along the length whose bottoms follow
the arch curve, ring band, solid abutment on the end tiles),
`Parapet` / `Wall` (posts with infill panels, solid wall with
openings), a ballasted `RailTrack` variant, `TwinPillar`
and an `Abutment` block at the landward end of starts —
the diagonals through the beam helper
(TODO "Diagonal members in the bridge generator").
Then measure each tier with `measure_bridge.py`,
which reads the pak128 cells pinned in `LEGACY_CELLS`
and prints material colours and the pillar box;
wire its plane helpers into `report`
(deck half-width on the deck plane from the bed class,
side z range on the side plane from the FrontImage cell,
girder bottom from the Back cell's lower envelope,
arch crown and span from the opening in the viewer-side spandrel).
Two measurement facts found so far:
the pillar face-step picks rail_160's buttress instead of the wall end,
so take the rightmost strong step, not the largest;
060b and 080 share one NS segment cell.
Each tier then gets `<tier>/scene.py` as `make_tier(<TIER>)`,
the deck track from the matching `RailParams` (060b on RAIL_060),
and its .dat rewritten to the rail_060 key layout
with every non-image property kept;
the legacy winter cells sit in the rows after the summer block
of each `rail_*_bridge.png`.

**rail_060_bridge silhouette y mismatch — remaining structural
question after the deck-anchor shift.**  The 6-px-too-high
hypothesis was confirmed: shifting `screen_center_y` 68→74 (+ hex
anchor 96→106) raised IoUs across the board (BackImage 0.66→0.74,
FrontImage 0.31→0.53).  What's left is the front-half score plateau
at ~0.53 — likely the second hypothesis from the prior entry: pak128
uses a fascia under the deck edge (front-side bar that extends
below deck) rather than our kick-rail-on-top-of-deck geometry.
Verify by eyeballing a front-half ref cell side-by-side with the
candidate, then add the fascia geometry.  The kick-rail tweaks
(RAILING_TOP_Z, TOP_BAR_THICKNESS) are still the wrong move —
they fit the bbox by shrinking the railing to a hairline.

**Aggregate scoring across slices not designed.** Multi-view
supervision gives one score per slice; there's no rolled-up
per-asset or per-pakset score. For tracking progress across many
slices and assets, need a strategy (sum, max, weighted, separate
panes). Defer until more slices are wired and the right shape
becomes obvious from use.

**render.py projection vs canonical engine math.** Rasterizer uses
`YAW=45°`, `ELEV=29.5°` hardcoded, both empirically calibrated
against the flat tile. The canonical math is
`screen_x = (tile_x-tile_y)*W/2`, `screen_y = (tile_x+tile_y)*W/4`
(`viewport.cc::get_screen_coord`); a 30° elevation gives a 2:1
dimetric exactly. Cross-check that the rasterizer reproduces the
engine projection bit-for-bit, not just close enough — pick this
up before scaling to many assets where rounding errors compound.

**`Image[<slope>][k]` second-axis semantics on the engine writer.**
The marker baker emits `Image[<slope>][0]` (front) and
`Image[<slope>][1]` (back) under one `Obj=ground / Name=Marker`
block — using `[k]` as a front/back discriminator rather than the
season axis it conventionally is.  Lightmap and borders only use
`[0]`, so this encoding hasn't been exercised yet.  Whether
`descriptor/writer/ground_writer.cc` (or whatever ends up parsing
the hex marker block) preserves `[k]>0` for `Obj=ground` is
unverified.  If it doesn't, the alternatives are a split-by-
offset encoding (`Image[<slope>][0]` front, `Image[<slope>+4096][0]`
back) or a separate `Obj=ground / Name=MarkerBack` block.  Pin
this when wiring the engine-side hex marker lookup, before any
in-game test depends on the current shape.

**Per-slope water_ani.** The `landscape/grounds/water_ani/` baker
covers all 6 × 32 (depth, stage) cells but only at the flat slope.
`get_water_tile`'s slope axis (`stage + water_animation_stages *
doubleslope_to_imgnr[slope]`) is still collapsed to slope_idx = 0.
The shore-side equivalent is now done —
`landscape/grounds/texture_shore/` bakes one ALPHA_RED-keyed alpha
cell per realisable
`(slope, water_mask)`, and the wet/dry boundary lives there — so
this is the last slope-axis collapse in the parametric ground
family.

**Water_ani art is procedural-placeholder.** The renderer is a
top-K hash speckle that reads as uniform-random sparkle rather
than the layered, clustered glints of pak128's palette art.  Two
measurable gaps remain against the legacy: (a) motion energy/cycle
392 vs 201 — per-frame ~1 / GLINT_PERSISTENCE re-hash is still
roughly twice the legacy shimmer rate; raising GLINT_PERSISTENCE
or cross-fading two hash sets phased on `cos(2π t/32)` /
`sin(2π t/32)` would lower it.  (b) Per-frame stddev 13.8 vs 8.8 —
single-tier glint amplitude too high; multi-tier brightness (e.g.
4% + 4% + 4% at staggered deltas) would lower contrast while
keeping mean exact.  Both deferred until the deliverable is in-game
and the cartoon-vs-realistic balance can be judged against the
rest of the hex tileset.

