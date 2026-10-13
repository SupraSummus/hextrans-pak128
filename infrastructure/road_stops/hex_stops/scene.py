"""3D models of the pak128 road stops for the hex grid.

Every road stop in pak128 is the same kit: a cobbled platform on each
side of the road, plus, by size and era, a yellow bus-bay zigzag, a
kiosk, a canopy with benches, a mailbox, or a raised cargo dock with
crates.  `STOPS` lists each stop as a `StopParams`; one scene builds
any of them along any of the three hex axes.

A through stop has 12 layouts, `4 * axis + ends` (the engine's
`building_desc_t::has_axis_layouts`): axes 0, 1, 2 run N-S, NW-SE and
NE-SW, and the two end bits say where the platform stops, bit 0 at
its S/SE/SW end, bit 1 at its N/NW/NE end, both on a lone tile.  An
open end drops to the road in a ramp; a joined end runs to the hex
edge, into the next tile's platform.

Each axis renders twice: furniture on the side of the road nearer the
camera goes to `FrontImage` (drawn over vehicles), the rest to
`BackImage`.  On the N-S axis neither side is nearer, so all of it is
back.

Writes `<name>_hex.png` (a row per axis: back/front for its four end
cases) next to each `.dat`, and rewrites the image lines and `Dims` of
the `.dat`.

    python3 -m infrastructure.road_stops.hex_stops.scene
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from tools.threed.bespoke import bake_atlas
from tools.threed.hex_synth import hash_noise01
from tools.threed.render import HexCamera, Model, render
from tools.threed.building_kit import set_layouts
from tools.threed.solids import Frame, add_block, add_face, add_prism, add_roof
from tools.threed.way import edge_midpoint
from tools.threed.way_surface import APOTHEM

STOPS_DIR = Path(__file__).resolve().parent.parent

# Per axis, the edge the stop's road leaves through, both ways; `s` of
# its frame points there.
AXES = ("N", "NW", "NE")
LAYOUTS = 12                # 4 * axis + ends
RAMP = 0.12                 # length of the ramp at an open platform end

# Cross-section, in world units from the road centreline.
PLATFORM_IN, PLATFORM_OUT = 0.42, 0.62
PLATFORM_Z = 0.05
BAY_IN = 0.25           # zigzag band, on the carriageway edge

# Warmer and lighter than the city sidewalk ground (PAVEMENT_RGB), so a
# platform reads as a raised slab in town too.
COBBLE = (158, 152, 132)
KERB = (214, 212, 198)
PLATFORM_SIDE = (92, 90, 80)
YELLOW = (212, 175, 31)
BENCH = (96, 58, 34)
CRATE = (150, 104, 58)
POST = (70, 72, 78)


@dataclass(frozen=True)
class StopParams:
    name: str
    zigzag: bool = False
    kiosk: tuple[int, int, int] | None = None
    kiosk_glass: bool = False
    canopy: tuple[int, int, int] | None = None
    canopy_glass: bool = False
    mailbox: bool = False
    cargo: bool = False
    sign: bool = True


EARLY_WOOD = (112, 70, 40)
CLASSIC_GREY = (150, 150, 146)
MODERN_BLUE = (120, 150, 200)

STOPS = [
    StopParams("bus_stops_11"),
    StopParams("bus_stops_12", zigzag=True),
    StopParams("bus_stops_21", kiosk=EARLY_WOOD),
    StopParams("bus_stops_22", zigzag=True, kiosk=CLASSIC_GREY),
    StopParams("bus_stops_23", zigzag=True, kiosk=MODERN_BLUE,
               kiosk_glass=True),
    StopParams("bus_stops_41", canopy=(150, 146, 140)),
    StopParams("bus_stops_42", zigzag=True, canopy=CLASSIC_GREY),
    StopParams("bus_stops_43", zigzag=True, canopy=MODERN_BLUE,
               canopy_glass=True),
    StopParams("bus_stops_m2", zigzag=True, mailbox=True, sign=False),
    StopParams("cargohighstop", zigzag=True, cargo=True, sign=False),
]


# --- Geometry helpers ---------------------------------------------------------

def edge_frame(edge: str) -> Frame:
    """Frame of one axis: `s` along the road (towards the axis edge),
    `p` across it."""
    return Frame(edge_midpoint(edge))


def cobble_shader(kerb_p, fr: Frame, side: int):
    """Cobble speckle; the strip nearest the road is a lighter kerb."""
    base = np.array(COBBLE, float)
    kerb = np.array(KERB, float)

    def shader(wx, wy, sx, sy):
        p = (wx * fr.v[0] + wy * fr.v[1]) * side
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = np.empty((len(wx), 3))
        rgb[:] = base
        rgb *= np.where(n < 0.3, 0.8, np.where(n < 0.85, 1.0, 1.15))[:, None]
        k = p < kerb_p
        rgb[k] = kerb * (0.95 + 0.1 * n[k])[:, None]
        return rgb, np.ones(len(wx), bool)

    return shader


# --- Parts --------------------------------------------------------------------

def reach(p):
    """Half the hex's length along the axis at `p` across it."""
    return (2 * APOTHEM * (1 - p) if p > 0.5 else APOTHEM) - 0.02


