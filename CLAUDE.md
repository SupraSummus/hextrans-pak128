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
deliverables. The slope work in `models/terrain/` is pipeline (1).

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
  `models/tools/render.py`.
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
  `models/parametric/<family>/refs/`. No `.dat` cropping needed.

### Texture vs. shape-only

For new assets without textured supervision yet, compare alpha mask
plus luminance over the alpha intersection (shape + shading, no
texture). Once the pakset's tile textures are wired in as material
inputs, switch to full RGB. `models/tools/diff.py` does shape +
luminance today.

## Repo layout (proposed, evolves)

New work lives under a `models/` directory at the repo root, parallel
to `landscape/`, `vehicles/`, etc. The parametric and bespoke
pipelines have different shapes:

```
models/
  README.md                  # short pointer to this file
  tools/
    diff.py                  # diff CLI (reference vs candidate PNG)
    crop_ref.py              # extract a tile from a pak sheet via .dat
    capture_synth.py         # dump synth_overlay::* output as reference PNGs
    render.py                # shared Blender-Python render entrypoint
  parametric/                # pipeline (1): one scene, sweep parameters
    ground/                  # synth ground tile family
      scene.py               # parametric scene; takes (slope, climate)
      sweep.sh               # render full (slope x climate) grid
      out/                   # baked PNGs (slope_<id>_climate_<id>.png)
      refs/                  # captured synth_overlay::get_ground output
    marker/                  # synth marker family
    border/                  # synth border family
    alpha/                   # synth alpha-mask family
    back_wall/               # synth cliff-face family
  bespoke/                   # pipeline (2): one scene per asset
    bridges/
      rail_stone_bridge/     # one asset per directory
        scene.py             # 3D parts (deck, pillar, ramp, …)
        build.sh             # produces one PNG per pak128 sheet entry
        out/                 # rendered slices (back_ns.png, front_ns.png, …)
        score.txt            # last per-slice diff scores
    vehicles/
      ...
```

Open question: commit rendered outputs and scores, or regenerate?
Probably commit them so reviewers see the current state without
rebuilding.

## Current state

### Bespoke pipeline: `rail_060_bridge_NS`

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

### Parametric pipeline: not yet started

The first-pass terrain work in `models/terrain/flat_tile/` and
`models/terrain/slope_sw1/` was mis-targeted (diffed against
pak128's square-projection legacy lightmap rather than the
engine's hex synth output, and rendered with OpenSCAD's square
dimetric camera). Skip those directories; the parametric pipeline
needs to be rebuilt from scratch. Specifically, in the engine's
`descriptor/ground_desc.cc::create_textured_tile`, each slope's
`texture-lightmap` entry carries **both** silhouette (RLE alpha
runs) and multiplicative shading; matching the legacy square
lightmap doesn't move us toward the hex deliverable.

### What's reusable across both pipelines

- `models/tools/crop_ref.py` — pak128 sheet cropping (bespoke).
- `models/tools/diff.py` — shape + luminance score + 4-panel
  debug PNG.
- `models/tools/render.py` — numpy z-buffer rasterizer with
  layer tagging (now used by `rail_060_bridge_NS`).

### What's missing

- A `capture_synth.py` (or equivalent) that runs the engine
  headlessly and dumps `synth_overlay::*` outputs as PNGs into
  `models/parametric/<family>/refs/`. This is the parametric
  pipeline's ground truth.
- A renderer (Blender Python or numpy) using the hex camera +
  light from `synth_geometry.h` for the parametric pipeline.
- A parametric scene per synth family (ground, marker, border,
  alpha, back_wall) parametrised by `slope_t::type` and climate.

### Recommended next iteration

1. Stand up `capture_synth.py` and dump the synth ground tiles for
   all slopes × climates as `models/parametric/ground/refs/`.
2. Stand up a minimal Blender Python `render.py` whose camera and
   light are read straight from the constants in `synth_geometry.h`
   (don't re-derive). Smoke-test it on a flat hex tile vs. the synth
   flat reference; expect near-zero diff.
3. Extend the scene to take `slope_t::type` and corner heights via
   `hex_corner_height`, and sweep one climate. Diff every slope.
4. Once one climate matches, sweep over all climates by varying the
   climate texture input.
5. Bake the full sweep, commit PNGs to the pakset, and on the engine
   side flip `synth_overlay::prefer_over_pakset` to false to let the
   pakset take over.

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

- **Synth capture mechanism.** How exactly do we dump
  `synth_overlay::*` outputs as PNGs? Options: (a) a small standalone
  C++ harness that links the engine's descriptor module, calls the
  synth functions, and writes via the existing image writer; (b) a
  full headless engine run with a screenshot hook; (c) re-implement
  the synth algorithm in Python and trust they match. (a) is the
  cleanest; (c) defeats the purpose of having synth as ground truth.
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
