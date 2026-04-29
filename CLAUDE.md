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
   neighbour height diff). The engine currently generates them
   algorithmically at startup via `synth_overlay::{get_ground, get_marker,
   get_border, get_alpha, get_back_wall}` (`src/simutrans/descriptor/
   synth_overlay.h` on the `simutrans` branch of `SupraSummus/hextrans`).
   That code lives in the engine for experimentation convenience; the
   target state is to **bake** its output into the hex pakset and flip
   `synth_overlay::prefer_over_pakset` to false. For these assets the
   pipeline is: parametric scene → render → diff against the engine's
   synth output (the actual ground truth) → sweep over all parameter
   combinations → commit PNGs to the pakset.

2. **Bespoke 3D assets** — vehicles, bridges, buildings, trees, factories.
   Each has hand-authored art in pak128. Here we genuinely have to model
   in 3D, supervised against pak128's existing sprite sheets, and
   re-render through the hex camera. The render-and-diff loop below is
   for this case.

The two pipelines share a renderer (camera, lighting, projection,
depth-clip slicing) but have different reference data and different
deliverables. The first parametric deliverable —
`landscape/grounds/texture-hex-lightmap.{png,dat}` baked from
`landscape/grounds/texture-hex-lightmap/` — is pipeline (1).

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
- **Hex synth ground truth**: `descriptor/synth_overlay.h` (interface)
  + `descriptor/synth_geometry.h` (camera, lift, light direction,
  vertex layout). The hex deliverable's reference is whatever
  `synth_overlay::*` returns at runtime; the directional light is
  `L = (-1, 1, 2)` calibrated so flat = 1.0×.
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
  rather than guessing from the offset.
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
1. **Read the .dat.** Enumerate every sheet entry the asset
   contributes. For bridges, that's BackImage / FrontImage / BackRamp
   / FrontRamp / BackStart / FrontStart / BackStart2 / FrontStart2 ×
   directions, plus pillars. Note seasons and the per-entry sheet
   offset.
2. **Look up engine facts.** Pull from the reference card above
   anything you'll need — compass, image enum, .dat key meaning,
   sheet offset semantics. Do this before opening the scene file.
3. **Map sheet entries to model layers.** Each entry is a 2D view of
   the asset under a specific (camera, depth-clip). Decide which 3D
   sub-parts go in which layer. Skip the composite-only first pass
   from earlier drafts of this doc — it hides per-slice errors.
4. **Stand up the build.** `build.sh` crops every reference, runs the
   scene, and diffs each candidate against its reference.
   Per-slice scores in the output.
5. **Iterate via structural recognition, not gradient descent.** Look
   at each per-slice debug image, spot what 3D structure the
   reference shows that the candidate lacks, change it, rerun.

A few concrete habits:

- **Bbox-check every iteration.** Print x/y range and pixel count
  for each reference and candidate. The eye misses silent shifts;
  bboxes catch them in two seconds.
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

- **Parametric pipeline.** Reference = engine's `synth_overlay::*`
  output captured headlessly. Camera + light from `synth_geometry.h`.
  Deliverable: baked PNGs replacing the algorithmic generator.
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
   + the hex depth-plane spec (engine-side, currently TBD — open
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
  against the whole sheet.
- **Parametric pipeline.** The reference is one PNG per parameter
  combination (one slope × climate, one marker × slope, etc.), captured
  from the engine's `synth_overlay::*` output and stored under
  `landscape/grounds/<family>/refs/` (or wherever the family lives).
  No `.dat` cropping needed.

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

landscape/grounds/                       # parametric pipeline lives here
  texture-hex-lightmap.png               # baked deliverable (committed; makeobj input)
  texture-hex-lightmap.dat               # baked deliverable (committed; makeobj input)
  texture-hex-lightmap/                  # source for the deliverable above
    render.py                            # per-slope lightmap cell
    build_pakset.py                      # bake the full atlas + .dat
  borders.png / borders.dat              # baked deliverable (committed)
  borders/                               # source for the deliverable above
    render.py                            # per-slope grid-line cell
    build_pakset.py                      # bake the full atlas + .dat
  marker.png / marker.dat                # baked deliverable (committed)
  marker/                                # source for the deliverable above
    render.py                            # per-slope marker half cell
    build_pakset.py                      # bake the full atlas + .dat
  …                                      # (other ground/.dat families to follow:
                                         #  alpha/, back_wall/)

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
  with the deliverable it produces, and sits next to it. Lightmap:
  `texture-hex-lightmap/` next to `texture-hex-lightmap.{png,dat}`.
  Bridge: `rail_060_bridge/` next to `rail_060_bridge.{png,dat}`.
- **Hex-baked deliverables overwrite the legacy filename.** When a
  parametric synth family (borders, marker, alpha, back_wall, …)
  has an existing pak128 deliverable that the hex bake replaces
  outright, the baked output keeps the legacy name
  (`borders.{png,dat}`, `marker.{png,dat}`) rather than adding a
  `texture-hex-` prefix. Lightmap is the one exception — it kept
  the legacy `texture-` prefix and inserted `hex-` because the
  square deliverable was packed differently (one cell per
  `(climate × slope)` pair, not one per slope) and reusing the name
  would have been misleading. Apply the overwrite rule to every
  remaining synth family.
- **Generated outputs are committed.** PNGs and .dats produced by a
  baker live next to the model dir and are checked into git so
  reviewers see the current state without rebuilding. Re-running the
  baker should produce a byte-identical result; a future CI check will
  enforce that.
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
  no commented-out blocks. Git history is the changelog. The square
  `texture-lightmap.{png,dat}` is gone for this reason — the hex
  pipeline replaces it outright.
- **No subdir-aware pakset compile.** Makeobj only scans the listed
  parent directory; model dirs (containing `.py`, `.sh`, `refs/`,
  `out_*.png`) are silently ignored. Adding a new model dir requires
  no Makefile change.

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
side hex depth-clip plane spec).