def open_end(p_out=PLATFORM_OUT):
    """Where an open platform end stops, so that its ramp, down to where
    the hex is shortest across the platform, stays inside the hex."""
    return reach(p_out) - RAMP


def platform_poly(side, ends=0, p_in=PLATFORM_IN, p_out=PLATFORM_OUT):
    """Trapezoid between the platform's kerb and back lines, `p_in` and
    `p_out` from the way, ending on the hex edges so neighbouring stop
    tiles join into one platform; an open end (`ends` bit 0 at `-s`,
    bit 1 at `+s`) stops at `open_end`."""
    a_in, a_out, cut = reach(p_in), reach(p_out), open_end(p_out)
    lo_in, lo_out = (-cut,) * 2 if ends & 1 else (-a_in, -a_out)
    hi_in, hi_out = (cut,) * 2 if ends & 2 else (a_in, a_out)
    return [(lo_in, side * p_in), (hi_in, side * p_in),
            (hi_out, side * p_out), (lo_out, side * p_out)]


def ramps(model, fr, side, layer, ends, z1, colour, p_in=PLATFORM_IN,
          p_out=PLATFORM_OUT):
    """A slope from the platform down to the way at each open end."""
    cut = open_end(p_out)
    for bit, sign in ((1, -1), (2, 1)):
        if not ends & bit:
            continue
        top_s, foot_s = sign * cut, sign * (cut + RAMP)
        pts = [fr.world(top_s, side * p_in, z1),
               fr.world(top_s, side * p_out, z1),
               fr.world(foot_s, side * p_out, 0.002),
               fr.world(foot_s, side * p_in, 0.002)]
        add_face(model, pts, colour, layer,
                 outward=fr.world(0, side * (p_in + p_out) / 2, -1))


def platform(model, fr, side, layer, *, high=False, ends=0):
    z1 = 0.11 if high else PLATFORM_Z
    top = (150, 150, 146) if high else COBBLE
    add_prism(model, fr, platform_poly(side, ends), 0.0, z1, top, layer,
              top_shader=None if high else
              cobble_shader(PLATFORM_IN + 0.035, fr, side),
              side_color=(120, 120, 116) if high else PLATFORM_SIDE)
    ramps(model, fr, side, layer, ends, z1, top)
    if high:
        # Yellow safety line along the edge.
        a = APOTHEM - 0.04
        add_block(model, fr, -a, a, side * PLATFORM_IN,
                  side * (PLATFORM_IN + 0.035), z1, z1 + 0.003, YELLOW, layer)


def zigzag(model, fr, side, layer):
    """Yellow bus-bay zigzag painted along the platform kerb."""
    period = 2 * APOTHEM / 11             # whole teeth per tile
    lo, hi = BAY_IN, PLATFORM_IN
    yellow = np.array(YELLOW, float)

    def shader(wx, wy, sx, sy):
        s = wx * fr.u[0] + wy * fr.u[1]
        p = (wx * fr.v[0] + wy * fr.v[1]) * side
        f = np.abs((s / period) % 1.0 - 0.5) * 2         # 0..1 triangle
        line = lo + 0.02 + f * (hi - lo - 0.05)
        keep = (np.abs(p - line) < 0.02) | (np.abs(p - (lo + 0.01)) < 0.012)
        keep &= np.abs(s) < APOTHEM - 0.06
        rgb = np.empty((len(wx), 3))
        rgb[:] = yellow
        return rgb, keep

    q = [fr.world(s, side * p, 0.004)
         for s, p in ((-APOTHEM, lo), (APOTHEM, lo), (APOTHEM, hi),
                      (-APOTHEM, hi))]
    if np.cross(np.subtract(q[1], q[0]), np.subtract(q[3], q[0]))[2] < 0:
        q = q[::-1]
    model.add_quad(q, (0, 0, 0), layer=layer, shader=shader)


