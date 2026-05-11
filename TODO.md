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
`rail_060_tracks` and the single-layer road family (road_030 /
road_040 / road_050 / road_055 / road_070 / road_090 /
cityroad_030 / highway_110), each shipping a parameterised hex
bake whose tier `scene.py` reduces to a `RoadParams` instance fed
through `make_tier`.  Still legacy: rail_080..rail_400, trams,
runways, kanals, narrowgauge, monorails, maglevs, all elevated /
catenary variants, and the two front-layer highways.  These
compile without fatal but every connectivity except `Image[-]`
resolves to `IMG_EMPTY` at runtime, so those ways will be
invisible on the map.  Two paths to migrate per family: a
cell-repoint (pak `N` = hex NE etc.) leaves third-axis combos
invisible; a 3D bake of the family's cross-section through the
shared topology produces the full 63-cell set.  highway_130 /
highway_200 additionally need a `FrontImage` block —
`bespoke.bake_atlas` only writes a single back atlas today, so a
second-layer pass needs adding before those tiers can migrate.

**Asphalt-tier centre dashes.**  road_050 / road_070 / road_090 /
highway_110 read as plain dark-grey slabs in the hex bake,
because `RoadParams` captures one carriageway colour.  In pak128
each of these tiers is the same colour with a white dashed
centreline (single dashes on road_050 / road_070, double on
road_090 / highway_110) — the most distinctive feature of the
upstream art and the strongest cue distinguishing tiers from
each other in-game.  Add a `lane_markings` field
(None / "single" / "double") to `RoadParams` and have
`RoadCrossSection.paint_straight` emit short-`s`-range white slabs
along the chord centreline when set; cadence keyed off
`chord_len` from `make_slab_emitter` so dashes line up across
adjacent tiles regardless of chord length (full-tile vs.
arc-piece).

