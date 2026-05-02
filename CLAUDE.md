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

Recurring lookup categories: tile-to-screen mapping
(`display/viewport.cc`), compass directions (`dataobj/koord.cc`),
slope encoding (`dataobj/ribi.h`), hex camera + lighting
(`tools/3d/hex_synth.py::HexGeom`, mirroring `display/hex_proj.h`),
per-asset-class .dat keys (the matching
`descriptor/writer/*_writer.cc`), and pak128 art conventions
(`devdocs/128painting.txt`). Engine repo is `SupraSummus/hextrans`;
a worktree of its `simutrans` branch is typically kept parallel to
the pakset checkout for these lookups.

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

## Modelling as programming

A scene is code that emits geometry — apply the usual code
hygiene.  DRY: a constant or helper used by two assets belongs in
a shared module (track cross-section in
`rail_tracks/rail_060_tracks/track_params.py`, atlas plumbing in
`tools/3d/bespoke.py`), not duplicated.  Separation of concerns:
per-asset `scene.py` owns geometry + the `(label, render_fn)`
entry list; `tools/3d/` owns rendering, atlas composition,
projection; `build.py` owns crop+render+diff orchestration.  One
source of truth across projections: the same 3D parts emit both
square and hex via `Scene.render(projection=…)` — never fork a
scene file per projection.  Refactor when the second consumer
arrives, not before; premature abstraction misfires the first
time a structural fact contradicts it.

The diff-against-pak128 step is the unit test: a structural
regression shows up as a bbox shift or a score drop on the
affected slice.

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
2. **Look up engine facts and existing helpers.** Grep the
   engine repo for whatever you need (compass, image enum, .dat
   key meaning, sheet offset semantics — see "Engine facts"
   above for the recurring lookup categories). Then skim
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
  (dither, taper, texture). A placement bug in a textured render
  reads as a shape bug — burning iterations on shape while
  placement is off is the classic trap.
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
- **Back-solve from reference geometry.** Measure a reference
  feature in pixels, divide by the projection's px-per-world-unit
  at the relevant axis, get the world-space extent. Do this
  before tweaking the constant.
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
tools/3d/                                # shared rendering, diff, cropping
                                         # (z-buffer rasterizer, hex camera,
                                         # bake_pakset helper)

landscape/grounds/<name>/                # parametric pipeline.
  <name>.png, <name>.dat                 # baked deliverable (committed)
  render.py                              # per-cell renderer
  build_pakset.py                        # bakes the atlas + .dat
  src/                                   # (optional) legacy art retained as
                                         # texture-supervision input; not in
                                         # DIRS128, not packaged
                                         #
                                         # current bakers: texture-lightmap,
                                         # borders, marker, water_ani,
                                         # texture-shore, texture-slope,
                                         # back_wall. each dir listed in
                                         # Makefile DIRS128.

infrastructure/<class>/<name>/           # bespoke pipeline. upstream
  scene.py                               # <name>.{png,dat} stays alongside
  build.sh or build.py                   # the model dir until the model
  refs/, out_*.png, diff_debug_*.png     # ships.
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

## Worked examples

For the parametric pipeline, `landscape/grounds/texture-lightmap/`
is the canonical reference: per-slope `render_cell()` plus a
`build_pakset.py` that calls `hex_synth.bake_pakset`. The other
ground bakers (borders, marker, water_ani, texture-shore,
texture-slope, back_wall) are variations on the same shape and
each is worth a glance for the part you're working on (atlas
axis, alpha key, .dat header).

For the bespoke pipeline, `infrastructure/rail_tracks/rail_060_tracks/`
is the worked example for shipping hex output today (single-layer,
one `scene.py` emitting both square + hex via `bake_pakset()`).
`infrastructure/rail_bridges/rail_060_bridge/` is the worked example
for multi-view supervision against pak128 sheet entries (multi-layer
square; hex bake of NS Back/Front via `bake_pakset()` →
`rail_060_bridge_hex.{png,dat}` — partial coverage of the bridge
sheet, see `TODO.md`).

Per-asset state — what's done, what's blocked, what's coming next —
lives in `git log` and `TODO.md`, not here.

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
- Session checkouts are typically shallow. If you need older
  history, `git fetch --unshallow` first.

## Open questions / TBD

- **Optimization loop.** Manual edit + diff for now. Camera-parameter
  auto-fit (scipy over tilt/offset/scale) is a clear next step once
  shape is roughly right. True geometry optimization is much harder
  and probably never automated end-to-end.
- **Multi-slice supervision plumbing.** For the bespoke pipeline, the
  diff is taken against N pak128 sheet entries simultaneously. How is
  the aggregate score combined (sum, max, per-slice gating)? How
  does the agent see per-slice debug images without information
  overload? Defer until the first bespoke asset.
