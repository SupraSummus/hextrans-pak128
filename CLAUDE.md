# CLAUDE.md

Notes for AI agents (and humans) working on this fork of pak128.

## Bigger picture

This fork exists because we want to port Simutrans to a **hex grid**
(`SupraSummus/hextrans`). A hex-grid map needs sprites rendered from
hex-appropriate camera angles — the existing pak128 sprites are drawn for the
square-tile dimetric projection and can't simply be reused.

The plan is to obtain hex-grid sprites by introducing an intermediate
representation we don't currently have: **3D models** of pakset assets. Once
an asset is a 3D scene, we can render it from any camera angle — including
hex viewpoints — to produce the new tileset.

We don't have time or skill to model the entire pakset by hand. The hope is
that an iterative, automated pipeline can carry most of the load.

### Two kinds of asset, two pipelines

The work splits cleanly:

1. **Parametric / synthesisable assets** — ground tiles per slope+climate,
   tile-cursor and grid-line markers, climate alpha masks, cliff faces.
   These have no bespoke art in the source pakset's sense; they are
   functions of a few engine parameters (`slope_t::type`, climate index,
   neighbour height diff).  All such families now ship as pakset
   descriptors baked from per-asset `render.py` + `build_pakset.py`
   under `landscape/grounds/`; the engine reads them directly.  The
   on-disk pipeline is: parametric scene → render → bake atlas + .dat
   → commit; verification against pak128 conventions is qualitative
   (legacy palette match, silhouette consistency with `LightTexture`).

2. **Bespoke 3D assets** — vehicles, bridges, buildings, trees, factories.
   Each has hand-authored art in pak128. Here we genuinely have to model
   in 3D, supervised against pak128's existing sprite sheets, and
   re-render through the hex camera. The render-and-diff loop below is
   for this case.

The two pipelines share a renderer (camera, lighting, projection,
depth-clip slicing) but have different reference data and different
deliverables. The first parametric deliverable —
`landscape/grounds/texture-lightmap/texture-lightmap.{png,dat}` baked from
`landscape/grounds/texture-lightmap/` — is pipeline (1).

## Engine facts (look up, don't fit)

Orientation, camera, sheet layout, slope encoding, sun direction —
these are engine and pakset facts, not free parameters. Look them
up before tweaking. Fitting them by trial against a single reference
gives a result that's right by accident and breaks when you swap to
the next sheet entry.

Reference card (paths are in the simutrans engine repo,
`SupraSummus/hextrans` branch `simutrans` for square / `claude/...`
or `simutrans` for hex synth):

- **Tile-to-screen mapping** (square dimetric):
  `display/viewport.cc::get_screen_coord` — `screen_x = (tile_x -
  tile_y)*(W/2)`, `screen_y = (tile_x + tile_y)*(W/4)`.
- **Compass** (square): `dataobj/koord.cc` — `north=(0,-1)`,
  `east=(1,0)`, `south=(0,1)`, `west=(-1,0)`. Combined with the
  tile-to-screen mapping: **N=upper-right, E=lower-right,
  S=lower-left, W=upper-left**. A NS bridge runs along the world
  y-axis; its east-facing (+x) side is closer to the viewer (the
  `FrontImage` layer).
- **Bridge image enum** (engine side):
  `descriptor/bridge_desc.h::img_t`. Image lookup helpers:
  `get_background()` / `get_foreground()` in the same file.
  Compositing call site: `obj/bruecke.cc::calc_image()` and
  `get_front_image()` — Back drawn with the way (behind vehicles),
  Front drawn after vehicles.
- **Bridge .dat keys** (pakset side):
  `descriptor/writer/bridge_writer.cc` parses
  `BackImage[NS|EW]`, `FrontImage[NS|EW]`, `BackRamp/FrontRamp[N|S|E|W]`,
  `BackStart/FrontStart[N|S|E|W]`, `BackStart2/FrontStart2[N|S|E|W]`
  (double-height), `backPillar[S|W]`. Pillar only `S` and `W` —
  the other two are mirrors.
- **Slope encoding**: `dataobj/ribi.h::slope_t` — base-3 per corner
  (`southwest=1, southeast=3, northeast=9, northwest=27`),
  `max_number = 80`, 81 raw indices.
- **Hex camera + lighting**: `tools/3d/hex_synth.py::HexGeom` is the
  canonical pakset-side camera (vertex layout, per-step lift derived
  from `display/hex_proj.h::hex_height_raster_scale_y`); directional
  light `L = (-1, 1, 2)` calibrated so flat = 1.0×.  The earlier
  engine-side `synth_overlay::*` runtime ground truth has been baked
  into the pakset and removed; the bakers are the source of truth.
- **Pak128 art conventions** (`devdocs/128painting.txt`): 2:1
  dimetric, sun from south at ~60° above horizon, 1 tile ≈ 20×20 m,
  12 px ≈ 2 m, building story ≈ 14 px. These are pak128's
  art-side conventions, not engine constants.

When something doesn't match the reference, before tweaking a
parameter, ask "is this an engine fact I haven't looked up yet?".
Common reflexes:

- **Sheet offset semantics.** A `.dat` entry like `…,0,32` is a
  draw-time offset the engine applies when compositing the cell
  over a tile, **not** a shift baked into the cell. The cropped
  cell is in raw cell coordinates; if your render's z=0 is at the
  wrong screen-y, calibrate empirically against a reference y_max
  rather than guessing from the offset. The offset is per-asset:
  each .dat declares its own and each scene calibrates its own
  `screen_center_y`. Don't copy a sibling asset's anchor constant
  just because it was the most recent example — `rail_060_bridge`
  empirically needed a non-default value; `rail_060_tracks`
  doesn't, and re-using the bridge constant ships the renderer
  off by ~30 px.
- **Structural anchors that are NOT free.** World z=0 is ground;
  a tile spans x,y in [-0.5, +0.5] (in unit-tile world coords);
  trestle / pillar bases sit at z=0 by convention. Use these as
  fixed points to back-solve other parameters.

## Open debt registry

`TODO.md` at the repo root is the running registry of open debt
for this work — a paragraph per item, not a list, deleted when
resolved (no strikethrough, no "done" notes; git history is the
changelog). When you notice something wrong while working on
something else, log it there as a paragraph rather than fixing it
on the spot (scope creep) or leaving it as an in-code `// TODO`
(invisible outside that file). Glance at it before starting new
work.

## Starting an asset

Every asset (parametric or bespoke) follows roughly the same arc.
Working order:

0. **Glance at `TODO.md`** for any open debt that touches this
   asset or its tooling.
1. **Read the .dat and crop a contact sheet.** Enumerate every
   sheet entry the asset contributes — for bridges, that's
   BackImage / FrontImage / BackRamp / FrontRamp / BackStart /
   FrontStart / BackStart2 / FrontStart2 × directions, plus
   pillars. Note seasons and the per-entry sheet offset. Then run
   `tools/3d/crop_ref.py` over every referenced cell **before
   opening `scene.py`** — the .dat alone doesn't tell you which
   cells are stubs vs. full-tile vs. slope variants, nor what art
   conventions apply (ballast dither, taper bands, mitred caps).
2. **Look up engine facts and existing helpers.** Pull from the
   reference card above anything you'll need — compass, image
   enum, .dat key meaning, sheet offset semantics. Then skim
   `tools/3d/hex_synth.py` and `tools/3d/render.py` for engine-
   mirror helpers (`HexGeom`, `hash_noise01`, `silhouette_mask`,
   `iter_valid_slopes`, projection support); reuse beats
   reinvention and keeps square / hex output coherent. Do all
   this before opening the scene file.
3. **Map sheet entries to model layers.** Each entry is a 2D view of
   the asset under a specific (camera, depth-clip). Decide which 3D
   sub-parts go in which layer. Skip the composite-only first pass
   from earlier drafts of this doc — it hides per-slice errors.
   One scene, multiple projections — never two parallel scene
   files for square vs. hex.
4. **Stand up the build.** `build.sh` crops every reference, runs the
   scene, and diffs each candidate against its reference.
   Per-slice scores in the output.
5. **Iterate via structural recognition, not gradient descent.** Look
   at each per-slice debug image, spot what 3D structure the
   reference shows that the candidate lacks, change it, rerun.

A few concrete habits:

- **First render verifies placement, not shape.** Run a
  solid-colour pass at the right bbox before adding any pattern
  (dither, taper, texture). Cheap, and a 30 px placement bug in a
  textured render reads as a shape bug — burning iterations on
  shape while placement is off is the classic trap.
- **Bbox-check every iteration.** Print x/y range and pixel count
  for each reference and candidate. The eye misses silent shifts;
  bboxes catch them in two seconds.
- **Verify geometry formulas at corner points.** For any
  half-plane, clip, or projection inequality, evaluate it at the
  6 hex corners (or 4 square corners) and any other known
  interior / exterior point before relying on it. Two minutes
  saves an iteration on a silently-wrong formula.