**rail_060_bridge bypasses way_topology.**  Mid-segments / ends are
built directly with `_add_oriented_box` against a `BRIDGE_LEN_HALF`
constant rather than the `StraightPath` chord that `rail_060_tracks`
uses.  This is why `build_segment` / `build_end` had to grow a
`length_half` parameter and why `render_segment` picks the value
per projection (chord = 1.0 in square, √3 in hex with
`HEX_TILE_RADIUS = 1.0`) — way_topology hides that scale inside the
chord it builds from `edge_midpoint`s.  Port the bridge to drive its
deck / posts / ties off a `StraightPath` (or a shared "build along
this chord" helper) so the next rail bridge variant lands without
re-plumbing length_half.

**Way-baker shared topology.** `tools/threed/way.py` +
`tools/threed/way_topology.py` carry the asset-agnostic hex topology
(stub / curve / junction / axis-slope path builders + a
`CrossSection` painter ABC).  Consumers today:
`infrastructure/rail_tracks/rail_060_tracks` (ballast + ties + rails
cross-section, with a `paint_arc` override for radial ties) and the
road family (`road_030` / `road_040` / `road_050` / `road_055` /
`road_070` / `road_090` / `cityroad_030` / `highway_110`, all
sharing the parameterised `RoadCrossSection` in
`infrastructure/roads/road_params.py`) — every one bakes the full
63-cell hex set into `<asset>_hex.png` plus a 6-cell axis-slope
atlas.  Open work: 3+ way junctions are placeholder "stub-per-edge"
geometry — a pass should promote any 60°-apart pair inside a
junction to an arc (through-route) and leave the remaining edges as
branching stubs; rail also wants a buffer-stop short beam at the
centre end of single-edge stubs (currently a clean cut reads as
"track ending mid-air"); the no-way `Image[-]` placeholder still
borrows an upstream pak128 square cell on every baker.

**Way winter art.** `rail_060_tracks.dat` and the migrated road
family (road_030 / road_040 / road_050 / road_055 / road_070 /
road_090 / cityroad_030 / highway_110) are all single-season now
— engine treats `Image[-][1]` absent as year-round summer.  Hex
winter art is deferred per family; lands as a colour/material
variant on the same scene parts (rail: ballast + tie palette swap;
road: snow-dusted pavement) producing `<asset>_hex_winter.png`
and re-introducing the `[1]` season block.

**rail_060_tunnel_hex remaining sheet calibration.**  The hex
deliverable (`rail_060_tunnel_hex.{png,dat}` baked from
`rail_060_tunnel/scene.py`) ships 12 cells (6 edges × Front/Back)
and is wired up as a separate `Name=Rail_060_Tunnel_Hex` object
alongside the legacy upstream tunnel.  Geometry is two cliff
buttresses + lintel + dark interior, with only the lintel in the
front layer (occludes the vehicle as it passes under the arch).
Square verification against pak128 cells 0-1.0..0-1.3 of
`rail_060_tunnel.png` via `build.py` lands back-layer IoU ~0.40
(0.53 on camera-facing [N]/[W], 0.27 on [S]/[E]) and front-layer
IoU ~0.06 — the back is close because the buttresses + dark
interior recreate the visible-cliff silhouette pak128 paints into
the back cell, but pak128's front cells carry a separately-shaped
"near-half cliff wedge" that our lintel-only front can't match.
Two open improvements: (a) the rectangular opening reads as a
doorway, not the arched cave mouth pak128 ships — needs curved
or bevelled top, gating on the renderer accepting non-axis-aligned
quads (same upgrade unlocks the bridge's X-bracing entry); (b) a
real depth-clip front-layer split (per-orientation `front_normal`,
matching the bridge's `Orient` pattern) would carve the cliff
along the camera-near plane and produce a substantial front cell
without duplicating geometry — needs `add_box` to grow a "split
at this plane" option, since axis-aligned boxes cut by an
arbitrary plane produce non-axis-aligned children.

**X-bracing on rail_060_bridge.** The numpy z-buffer rasterizer
in `tools/threed/render.py` only supports axis-aligned boxes via
`add_box`, so the diagonal X-bracing between trestle posts can't
be modelled cleanly. Two options: extend `Scene.add_quad` with
explicit non-axis-aligned corners (a thin plate in the y-z plane,
rendered double-sided), or switch this asset class to Blender.
Defer until other rail bridge variants are in flight so the fix
applies once across the family.

**rail_060_bridge remaining sheet calibration.** Mid-segments
(NS/EW back+front), ramps, starts, start2, and pillars are now
modelled and bake into both the square verification renders
(`build.py` refs table) and the hex atlas.  Ramps/starts are still
first-pass geometry — coherent with the 60 bridge model, but not yet
closely fitted to the upstream pak128 cells.  Pillar geometry is also
a first-pass stub — a single
stone box from z=PILLAR_BOTTOM_Z to deck-bottom; it doesn't match
the reference's wider cross-section or the asymmetric face that
`pillar_asymmetric=1` implies (alpha_iou ≈ 0.15 per the diff).
Winter variants of every entry remain entirely deferred — should
plug in as a colour/material variant on the same parts once the
summer set reads right.

**rail_060_bridge_hex end-entry calibration.**  Engine
`bridge_desc_t::img_t` is the hex layout — 3 way
axes for segments / pillars (`ns`, `ne_sw`, `nw_se`) and 6 hex edges
for starts / ramps (`n`, `s`, `ne`, `se`, `sw`, `nw`); the writer
reads keys at those names (`bridge_writer.cc`).  The hex dat now
covers the full summer set: segments + pillars via the axis
orientations, and ramps / starts / start2 via edge orientations.
Next pass should tune the ramp grade, landward cut, and front railing
placement against the square reference diffs before cloning the
material variant for winter.

**rail_060_bridge_hex deep supports clip at the image bottom.**
`PILLAR_BOTTOM_Z = -0.55` projects to screen-y ≈ 156 under the hex
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