### Parametric pipeline: hex ground deliverable baked

`landscape/grounds/texture-hex-lightmap/render.py` is the canonical renderer for
hex ground tiles. An earlier crash-fast probe validated bit-for-bit
that it reproduces the engine's `synth_overlay::rasterise_ground`
output for the flat tile across all 8 climates, so the documented
constants in `synth_geometry.h` (vertex layout, lift, light direction,
shade math, fill convention) are known reproducible. **Going forward
the renderer is the source of truth for the hex ground deliverable;
the engine's in-process synth path stays as a runtime fallback floor.**

`build_pakset.py` runs the renderer for every valid hex slope and
bakes a pak128-style deliverable into `landscape/grounds/`:

- `texture-hex-lightmap.png` — atlas of 141 grayscale lightmap cells
  (12 × 12 × 128 px = 1536 × 1536 px). Each cell carries per-region
  Lambert shading as RGB8 grayscale (5-bit `brightness/16` expanded;
  identity = 132) and the hex silhouette as alpha. Per-region shading
  comes from a Python port of
  `synth_plane_partition.h::find_min_partition`, so multi-region
  slopes (saddles, wedges) get one Lambert face per coplanar region
  rather than a single averaged shade. Cell layout names follow
  pakset convention (`texture-hex-lightmap.<row>.<col>`).
- `texture-hex-lightmap.dat` — `Obj=ground`, `Name=HexLightTexture`,
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
hex-aware lookup that consumes the 340-slope `HexLightTexture` block
is engine-side work. Until that lands, the synth path keeps serving
ground tiles in-process and the baked PNG sits unused on disk.

### What's reusable across both pipelines

- `tools/3d/crop_ref.py` — pak128 sheet cropping (bespoke).
- `tools/3d/diff.py` — shape + luminance score + 4-panel
  debug PNG.
- `tools/3d/render.py` — numpy z-buffer rasterizer with
  layer tagging (now used by `rail_060_bridge`).
- `tools/3d/hex_synth.py` — shared engine-mirror utilities for
  the parametric pipeline: `HexGeom` (per-slope vertex layout),
  raw-`slope_t` decoding, `iter_valid_slopes()`,
  `find_min_partition` (port of `synth_plane_partition.h`),
  Lambert lighting, polygon fill, Bresenham `draw_line`, and
  `bake_pakset` (per-asset bakers pass a `render_cell` callback,
  per-asset doc paragraph, and `halves=1|2`; the helper handles
  argparse, atlas, .dat header, per-line corner comment, and
  stderr summary).  Keeps the lightmap, borders, and marker
  bakers in lockstep with each other and with `synth_geometry.h`
  / `synth_overlay.cc`; each per-asset `build_pakset.py` is now
  ~50 lines, mostly the per-asset doc paragraph.

### Parametric pipeline: hex grid-border deliverable baked

`landscape/grounds/borders/render.py` is the canonical renderer
for hex grid-line cells, mirroring `synth_overlay::build_border`:
a closed 6-edge hex outline at the slope's lifted vertices, drawn
in pak128 dark-grey (32, 32, 32) on a transparent background.
Style matches the legacy `borders.png`, not the engine's debug
yellow `OUTLINE_COLOR` (which is for the in-process synth path
only).  `build_pakset.py` runs the renderer for every valid hex
slope and bakes `landscape/grounds/borders.{png,dat}`, replacing
the upstream 27-entry square deliverable on this fork.  The .dat
indexes by raw `slope_t` (same convention as `HexLightTexture`).
Engine consumption is the next blocker — `get_border_image` still
packs `(slope&1) + ((slope>>1)&6)` into 8 square indices; needs
the same hex-aware lookup as `get_ground_tile`.

### Parametric pipeline: hex marker deliverable baked