def sign(model, fr, side, layer, s=0.42, kerb=PLATFORM_IN):
    """Bus stop sign: grey pole, yellow plate with a green rim, just
    behind the platform kerb at `kerb` from the road axis."""
    p = side * (kerb + 0.05)
    z0 = PLATFORM_Z
    add_block(model, fr, s - 0.012, s + 0.012, p - 0.012, p + 0.012,
              z0, z0 + 0.34, POST, layer)
    add_block(model, fr, s - 0.06, s + 0.06, p - 0.01, p + 0.01,
              z0 + 0.25, z0 + 0.37, (40, 130, 70), layer)
    add_block(model, fr, s - 0.045, s + 0.045, p - 0.014, p + 0.014,
              z0 + 0.265, z0 + 0.355, (232, 200, 40), layer)


def kiosk(model, fr, side, layer, color, glass):
    s0, s1 = -0.26, 0.02
    p0, p1 = side * (PLATFORM_IN + 0.08), side * (PLATFORM_OUT - 0.02)
    z0 = PLATFORM_Z
    if glass:
        frame = (225, 228, 232)
        for s in (s0, s1):
            for p in (p0, p1):
                add_block(model, fr, s - 0.01, s + 0.01, p - 0.01, p + 0.01,
                          z0, z0 + 0.22, frame, layer)
        add_block(model, fr, s0, s1, p1 - side * 0.01, p1, z0 + 0.03,
                  z0 + 0.2, (150, 190, 215), layer)
        add_block(model, fr, s0 - 0.02, s1 + 0.02, min(p0, p1) - 0.02,
                  max(p0, p1) + 0.02, z0 + 0.22, z0 + 0.24, color, layer)
        bench(model, fr, side, layer, (s0 + s1) / 2,
              PLATFORM_OUT - 0.08)
        return
    add_block(model, fr, s0, s1, min(p0, p1), max(p0, p1), z0, z0 + 0.22,
              color, layer)
    # Roof overhang and a dark window facing the road.
    add_block(model, fr, s0 - 0.025, s1 + 0.025, min(p0, p1) - 0.025,
              max(p0, p1) + 0.025, z0 + 0.22, z0 + 0.245,
              tuple(int(c * 0.7) for c in color), layer)
    add_block(model, fr, s0 + 0.05, s1 - 0.05, p0 - side * 0.004, p0,
              z0 + 0.1, z0 + 0.18, (60, 56, 70), layer)


def bench(model, fr, side, layer, s, p_mid):
    p = side * p_mid
    z0 = PLATFORM_Z
    add_block(model, fr, s - 0.09, s + 0.09, p - 0.03, p + 0.03,
              z0 + 0.04, z0 + 0.055, BENCH, layer)
    add_block(model, fr, s - 0.09, s + 0.09, p + side * 0.02,
              p + side * 0.03, z0 + 0.055, z0 + 0.1, BENCH, layer)
    for ds in (-0.07, 0.07):
        add_block(model, fr, s + ds - 0.01, s + ds + 0.01, p - 0.02,
                  p + 0.02, z0, z0 + 0.04, (60, 50, 44), layer)


def canopy(model, fr, side, layer, color, glass):
    z0 = PLATFORM_Z
    p_in, p_out = PLATFORM_IN + 0.02, PLATFORM_OUT + 0.04
    posts = (-0.4, 0.0, 0.4)
    post_col = (225, 228, 232) if glass else (90, 92, 98)
    for s in posts:
        p = side * (p_out - 0.06)
        add_block(model, fr, s - 0.014, s + 0.014, p - 0.014, p + 0.014,
                  z0, z0 + 0.42, post_col, layer)
    for s in (-0.2, 0.2):
        bench(model, fr, side, layer, s, PLATFORM_OUT - 0.08)
    # Glass: brighter panes between white ribs; metal: darker seams.
    base = np.array(color, float)
    tone, amp, pitch, gap, gap_rgb = (
        (1.05, 0.1, 0.2, 0.42, (225, 228, 232)) if glass
        else (0.96, 0.08, 0.08, 0.4, None))

    def roof(wx, wy, sx, sy):
        s = wx * fr.u[0] + wy * fr.u[1]
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = base * (tone + amp * n)[:, None]
        line = np.abs((s / pitch) % 1.0 - 0.5) > gap
        if gap_rgb:
            rgb[line] = gap_rgb
        else:
            rgb[line] *= 0.86
        return rgb, np.ones(len(wx), bool)

    add_roof(model, fr, -0.5, 0.5, side * (p_in - 0.04),
             side * (p_out + 0.02), z0 + 0.4, z0 + 0.46, 0.02,
             color, layer, shader=roof)