- **Check existing pak128 conventions before inventing geometry.**
  The dat's "curve" cells may be short straight-with-mitred-caps
  rather than arcs; the contact sheet from step 1 answers this
  in a minute. When generalising a geometry helper, write down
  the case where it breaks (e.g. "this construct only works while
  the cap fits inside the available corner clearance") before
  shipping the renders — keeps later you from learning by bbox.
- **Per-asset constants stay per-asset.** Sheet offset, anchor Y,
  gauge, tie cadence — declared in the asset's own
  `scene.py` / .dat. Don't copy them from a sibling. Conversely,
  *track-family* parameters that should stay consistent across
  rail_060 / rail_080 / road / tram (gauge, tie spacing, ballast
  bands) belong in a shared module, not duplicated per scene.
- **Back-solve from reference geometry.** If the reference's front
  strip is 41 px tall and your projection has 90 px / world unit at
  the relevant axis, the railing's z extent is `41 / 90 ≈ 0.13`. Do
  this calculation before tweaking the constant.
- **Use TodoWrite for multi-step iteration.** Per-slice fixes,
  orientation lookups, geometry tunes — easy to lose track without
  it.

## The approach: render-and-diff

For each asset:

1. A **3D scene description** (text, AI-editable).
2. A **build command** that renders one PNG per sheet entry.
3. A **diff** of each rendered PNG against its reference.

References:

- **Parametric pipeline.** Reference = the bakers' own output;
  validation is qualitative (legacy palette match, silhouette
  consistency with `LightTexture`).  Camera + lighting come from
  `tools/3d/hex_synth.py::HexGeom`.  Deliverable: baked PNGs that
  the engine reads directly.
- **Bespoke pipeline.** Reference = pak128's existing sheet entries.
  All slices used as supervision simultaneously (one diff per
  entry, not against a composite). Same scene re-renders through
  the hex camera + hex slicing spec for the hex deliverable.

### The diff is a sanity check, not the steering signal

The goal isn't to "minimize the diff"; the goal is a structurally
correct 3D model that happens to render close to pak128 from one
camera. The score lags. What actually moves the score:

- **Structural recognition.** Look at the reference and the
  candidate side by side. Ask "what 3D structure produces *that*
  2D image?" — not "what tweak shrinks the diff?". When the front
  layer is missing a kick-rail, that's a structural observation
  about the reference, not a derivative of the diff score.
- **Engine-fact lookup** (orientation, sheet offset, .dat keys).
  Trial-and-error against the diff produces a result that's right
  by accident. See "Engine facts" above.

The diff loop's actual jobs are: regression check (an edit didn't
quietly make things worse), progress quantifier (we're heading
the right direction across iterations), and surfacing
discrepancies the eye misses (silent shifts, sub-pixel mismatches).
Treat low diff as necessary but not sufficient.

When you add a new pak128 art convention (dither, ballast taper,
gritty edge), expect IoU to drop — the convention matches
pak128's looser visual contract at the cost of pixel-exactness
against any one cell. Document the reason in the commit; don't
tweak parameters back to fight the score.

### Structural correctness as anchors

Some structural facts are fixed and you should back-solve other
parameters from them:

- **World z=0 is ground.** Trestle / pillar bases sit at z=0.
- **Tile spans `[-0.5, +0.5]` in x,y** (unit-tile coords). Bridges
  meet the ground at world `y = ±0.5` (NS) or `x = ±0.5` (EW).
- **Heights shared across variants.** All `rail_*_bridge` decks
  share a deck-top z so a slow bridge upgraded to a fast one
  doesn't tilt; same for road bridges, tunnels, etc.
- **Repeating elements at the same pitch** across variants.

Structural correctness is required for the asset to read correctly
from hex angles, not just pak128's. A model that pixel-matches but
is structurally wrong is a failure.

### Who does the modeling

An AI agent acting as a directed artist — examine the reference,
build a scene, render it, look at the side-by-side, edit, iterate.
Not numerical optimisation; no scipy, no gradient descent over
vertex positions.

### Modeling unit and slicing

Three orthogonal axes that are easy to tangle:

1. **Modeling unit = structural 3D parts** (deck, pillar, ramp,
   span, …). Not the whole asset as one fused mesh, not one scene
   per sheet entry. Parts compose for the whole asset and recompose
   for hex output. Slicing into the modeling unit would bake
   pak128's depth planes into geometry; hex has different ones, so
   we'd lose re-sliceability.
2. **Supervision = all sheet entries simultaneously.** Each entry
   is an independent 2D view of the same 3D parts under a specific
   `(camera, depth_clip)`. Strictly stronger than diffing the
   composite (which is just the union and gives less signal per
   pixel and hides per-slice errors).
3. **Output slicing = renderer parameter.** `render(scene, camera,
   depth_clip) → PNG`. Emit pak128 sheets via square dimetric +
   pak128's depth planes; emit hex sheets via `synth_hex_geometry_t`
   (single-layer assets work today — see `rail_060_tracks`;
   multi-layer assets wait on the hex depth-plane spec, open
   question below).

### Renderer choice

The constraint is: **the renderer must expose camera, depth-clip
plane, lighting, and projection as parameters** the agent can edit.
A scene file that hardcodes any of them can't emit both pak128 and
hex slicings from one source. Beyond that, choose the renderer that
fits the asset:

- A ~150-line numpy z-buffer rasterizer is enough for hard-surface
  CSG (terrain, simple bridges, low-poly vehicles); see
  `tools/3d/render.py`.
- Blender Python (`bpy`, headless via `blender -b`) is the right
  pick for textured / sculpted / mesh-heavy content.
- OpenSCAD is fine for blocky parametric assets if you can post-
  process its preview render to inject controllable lighting; the
  preview's hardcoded sun is a real limitation.

The build-command → `out.png` contract stays the same regardless;
the diff tool doesn't care how `out.png` was made.

### Don't bake the answer

Asset source must not contain or read the reference PNG. Pakset
materials (e.g. flat-grass climate texture) may be reused as
material *inputs* into a real renderer, never as the rendered
output.

### Diff scope: one tile region at a time

The unit of diffing is **one single sprite** — the atomic image the
game looks up.