`landscape/grounds/marker/render.py` is the canonical renderer
for hex marker (cursor) cells, mirroring
`synth_overlay::build_marker`: an open polyline at the slope's
lifted vertices — `E → SE → SW → W` for the front half (3
south-side edges) or `E → NE → NW → W` for the back half (3
north-side edges) — drawn in bright orange `(255, 128, 0)` on a
transparent background.  Colour matches the only non-background
pixel value in the upstream pak128 `marker.png` this fork
overwrites; diverges from the engine's debug-yellow
`OUTLINE_COLOR = 0x7FE0` for the same reason borders does (the
engine's synth path is a runtime fallback floor that ships with
debug-friendly redundancy; the baked deliverable follows the
legacy art convention).  The two halves bracket tile content at
draw time
(back drawn before vehicles/buildings, front drawn after) so the
cursor silhouette wraps around objects on the tile.

`build_pakset.py` runs the renderer for every valid hex slope
× both halves and bakes `landscape/grounds/marker.{png,dat}`,
overwriting the legacy 27-front-+-27-back square deliverable on
this fork.  The atlas is 282 cells (141 fronts in
`iter_valid_slopes()` order followed by 141 backs in the same
order); the .dat emits two `Image[<slope_t>][k]` entries per
slope (`k=0` front, `k=1` back) indexed by raw `slope_t` (same
convention as `HexLightTexture` / `Borders`).  Engine consumption
is the next blocker — `get_marker_image` still uses the legacy
square hang-formula (`hang%27` / `(hang%3) + ((hang-(hang%9))/3)`)
into 27-entry compact ranges; needs the same hex-aware lookup as
the other synth families.

### What's missing

- Engine-side hex lookup that indexes the raw-`slope_t` blocks
  (`HexLightTexture`, `Borders`, `Marker`) instead of the square
  `climate_image[c] + doubleslope_to_imgnr[slope]` /
  `(slope&1) + ((slope>>1)&6)` / hang-formula paths. Without it,
  the baked atlases sit on disk unused.
- Renderer + atlas for the remaining synth families (alpha,
  back-wall). Should drop in cleanly via the
  `tools/3d/hex_synth.py` shared module — `bake_pakset` already
  handles the boilerplate, so each new family needs only a
  `render.py` and a ~50-line `build_pakset.py` shaped like the
  borders/marker callers.

### Recommended next iteration

1. Engine work to consume the new pakset block. On the hex branch
   of `SupraSummus/hextrans`, add a `get_hex_ground_tile(slope, c)`
   path that looks up the 0..339 compact slope index against
   `HexLightTexture`'s `climate_image_hex[c]` block, parallel to
   the existing square `get_ground_tile`. Once it lands, flip
   `synth_overlay::prefer_over_pakset` to false on a pakset with
   `texture-hex-lightmap` and verify in-game.
2. Repeat the bake-and-commit pattern for the remaining synth
   families. Borders and marker are done; alpha and back_wall are
   what's left.  Alpha is climate-keyed (one mask per climate
   transition) but otherwise close to borders in structure;
   back_wall is per-(wall × index) rather than per-slope, which
   `bake_pakset`'s slope-keyed iteration doesn't model — it'll
   need either an `iter_keys` parameter or a sibling helper.
   `fill_polygon` already lives in `tools/3d/hex_synth.py` for
   lightmap's per-region fills.

The first asset for the bespoke pipeline (vehicles or a simple
bridge) can start in parallel once the parametric pipeline's renderer
plumbing is sound — they share the camera/light/depth-clip
infrastructure.

## Workflow rules

- Stream branch name is set per session by the harness (currently
  `claude/review-pak-3d-modeling-Uy9vT`). The companion engine repo
  is `SupraSummus/hextrans` on the same branch name. Cross-repo
  changes are coordinated.
- For engine reference (the `simutrans` baseline and the in-engine
  `synth_overlay::*` ground truth), keep a `git worktree` of
  `SupraSummus/hextrans` on branch `simutrans` parallel to the
  `claude/...` branch. The session-start hook can set this up; in
  this session it's at `/home/user/hextrans-simutrans/`.
- Commit small, push often; no PRs unless the user asks.

## Open questions / TBD

- **Hex depth-clip planes for bespoke output.** The bespoke pipeline
  re-renders 3D assets through the hex camera with hex depth planes
  to produce hex sheet entries. The square pakset's depth planes are
  pak128 art convention; the hex equivalents need an explicit spec
  on the engine side (analogous to how `synth_geometry.h` defines
  the camera). Doesn't block parametric pipeline work.
- **Optimization loop.** Manual edit + diff for now. Camera-parameter
  auto-fit (scipy over tilt/offset/scale) is a clear next step once
  shape is roughly right. True geometry optimization is much harder
  and probably never automated end-to-end.
- **Multi-slice supervision plumbing.** For the bespoke pipeline, the
  diff is taken against N pak128 sheet entries simultaneously. How is
  the aggregate score combined (sum, max, per-slice gating)? How
  does the agent see per-slice debug images without information
  overload? Defer until the first bespoke asset.