def mailbox(model, fr, side, layer):
    s, p = -0.2, side * (PLATFORM_IN + 0.12)
    z0 = PLATFORM_Z
    add_block(model, fr, s - 0.012, s + 0.012, p - 0.012, p + 0.012,
              z0, z0 + 0.12, POST, layer)
    add_block(model, fr, s - 0.05, s + 0.05, p - 0.04, p + 0.04,
              z0 + 0.12, z0 + 0.24, (236, 190, 20), layer)
    add_block(model, fr, s - 0.055, s + 0.055, p - 0.045, p + 0.045,
              z0 + 0.24, z0 + 0.26, (60, 60, 70), layer)


def crates(model, fr, side, layer):
    z0 = 0.11
    for s, dp, h in ((-0.3, 0.1, 0.09), (-0.18, 0.12, 0.07), (0.1, 0.09, 0.1),
                     (0.24, 0.13, 0.06)):
        p = side * (PLATFORM_IN + dp)
        add_block(model, fr, s - 0.055, s + 0.055, p - 0.05, p + 0.05,
                  z0, z0 + h, CRATE, layer,
                  side_color=tuple(int(c * 0.85) for c in CRATE))


# --- Scene --------------------------------------------------------------------

def build(params: StopParams, layout: int) -> Model:
    ends = layout & 3
    fr = edge_frame(AXES[layout // 4])
    model = Model()
    front = fr.front_sign()
    # Furniture side: away from the camera when one side is nearer.
    back_side = -front if front else -1
    for side in (+1, -1):
        layer = "front" if side == front else "back"
        platform(model, fr, side, layer, high=params.cargo, ends=ends)
        if params.zigzag:
            zigzag(model, fr, side, layer)
    far, near = back_side, -back_side
    far_layer = "back"
    near_layer = "front" if front else "back"
    if params.kiosk:
        kiosk(model, fr, far, far_layer, params.kiosk, params.kiosk_glass)
    if params.canopy:
        canopy(model, fr, far, far_layer, params.canopy, params.canopy_glass)
    if params.mailbox:
        mailbox(model, fr, near, near_layer)
    if params.cargo:
        crates(model, fr, far, far_layer)
        crates(model, fr, near, near_layer)
    if params.sign:
        sign(model, fr, near, near_layer)
    return model


def render_layer(params, layout, layer):
    return render(build(params, layout), HexCamera(), layer_filter=layer)


# --- Bake ---------------------------------------------------------------------

CELL_ORDER = [(layout, layer) for layout in range(LAYOUTS)
              for layer in ("back", "front")]


def dat_lines(name: str) -> list[str]:
    lines = []
    for layout in range(LAYOUTS):
        row, col = layout // 4, (layout % 4) * 2
        lines.append(f"BackImage[{layout}][0][0][0][0]={name}_hex.{row}.{col}")
        lines.append(f"FrontImage[{layout}][0][0][0][0]="
                     f"{name}_hex.{row}.{col + 1}")
    return lines


IMAGE_LINE = re.compile(r"^\s*(Back|Front)Image\[")
LEGEND_LINE = re.compile(r"^#[0-7] ")   # old square layout legend


def rewrite_dat(path: Path, name: str) -> None:
    """Replace the image block of the stop in `path` (and the comments
    inside it) with `dat_lines`; leave icons and other keys alone."""
    lines = path.read_text(errors="replace").splitlines()
    idx = [i for i, line in enumerate(lines) if IMAGE_LINE.match(line)]
    first, last = idx[0], idx[-1]
    header = ["# Layouts 4 * axis + ends: axes N-S, NW-SE, NE-SW; end bit 0",
              "# at the S/SE/SW end, bit 1 at N/NW/NE.  Baked by",
              "# hex_stops/scene.py."]
    out = [line for line in lines[:first]
           if not LEGEND_LINE.match(line) and line not in header]
    block = header + dat_lines(name)
    out += block + lines[last + 1:]
    path.write_text("\n".join(out) + "\n")


def bake_pakset() -> None:
    for params in STOPS:
        entries = [(f"{layer}[{layout}]",
                    lambda p=params, lo=layout, la=layer:
                    render_layer(p, lo, la))
                   for layout, layer in CELL_ORDER]
        bake_atlas(out_png=STOPS_DIR / f"{params.name}_hex.png",
                   entries=entries, cols_per_row=8)
        rewrite_dat(STOPS_DIR / f"{params.name}.dat", params.name)
        set_layouts(STOPS_DIR / f"{params.name}.dat", LAYOUTS)


if __name__ == "__main__":
    bake_pakset()
