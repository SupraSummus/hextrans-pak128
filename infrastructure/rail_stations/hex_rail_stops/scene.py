"""3D models of the pak128 small rail stops for the hex grid.

The ten one-tile rail stops are through stops, a platform along each
side of the track plus what makes each one: a glass hall, a station
house, an office, a closed shed, freight gear, a coal loader or
containers.  `STOPS` lists them as `RailStopParams`; one scene builds
any of them along any hex axis, with the axes, layouts and `.dat`
rewrite of the road stops (`infrastructure.road_stops.hex_stops`):
12 layouts, `4 * axis + ends`, an open platform end ramped down.

Parts on the camera side of the track go to `FrontImage`, as do roofs
over the track, which a train passes under.

    python3 -m infrastructure.rail_stations.hex_rail_stops.scene
    python3 -m infrastructure.rail_stations.hex_rail_stops.scene --preview out.png
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from infrastructure.road_stops.hex_stops.scene import (
    AXES, LAYOUTS, bench, edge_frame, platform_poly, ramps, rewrite_dat)
from infrastructure.road_stops.hex_terminals.scene import junction_preview
from tools.threed.bespoke import bake_atlas
from tools.threed.building_kit import (
    STOREY, Palette, add_beam, facade, gabled_block, set_layouts,
    speckle_shader)
from tools.threed.hex_synth import hash_noise01
from tools.threed.render import HexCamera, Model, render
from tools.threed.solids import (
    Frame, add_block, add_frustum, add_prism, add_roof)
from tools.threed.way_surface import APOTHEM

STATIONS_DIR = Path(__file__).resolve().parent.parent
RAIL_060 = STATIONS_DIR.parent / "rail_tracks" / "rail_060_tracks.dat"

# Cross-section, in world units from the track centreline.
P_IN, P_OUT, P_Z = 0.22, 0.62, 0.05
# Halls over the track reach this far out: up to here the hex has its
# full length along the track, so the halls of stops in a row join.
HALL_W = 0.5
CONCRETE = (172, 170, 162)
EDGE = (226, 224, 214)
SIDE = (110, 108, 100)
IRON = (96, 120, 156)
WHITE = (226, 228, 230)
GLASS = (170, 196, 214)
DARK = (52, 50, 54)
YELLOW = (226, 186, 40)
COAL = (46, 44, 48)
CONTAINERS = ((190, 50, 44), (230, 230, 226), (44, 72, 150), (60, 130, 70),
              (220, 150, 40), (200, 180, 130), (40, 40, 44))
HOUSE = Palette(wall=(214, 196, 160), trim=(240, 232, 214),
                roof=(176, 92, 60), glass=(56, 66, 84))
OFFICE = Palette(wall=(150, 84, 62), trim=(220, 210, 190),
                 roof=(150, 82, 56), glass=(56, 66, 84))


@dataclass(frozen=True)
class RailStopParams:
    name: str                 # .dat stem; the object's name is the .dat's
    hall: str | None = None   # "glass", "mesh" or "shed" over the track
    house: str | None = None  # "village" or "office" on the far side
    freight: bool = False     # forklift and crates
    coal: bool = False        # loader bunker over the track
    containers: int = 0       # container stacks per side
    benches: bool = True


STOPS = [
    RailStopParams("trainstop", hall="glass"),
    RailStopParams("villagetrainstop", house="village"),
    RailStopParams("officetrainstop", house="office", benches=False),
    RailStopParams("opentrainstop", benches=False),
    RailStopParams("closedtrainstop", hall="shed", benches=False),
    RailStopParams("moderntrainstop", hall="mesh"),
    RailStopParams("freighttrainstop", freight=True, benches=False),
    RailStopParams("coaltrainstop", coal=True, benches=False),
    RailStopParams("container1trainstop", containers=1, benches=False),
    RailStopParams("container2trainstop", containers=2, benches=False),
]


def platform(model, fr, side, layer, ends):
    """A platform from the hex edges, or a ramp short of them at an open
    end (`ends` bit 0 at `-s`, bit 1 at `+s`)."""
    base = np.array(CONCRETE, float)

    def top(wx, wy, sx, sy):
        p = np.abs(fr.local(wx, wy)[1])
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = base * (0.94 + 0.1 * n)[:, None]
        rgb[p < P_IN + 0.03] = EDGE
        rgb[np.abs(p - P_IN - 0.045) < 0.006] = YELLOW
        return rgb, np.ones(len(wx), bool)

    add_prism(model, fr, platform_poly(side, ends, P_IN, P_OUT), 0.0, P_Z,
              CONCRETE, layer, top_shader=top, side_color=SIDE)
    ramps(model, fr, side, layer, ends, P_Z, CONCRETE, P_IN, P_OUT)


def lamp(model, fr, s, p, layer):
    add_block(model, fr, s - 0.01, s + 0.01, p - 0.01, p + 0.01, P_Z, 0.42,
              DARK, layer)
    add_block(model, fr, s - 0.03, s + 0.03, p - 0.03, p + 0.03, 0.4, 0.43,
              WHITE, layer)


# --- Halls over the track -----------------------------------------------------

def bays(n):
    """`n` positions along the tile, evenly spaced across tile borders
    too, so that a row of stops keeps the same pitch."""
    return [(k + 0.5) * 2 * APOTHEM / n - APOTHEM for k in range(n)]


def arch_hall(model, fr, colour, glass, *, rise=0.3, springing=0.38,
              ribs=4, roof_tone=None):
    """Columns along both platforms carrying an arched roof over the
    track: ribs across and glazing between them."""
    w, a = HALL_W, APOTHEM
    n = 10
    prof = [(-w * math.cos(math.pi * k / n),
             springing + rise * math.sin(math.pi * k / n)) for k in range(n + 1)]
    for s in bays(ribs):
        for side in (-1, 1):
            add_block(model, fr, s - 0.015, s + 0.015, side * w - 0.015,
                      side * w + 0.015, P_Z, springing,
                      colour, "front" if side == fr.front_sign() else "back")
        for (p0, z0), (p1, z1) in zip(prof, prof[1:]):
            add_beam(model, fr.world(s, p0, z0), fr.world(s, p1, z1), 0.02,
                     colour, layer="front")
    tone = roof_tone or glass
    for k, ((p0, z0), (p1, z1)) in enumerate(zip(prof, prof[1:])):
        mid = abs(k - n / 2 + 0.5) < 2
        add_roof(model, fr, -a, a, p0, p1, z0, z1, 0.008,
                 tone if mid else glass, "front",
                 shader=None if mid else glass_shader(fr, glass, colour))


def glass_shader(fr: Frame, glass, rib):
    glass, rib = np.array(glass, float), np.array(rib, float)

    pitch = 2 * APOTHEM / 19   # a whole number of panes per tile

    def shader(wx, wy, sx, sy):
        s = fr.local(wx, wy)[0]
        n = hash_noise01(sx.astype(np.uint32), sy.astype(np.uint32))
        rgb = glass * (0.95 + 0.1 * n)[:, None]
        rgb[np.abs(((s + APOTHEM) / pitch) % 1.0 - 0.5) > 0.42] = rib
        return rgb, np.ones(len(wx), bool)

    return shader


def shed(model, fr):
    """A closed goods shed over the track: walls along the platform
    backs, the ends open, a pitched roof with roof lights."""
    w, a = HALL_W - 0.06, APOTHEM
    eave, ridge = 0.42, 0.62
    wall = (150, 150, 146)
    for side in (-1, 1):
        layer = "front" if side == fr.front_sign() else "back"
        add_block(model, fr, -a, a, side * w - 0.02, side * w + 0.02, 0.0,
                  eave, wall, layer, side_shader=speckle_shader(wall))
        add_roof(model, fr, -a, a, side * HALL_W, 0.0,
                 eave - 0.02, ridge, 0.025, (130, 132, 134), "front",
                 shader=speckle_shader((130, 132, 134)))
        for s in bays(3):
            add_roof(model, fr, s - 0.07, s + 0.07, side * w * 0.6,
                     side * w * 0.25, eave + (ridge - eave) * 0.4 + 0.026,
                     eave + (ridge - eave) * 0.75 + 0.026, 0.004, GLASS,
                     "front")
        # Windows along the wall, a row of dark panes.
        for s in bays(5):
            add_block(model, fr, s - 0.05, s + 0.05, side * (w + 0.021),
                      side * (w + 0.024), 0.22, 0.34, DARK, layer)


# --- Buildings on the far platform --------------------------------------------

def station_house(model, fr, side, layer, kind):
    """A house standing on the back of the far platform, its front
    to the track."""
    house = Frame((fr.v[0] * side, fr.v[1] * side),
                  origin=fr.world(0.0, 0.0, 0.0)[:2])
    if kind == "village":
        gabled_block(model, house, P_IN + 0.14, P_OUT + 0.04, 0.3, 2, HOUSE,
                     pitch=0.2, stepped=False, bays=3)
        # A glass-free canopy on the platform in front of it.
        add_roof(model, fr, -0.45, 0.45, side * (P_IN + 0.02),
                 side * (P_IN + 0.16), 0.36, 0.4, 0.02, (90, 92, 98), layer)
        for s in (-0.4, 0.0, 0.4):
            add_block(model, fr, s - 0.012, s + 0.012,
                      side * (P_IN + 0.08) - 0.012,
                      side * (P_IN + 0.08) + 0.012, P_Z, 0.37, DARK, layer)
    else:
        s0, s1 = P_IN + 0.12, P_OUT
        add_block(model, house, s0, s1, -0.32, 0.32, 0.0, 2 * STOREY + 0.04,
                  OFFICE.wall, layer, side_shader=speckle_shader(OFFICE.wall))
        add_block(model, house, s0 - 0.02, s1 + 0.02, -0.34, 0.34,
                  2 * STOREY + 0.04, 2 * STOREY + 0.08, OFFICE.roof, layer)
        facade(model, house, (s0, 0.32), (s0, -0.32), (1, 0), OFFICE,
               storeys=2, bays=4, door=True)


# --- Freight ------------------------------------------------------------------

def forklift(model, fr, s, p, layer):
    add_block(model, fr, s - 0.05, s + 0.05, p - 0.035, p + 0.035, P_Z + 0.01,
              P_Z + 0.07, YELLOW, layer)
    add_block(model, fr, s - 0.03, s + 0.03, p - 0.03, p + 0.03, P_Z + 0.07,
              P_Z + 0.14, DARK, layer)
    for dp in (-0.025, 0.025):
        add_block(model, fr, s + 0.05, s + 0.1, p + dp - 0.006,
                  p + dp + 0.006, P_Z + 0.01, P_Z + 0.02, DARK, layer)
    add_block(model, fr, s + 0.05, s + 0.06, p - 0.03, p + 0.03, P_Z,
              P_Z + 0.16, DARK, layer)


def container(model, fr, s, p, z, colour, layer, length=0.36):
    add_block(model, fr, s - length / 2, s + length / 2, p - 0.055, p + 0.055,
              z, z + 0.11, colour, layer,
              side_color=tuple(int(c * 0.82) for c in colour))
    for ds in np.linspace(-length / 2 + 0.03, length / 2 - 0.03, 6):
        add_block(model, fr, s + ds - 0.004, s + ds + 0.004, p - 0.056,
                  p + 0.056, z + 0.005, z + 0.105,
                  tuple(int(c * 0.9) for c in colour), layer)


def coal_loader(model, fr, side, layer):
    """A bunker on legs over the far platform with a chute over the
    track, a heap beside it."""
    p = side * (P_OUT - 0.14)
    for ds in (-0.12, 0.12):
        for dp in (-0.08, 0.08):
            add_block(model, fr, ds - 0.012, ds + 0.012, p + dp - 0.012,
                      p + dp + 0.012, P_Z, 0.36, DARK, layer)
    add_block(model, fr, -0.16, 0.16, p - 0.12, p + 0.12, 0.36, 0.56,
              (96, 92, 88), layer, side_shader=speckle_shader((96, 92, 88)))
    add_frustum(model, fr, 0.0, p, 0.13, 0.05, 0.28, 0.36, (96, 92, 88),
                layer, n=4)
    add_beam(model, fr.world(0.0, p, 0.34), fr.world(0.0, side * 0.08, 0.26),
             0.05, (80, 78, 76), layer="front")
    for r, z0, z1 in ((0.14, 0.0, 0.06), (0.09, 0.05, 0.1)):
        add_frustum(model, fr, -0.5, side * (P_IN + 0.18), r, r * 0.7,
                    P_Z + z0, P_Z + z1, COAL, layer, n=10,
                    side_shader=speckle_shader(COAL))
    # Water tower: four legs under a round tank.
    wp = side * (P_OUT - 0.12)
    for ds in (-0.06, 0.06):
        for dp in (-0.06, 0.06):
            add_beam(model, fr.world(0.5 + ds, wp + dp, P_Z),
                     fr.world(0.5 + ds * 0.7, wp + dp * 0.7, 0.4), 0.02,
                     DARK, layer=layer)
    add_frustum(model, fr, 0.5, side * (P_OUT - 0.12), 0.11, 0.11, 0.4,
                0.55, (120, 116, 110), layer, n=10)


# --- Scene --------------------------------------------------------------------

def crates(model, fr, s, p, n=3, size=0.07, colour=(150, 104, 58),
           layer="back"):
    for k in range(n):
        add_block(model, fr, s - size, s + size, p - size + k * 0.02,
                  p + size + k * 0.02, P_Z + k * size * 1.6,
                  P_Z + (k + 1) * size * 1.6, colour, layer,
                  side_color=tuple(int(c * 0.82) for c in colour))


def build(st: RailStopParams, layout: int) -> Model:
    ends = layout & 3
    fr = edge_frame(AXES[layout // 4])
    model = Model()
    front = fr.front_sign()
    far = -front if front else -1
    for side in (+1, -1):
        layer = "front" if side == front else "back"
        platform(model, fr, side, layer, ends)
        if st.benches and not st.house:
            for s in (-0.3, 0.3):
                bench(model, fr, side, layer, s, P_IN + 0.2)
        if not st.hall and not st.coal:
            lamp(model, fr, 0.55 if side == far else -0.55,
                 side * (P_OUT - 0.08), layer)
    near_layer = "front" if front else "back"
    if st.hall in ("glass", "mesh"):
        arch_hall(model, fr, IRON if st.hall == "glass" else WHITE,
                  GLASS if st.hall == "glass" else (210, 220, 226),
                  roof_tone=(124, 96, 70) if st.hall == "glass" else None,
                  rise=0.3 if st.hall == "glass" else 0.22)
    elif st.hall == "shed":
        shed(model, fr)
    if st.house:
        station_house(model, fr, far, "back", st.house)
        if st.house == "village":
            for s in (-0.25, 0.25):
                bench(model, fr, -far, near_layer, s, P_IN + 0.2)
    if st.freight:
        forklift(model, fr, 0.2, far * (P_IN + 0.18), "back")
        crates(model, fr, -0.35, far * (P_IN + 0.22))
        crates(model, fr, 0.45, far * (P_IN + 0.24), n=2)
    if st.coal:
        coal_loader(model, fr, far, "back")
    for k in range(st.containers):
        z = P_Z + k * 0.11
        for side, layer in ((far, "back"), (-far, near_layer)):
            for i, s in enumerate((-0.25, 0.2)):
                colour = CONTAINERS[(i * 3 + k * 2 + (side > 0)) %
                                    len(CONTAINERS)]
                container(model, fr, s, side * (P_IN + 0.17), z, colour,
                          layer)
    return model


def render_layer(st, layout, layer):
    return render(build(st, layout), HexCamera(), layer_filter=layer)


def bake_pakset() -> None:
    for st in STOPS:
        entries = [(f"{layer}[{layout}]",
                    lambda s=st, lo=layout, la=layer: render_layer(s, lo, la))
                   for layout in range(LAYOUTS) for layer in ("back", "front")]
        bake_atlas(out_png=STATIONS_DIR / f"{st.name}_hex.png",
                   entries=entries, cols_per_row=8)
        dat = STATIONS_DIR / f"{st.name}.dat"
        rewrite_dat(dat, st.name)
        set_layouts(dat, LAYOUTS)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path,
                    help="write each stop on the legs of a junction, one "
                         "file per stop, instead of baking")
    a = ap.parse_args()
    if a.preview:
        layout = {"N": 3, "S": 3, "NW": 7, "SE": 7, "NE": 11, "SW": 11}
        for st in STOPS:
            junction_preview(
                [lambda f, s=st: {la: render_layer(s, layout[f], la)
                                  for la in ("back", "front")}],
                a.preview.with_stem(f"{a.preview.stem}_{st.name}"), RAIL_060)
    else:
        bake_pakset()