- **Bespoke pipeline.** Pak128 packs many tiles per PNG, layout declared
  in an accompanying `.dat` file (e.g. entries like
  `Image[1][0]=foo.1.0` meaning "row 1, col 0 of foo.png" in
  tile-sized cells). `crop_ref.py` parses these and crops one tile.
  Diff against each pak128 sheet entry independently; do not score
  against the whole sheet. Square verification only applies to
  hex entries whose direction maps to a square direction (the 4
  hex axes that align with N/E/S/W). For hex-only entries — 120°
  curves, third-axis straights — the .dat may repoint to a
  less-faithful square sprite or to `IMG_EMPTY`; skip the square
  diff there and rely on visual inspection + bbox.
- **Parametric pipeline.** No external reference: each baker is the
  canonical source for its `(slope, …)` cells.  Validation is
  qualitative (eyeball the atlas, check `LightTexture` silhouette
  alignment via the engine's startup tripwire).  No `.dat` cropping
  needed.

### Texture vs. shape-only

For new assets without textured supervision yet, compare alpha mask
plus luminance over the alpha intersection (shape + shading, no
texture). Once the pakset's tile textures are wired in as material
inputs, switch to full RGB. `tools/3d/diff.py` does shape +
luminance today.

## Repo layout

Models live next to the pakset asset they generate or supervise, not
in a separate `models/` tree. Shared rendering/diff tooling lives at
`tools/3d/`. The two pipelines look like:

```
tools/
  3d/                                    # shared by both pipelines
    render.py                            # numpy z-buffer rasterizer (layer-tagged)
    diff.py                              # reference-vs-candidate score + 4-panel PNG
    crop_ref.py                          # extract one tile from a pak sheet via .dat

landscape/grounds/                       # parametric pipeline lives here.
                                         #   each baker dir is listed in
                                         #   Makefile DIRS128 so makeobj picks
                                         #   up the .dat from inside the dir.
  texture-lightmap/
    texture-lightmap.png             # baked deliverable (committed; makeobj input)
    texture-lightmap.dat             # baked deliverable (committed; makeobj input)
    render.py                            # per-slope lightmap cell
    build_pakset.py                      # bake the full atlas + .dat
  borders/
    borders.png / borders.dat            # baked deliverable (committed; makeobj input)
    render.py                            # per-slope grid-line cell
    build_pakset.py                      # bake the full atlas + .dat
  marker/
    marker.png / marker.dat              # baked deliverable (committed; makeobj input)
    render.py                            # per-slope marker half cell
    build_pakset.py                      # bake the full atlas + .dat
  water_ani/
    water_ani.png / water_ani.dat        # baked deliverable (committed; makeobj input)
    render.py                            # per-(depth,stage) animated water cell
    build_pakset.py                      # bake the full atlas + .dat
    legacy_reference.png                 # upstream pak128 art kept for compare.py
    compare.py                           # qualitative side-by-side eval
  texture-shore/
    texture-shore.png / texture-shore.dat # baked deliverable (committed; makeobj input)
    render.py                            # per-(slope, water_mask) ALPHA_RED beach mask
    build_pakset.py                      # bake the full atlas + .dat
  texture-slope/
    texture-slope.png / texture-slope.dat # baked deliverable (committed; makeobj input)
    render.py                            # per-(slope, corner_mask) ALPHA_GREEN|ALPHA_BLUE climate / snowline mask
    build_pakset.py                      # bake the full atlas + .dat
  back_wall/
    slopes.png / slopes.dat              # natural cliffs (Name=Slopes; committed; makeobj input)
    basement.png / basement.dat          # man-made cliffs (Name=Basement; committed; makeobj input)
    render.py                            # per-(wall, index, flavor) cliff-face cell
    build_pakset.py                      # bake both atlases + both .dats
    src/                                 # legacy Fabio Gonella rock-photo art kept
                                         #   for future texture-supervision input;
                                         #   not in DIRS128, not packaged
      slope.png / slope.dat              #   upstream pak128 Name=Slopes (rock photos)
      basement.png / basement.dat        #   upstream pak128 Name=Basement (rock photos)

infrastructure/rail_bridges/             # bespoke pipeline lives next to source art
  rail_060_bridge.png                    # upstream pakset art (kept; supervisory ref)
  rail_060_bridge.dat                    # upstream pakset descriptor (kept; packaged)
  rail_060_bridge/                       # 3D model + supervision artefacts
    scene.py                             # 3D parts (deck, pillar, ramp, …)
    build.sh                             # crop refs, render slices, diff each
    refs/                                # cropped pak128 sheet entries (cache)
    out_back.png, out_front.png          # rendered slices
    diff_debug_*.png                     # per-slice debug images
```

Conventions, in order:

- **Co-location.** A model directory shares a name (without extension)
  with the deliverable it produces. For parametric ground bakers the
  baked `.png`/`.dat` lives **inside** the model dir
  (`texture-lightmap/texture-lightmap.{png,dat}`,
  `borders/borders.{png,dat}`, `marker/marker.{png,dat}`,
  `water_ani/water_ani.{png,dat}`); each dir is listed in
  Makefile `DIRS128` so makeobj scans it.  For bespoke supervised
  assets the upstream pakset art still lives next to the model dir
  (`rail_060_bridge.{png,dat}` next to `rail_060_bridge/`) — until
  the model is shippable, the upstream art is the packaged
  deliverable, not the model output.
- **Hex-baked deliverables keep the legacy filename.** When a
  parametric synth family (borders, marker, texture-lightmap,
  water_ani, alpha, back_wall, …) has an existing pak128
  deliverable that the hex bake replaces outright, the baked output
  reuses the legacy name unchanged.  Even where the packing
  differs — `texture-lightmap` is one cell per slope here vs. one
  cell per `(climate × slope)` pair upstream — the filename stays
  the same; the `.dat` documents the new layout.  Apply this to
  every remaining synth family.
- **Generated outputs are committed.** PNGs and .dats produced by a
  baker are checked into git inside the model dir so reviewers see
  the current state without rebuilding. Re-running the baker should
  produce a byte-identical result; a future CI check will enforce
  that.
- **Source art for complex bespoke assets is kept** (e.g. the bridge
  PNG/dat) even after a model exists, both because models start out
  incomplete and because we want to keep them in sync with upstream
  pakset changes.
- **Source art is not packaged once a model produces sensible-quality
  output.** When that point is reached for a given asset, move the
  source art to a sibling `src/` (or similarly-named) subdir that
  makeobj does not scan; the model-baked PNG/dat in the parent dir is
  what gets packaged.
- **Old art that is fully superseded is deleted.** No `_old` suffixes,
  no commented-out blocks.  Git history is the changelog.  The
  square `texture-lightmap.{png,dat}` is gone for this reason — the
  hex bake under the same filename replaces it outright (and the
  packing differs, so the cells aren't comparable in-place).
- **No subdir-aware pakset compile.** Makeobj only scans the listed
  parent directory; model dirs (containing `.py`, `.sh`, `refs/`,
  `out_*.png`) are silently ignored. Adding a new model dir requires
  no Makefile change.
- **One file per baker.**  Default shape is a single file with the
  `render_cell()` function plus an `if __name__ == "__main__":
  hex_synth.bake_pakset(...)` block; same for bespoke single-layer
  assets (`rail_060_tracks/scene.py` is the worked example, with
  `bake_pakset()` next to the 3D parts and `HEX_ENTRIES`).  Four of
  the six parametric ground bakers still have a `render.py` /
  `build_pakset.py` split where the build file is ~50 lines of thin
  wrapper around `hex_synth.bake_pakset` — folding them is zero-content
  churn, leave them.  Verification harnesses (`rail_060_bridge/build.sh`,
  `rail_060_tracks/build.py`) stay separate from the bake — that role
  is genuinely different (crop refs, run renders, diff against pak128).

## Current state

### Bespoke pipeline: `rail_060_bridge`

Worked example for the bespoke pipeline. Multi-view supervision is
wired (one diff per pak128 sheet entry, no composite); orientation
was looked up in `viewport.cc::get_screen_coord` + `koord.cc`
rather than fitted; geometry tuned via structural recognition
against per-slice debug images. Score progression on the two
slices currently rendered (lower = better):

|                   | Back  | Front |
|-------------------|-------|-------|
| Composite (orig.) | 0.80  | n/a   |
| + multi-view      | 0.81  | 1.15  |
| + orientation     | 0.58  | 1.15  |
| + geometry tune   | 0.49  | 0.84  |

Outstanding work on this asset: X-bracing on the trestle (the
axis-aligned numpy rasterizer doesn't model diagonals well —
needs `add_quad` with explicit diagonal corners or a Blender
backend); fine-tune railing top height (Back XOR shows the
candidate is still ~6 px taller than the reference); the other
~28 sheet entries on this bridge (ramps, starts, pillars, EW
segments, winter variants); hex output (blocked on the engine-
side hex depth-clip plane spec — bridges are multi-layer
(Back / Front), so the depth-clip blocker bites here).

### Bespoke pipeline: `rail_060_tracks`

First single-layer bespoke asset (ballast + ties + rails, no
Front / Back split), and the worked example for shipping hex
output today: one `scene.py` (3D parts + `bake_pakset()`) that
emits both square pak128 dimetric (verified against cells 1.5 and
1.6) and the full 21-cell hex atlas the .dat names — 6 single-
edge stubs (ribi 1/2/4/8/16/32), 3 axis-straights, and all 12
bends — keyed by raw hex ribi.  120°-apart and opposite (180°)
edge pairs use a straight chord with mitred caps; 60°-apart pairs
use a hex-centred arc (the chord construct degenerates when the
shared corner sits closer than the ballast half-width); stubs are
a half-tile chord from the hex centre to the edge midpoint with a
clean perpendicular cut at the centre (no buffer-stop yet, the
rails just end).  Reuses `HexGeom` and `hash_noise01` from
`tools/3d/hex_synth.py` so square and hex output share dither
grain and silhouette anchor; `render.py` grew a
`projection="hex"` path with per-pixel hex plan-view clip
alongside.

### Parametric pipeline: hex ground deliverable baked

`landscape/grounds/texture-lightmap/render.py` is the canonical
renderer for hex ground tiles, and the source of truth for the hex
ground deliverable.  Camera, lift, light direction, shade math and
fill convention live in `tools/3d/hex_synth.py::HexGeom` plus its
companion helpers; an earlier crash-fast probe validated bit-for-bit
parity with the now-retired engine-side synth path; see
`hextrans/TODO.md` for the historical context.

`build_pakset.py` runs the renderer for every valid hex slope and
bakes a pak128-style deliverable into `landscape/grounds/`:

- `texture-lightmap.png` — atlas of 141 grayscale lightmap cells
  (12 × 12 × 128 px = 1536 × 1536 px). Each cell carries per-region
  Lambert shading as RGB8 grayscale (5-bit `brightness/16` expanded;
  identity = 132) and the hex silhouette as alpha. Per-region shading
  comes from a Python port of
  `synth_plane_partition.h::find_min_partition`, so multi-region
  slopes (saddles, wedges) get one Lambert face per coplanar region
  rather than a single averaged shade. Cell layout names follow
  pakset convention (`texture-lightmap.<row>.<col>`).
- `texture-lightmap.dat` — `Obj=ground`, `Name=LightTexture`,
  one `Image[<slope_t>][0]` entry per normalised slope shape, indexed
  by the **raw `slope_t` value itself** (base-4 per corner: E=1,
  SE=4, SW=16, W=64, NW=256, NE=1024). The engine's hex-aware ground
  lookup calls `get_image_ptr(slope - hgt_shift)` directly without a
  compact-index translation table. The index space is sparse — only
  the 141 normalised shapes (per-edge delta ≤ 1, min(corner_heights)
  == 0, since base elevation lives in the tile's `hgt` field, not in
  the slope encoding) appear out of 3655 declared slots. Invalid
  encodings read as IMG_EMPTY and are never requested at runtime
  because they can't appear on real terrain.

The climate texture is **not** regenerated: pak128's existing
`landscape/grounds/texture-climate.png` is real biome art (grass,
sand, …) with no tile geometry baked in, so we reuse it unchanged.
The runtime path is `create_textured_tile(hex_lightmap[slope],
texture-climate[c])`, mirroring the square pakset's
`(texture-lightmap × ClimateTexture)` model.

**Engine consumption is the next blocker.** The engine's
`get_ground_tile` still indexes via `climate_image[c] +
doubleslope_to_imgnr[slope]` (square projection, 81 slopes); a
hex-aware lookup that consumes the 340-slope `LightTexture` block
is engine-side work.  Until that lands, the baked PNG sits unused
on disk.

### What's reusable across both pipelines

- `tools/3d/crop_ref.py` — pak128 sheet cropping (bespoke).
- `tools/3d/diff.py` — shape + luminance score + 4-panel
  debug PNG.
- `tools/3d/render.py` — numpy z-buffer rasterizer with
  layer tagging (now used by `rail_060_bridge`).
- `tools/3d/hex_synth.py` — shared utilities for the parametric
  pipeline: `HexGeom` (per-slope vertex layout), raw-`slope_t`
  decoding, `iter_valid_slopes()`, `find_min_partition` (Python
  port of the engine's old plane-partition helper), Lambert
  lighting, polygon fill, Bresenham `draw_line`, and `bake_pakset`
  (per-asset bakers pass a `render_cell` callback, per-asset doc
  paragraph, and an `iter_entries` callback; the helper handles
  argparse, atlas, .dat header, per-line comment, and stderr
  summary).  Keeps the lightmap, borders, marker and back_wall
  bakers in lockstep; each per-asset `build_pakset.py` is now
  ~50 lines, mostly the per-asset doc paragraph.

### Parametric pipeline: hex grid-border deliverable baked

`landscape/grounds/borders/render.py` is the canonical renderer
for hex grid-line cells: the 3 north-side edges of the hex outline
at the slope's lifted vertices (open polyline E → NE → NW → W),
drawn in pak128 dark-grey (32, 32, 32) on a transparent background.
Single-side per tile mirrors square pak128's borders convention
(the south neighbour's back edges cover this tile's south side).
`build_pakset.py` runs the renderer for every valid hex slope and
bakes `landscape/grounds/borders/borders.{png,dat}`, replacing the
upstream 27-entry square deliverable on this fork.  The .dat
indexes by raw `slope_t` (same convention as `LightTexture`).
Engine consumption is the next blocker — `get_border_image` still
packs `(slope&1) + ((slope>>1)&6)` into 8 square indices; needs
the same hex-aware lookup as `get_ground_tile`.

### Parametric pipeline: hex water_ani deliverable baked

`landscape/grounds/water_ani/render.py` is the canonical renderer
for animated open-water cells.  The renderer is the source of truth
and validation against the legacy square `water_ani.png` is
qualitative (same kind of muted-blue surface, hex silhouette
instead of diamond).  The 32-
frame loop is two superposed sine waves with integer-wavelength
counts inside the period so frame 31 reads back into frame 0
seamlessly; the base colour is `(60, 95, 130)` muted navy/teal,
modulated by ±9 RGB units of ripple.  Outside the hex silhouette is
`alpha = 0` (matching borders / marker), not the
`(231, 255, 255)` transparency-key colour the legacy square
`water_ani.png` uses.

`build_pakset.py` is standalone (doesn't go through
`hex_synth.bake_pakset`) — that helper iterates valid slopes ×
halves, but water_ani's atlas axes are `(depth, stage)` rather
than slope-keyed.  The .dat emits all 6 × 32 = 192 cells under
one `Obj=ground / Name=Water` block, matching the legacy row count
exactly.  All `(depth, stage)` cells are required: the engine's
wasser_t draw path (`grund.cc::display`) calls
`sea->get_image(depth, stage)` with the running animation stage
on every depth tier, so leaving stages 1..31 of a deep-water tier
undeclared would flicker the sprite out for 31/32 of every cycle.
The engine clamps depth at `water_depth_levels = count - 2` (= 4
for our N_DEPTHS = 6); depth 5 is reserved / unreachable but kept
to match the legacy row count and the `count - 2` formula.  Atlas
is 16×12 cells (2048×1536 px), overwriting the legacy on this fork.

Image[0][stage] is also consumed on a second engine path —
`create_texture_from_tile` in `ground_desc.cc` uses it as a
transparency-keyed overlay multiplied with the climate's water
texture for shore tiles via `get_water_tile(slope, stage)`.  That
path hardcodes square-dimetric tile-replication offsets (cell +
copies at `±ref_w/2, ±ref_w/4`) so it doesn't currently produce
correct output for hex-silhouette overlays — engine-side hex port
issue, not fixable from the pakset side.

The depth ramp matches the legacy per-row mean RGB within ~1 unit
per channel ((79, 90, 117) at depth 0 → (62, 70, 91) at depth 5,
~5% darker per channel per tier).

This is still **flat-only on slope**.  `get_water_tile`'s second
axis (`stage + water_animation_stages * doubleslope_to_imgnr[slope]`)
collapses to slope_idx = 0 here pending engine-side hex water lookup
and a design call on whether the hex pakset ships per-slope
shoreline tiles in `Water` or pushes the wet/dry boundary entirely
into the alpha shore-transition family.

### Parametric pipeline: hex marker deliverable baked

`landscape/grounds/marker/render.py` is the canonical renderer
for hex marker (cursor) cells: an open polyline at the slope's
lifted vertices — `E → SE → SW → W` for the front half (3
south-side edges) or `E → NE → NW → W` for the back half (3
north-side edges) — drawn in bright orange `(255, 128, 0)` on a
transparent background.  Colour matches the only non-background
pixel value in the upstream pak128 `marker.png` this fork
overwrites.  The two halves bracket tile content at draw time
(back drawn before vehicles/buildings, front drawn after) so the
cursor silhouette wraps around objects on the tile.

`build_pakset.py` runs the renderer for every valid hex slope
× both halves and bakes `landscape/grounds/marker/marker.{png,dat}`,
overwriting the legacy 27-front-+-27-back square deliverable on
this fork.  The atlas is 282 cells (141 fronts in
`iter_valid_slopes()` order followed by 141 backs in the same
order); the .dat emits two `Image[<slope_t>][k]` entries per
slope (`k=0` front, `k=1` back) indexed by raw `slope_t` (same
convention as `LightTexture` / `Borders`).  Engine consumption
is the next blocker — `get_marker_image` still uses the legacy
square hang-formula (`hang%27` / `(hang%3) + ((hang-(hang%9))/3)`)
into 27-entry compact ranges; needs the same hex-aware lookup as
the other synth families.

### Parametric pipeline: hex slope-transition deliverable baked

`landscape/grounds/texture-slope/render.py` is the canonical
renderer for the hex SlopeTrans alpha — the cell read by
`grund.cc::display` for **climate-corner mixing**
(`get_alpha_tile(slope, corners)` with `ALPHA_GREEN | ALPHA_BLUE`)
and **snowline transitions** (`get_alpha_tile(slope)` with
`ALPHA_GREEN | ALPHA_BLUE` for case 1, `ALPHA_BLUE` alone for the
mid-slope case 2).  Cells use `hex_synth.silhouette_mask` so each
`(slope, corner_mask)` cell is bit-identical in alpha shape to the
matching `LightTexture[slope]` cell, and the engine's `draw_alpha`
walks source and alpha streams in lockstep without a runtime
normalisation cache.

The cell's interior is a 3-band quantisation of a barycentric
centre-fan strength field (the same shape function `texture-shore`
uses for wetness, just on a corner-mask 0/1 weight) with a
position-deterministic hashed dither at the band boundaries:

  RED   — alpha=0 under both alpha keys; base climate stays.
  GREEN — opaque under `ALPHA_GREEN | ALPHA_BLUE`; transparent
          under `ALPHA_BLUE` alone.
  BLUE  — opaque under both keys (the inner / highest mask region).

One bake serves both readers: climate transitions pass the
`climate_corners` mask; the snowline path passes
`high_corners_of(slope)` (corners with `corner_height > 0`).

`build_pakset.py` runs the renderer for every valid hex slope ×
every nonempty 6-bit corner mask and bakes
`landscape/grounds/texture-slope/texture-slope.{png,dat}`,
overwriting the legacy 15-cell square deliverable on this fork.
The atlas is **8883 cells** (141 slopes × 63 masks); the .dat
emits one `Image[<slope_t>][<corner_mask>]` line per cell indexed
by raw `slope_t` and 6-bit corner mask (same convention as
`ShoreTrans`).  Climate transitions don't have shore's "must be
sea level" constraint, so the mask axis stays full at 63 — the
atlas is ~10× shore's at ~16 MB on disk, ~115 MB compiled into
the pak.  Heavy but accepted for now; deduplication via hex
dihedral symmetry (each orbit cuts ~12×) is the obvious followup
if the size ever bites.

Engine consumption is wired: `ground_desc_t::init_ground_textures`
dropped the per-slope rotation case-table + `create_alpha_tile`
diamond-unwarp projection (the legacy 15-cell square pipeline);
`get_alpha_tile(slope, corners)` and `get_alpha_tile(slope)` are
now direct `transition_slope_texture->get_image(...)` lookups.
Init-time silhouette tripwire mirrors the shore one.

### What's missing

- Engine-side hex lookup that indexes the raw-`slope_t` blocks
  (`LightTexture`, `Borders`, `Marker`) instead of the square
  `climate_image[c] + doubleslope_to_imgnr[slope]` /
  `(slope&1) + ((slope>>1)&6)` / hang-formula paths. Without it,
  the baked atlases sit on disk unused.  Water_ani has the same
  blocker on the engine side (`ground_desc.cc::get_water_tile`
  still uses `doubleslope_to_imgnr`) plus a one-tier-vs-many-tiers
  decision before the second axis is meaningful.  SlopeTrans is
  done — `get_alpha_tile` reads the (slope, mask) bake directly.
### Recommended next iteration

1. Engine work to consume the new pakset block. On the hex branch
   of `SupraSummus/hextrans`, add a `get_hex_ground_tile(slope, c)`
   path that looks up the 0..339 compact slope index against
   `LightTexture`'s `climate_image_hex[c]` block, parallel to
   the existing square `get_ground_tile`. Once it lands, verify
   in-game on a pakset with `texture-lightmap`.

The first asset for the bespoke pipeline (vehicles or a simple
bridge) can start in parallel once the parametric pipeline's renderer
plumbing is sound — they share the camera/light/depth-clip
infrastructure.

## Commit message rules

Default to short. The diff already shows *what* changed; the message
captures only the *why* a reader can't recover from it. A one-line
subject with no body is the right answer for mechanical fixes and
obvious refactors.

Subject: short, present-tense, scope-prefixed (`hex-port shore:`,
`water_ani:`, `ci:`). Keep the prefix consistent across commits in
the same area. ≤ 72 chars.

Body: usually 1–2 short paragraphs, often none. Cover the
load-bearing reason, a non-obvious trade-off, a shim's retirement
trigger — anything that would surprise a reader who knows the
codebase but not this commit. Don't:

- Re-explain the surrounding subsystem; link to the file, symbol or
  prior commit.
- Enumerate every cell, slope or pixel-count delta the diff shows.
- Narrate verification ("re-baked, byte-identical", "atlas
  reproduces").
- Recap the companion engine commit; name it and stop.
- Inline durable design context. That belongs in `TODO.md` /
  `CLAUDE.md`, where it stays current.

If a body is getting long, prefer splitting the commit or moving the
context into `TODO.md` / `CLAUDE.md`.

## Workflow rules

- Stream branch name is set per session by the harness (currently
  `claude/review-pak-3d-modeling-Uy9vT`). The companion engine repo
  is `SupraSummus/hextrans` on the same branch name. Cross-repo
  changes are coordinated.
- For engine reference (the `simutrans` baseline) keep a `git
  worktree` of `SupraSummus/hextrans` on branch `simutrans` parallel
  to the `claude/...` branch.  The session-start hook can set this
  up; in this session it's at `/home/user/hextrans-simutrans/`.
- Commit small, push often; no PRs unless the user asks.

## Open questions / TBD

- **Hex depth-clip planes for bespoke output.** Only relevant for
  assets that use a Front / Back layer split (bridges, vehicles,
  multi-storey buildings) — those re-render 3D scenes through the
  hex camera with hex depth planes to produce per-layer hex sheet
  entries, and the hex equivalents of pak128's depth planes need
  an explicit spec on the engine side, anchored against the same
  hex camera the bakers already use (`tools/3d/hex_synth.py::HexGeom`).
  Single-layer assets —
  tracks, roads, trees, simple buildings — render through one hex
  camera with no depth slicing and are unblocked today;
  `rail_060_tracks` is the worked example. Doesn't block
  parametric pipeline work.
- **Optimization loop.** Manual edit + diff for now. Camera-parameter
  auto-fit (scipy over tilt/offset/scale) is a clear next step once
  shape is roughly right. True geometry optimization is much harder
  and probably never automated end-to-end.
- **Multi-slice supervision plumbing.** For the bespoke pipeline, the
  diff is taken against N pak128 sheet entries simultaneously. How is
  the aggregate score combined (sum, max, per-slice gating)? How
  does the agent see per-slice debug images without information
  overload? Defer until the first bespoke asset.
