"""See baked assets in the running game, in one command.

Builds the pakset, lays out the asked placements on an empty flat map
through a throwaway scenario, starts the engine on a virtual display,
jumps to them and saves a screenshot:

    python3 -m tools.ingame_check --place through track Depot_train_1936 \\
        --place building - Saegewerk --any-year

`--place KIND WAY BUILDING` (repeatable) puts one group per call in a
row, W to E:

- `terminal`: six dead ends round a junction, the building on each,
  so every hex side is faced once.
- `through`: three straight ways, one per hex axis, the building on
  the middle tile of each (stops on the middle three).
- `island`: as `through`, with a second way beside each and stops on
  its middle three too, so one-sided platforms meet between the two.
- `dock`: a harbour on each of the four faces a dock is built on
  (S, SE, N, NW), each on a shore slope with a pond in front;
  WAY is ignored (`-`).
- `building`: one copy per layout, W to E; WAY is ignored (`-`).
  Factories are built with the factory tool, station extensions with
  the station tool next to a bus stop on a short road S of them,
  anything else with the house tool, which wants a city on the map:
  one is founded in a corner, away from the screenshots.

WAY is a way's .dat name or one of `WAYS` (the first flat way of that
type the timeline offers).  Depots are built with the depot tool,
stops with the station tool.

`--any-year` rebuilds the pak of each placed object's directory with
the `intro_*` / `retire_*` lines of its .dat dropped, so an object
outside the map's starting year can be placed; `--any-year DAT...`
does that for the given .dat files instead.
The engine checkout and its build are taken from `--engine`
(default: `../hextrans` next to this repo).
Needs Xvfb, xdotool and ImageMagick's `import`.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
PAKDIR = REPO / "simutrans" / "pak128"
CACHE = REPO / "build-ingame"
SCENARIO = "ingame_check"
DISPLAY = ":99"
SCREEN = (1280, 800)
STEP = 6                # tiles between groups
# Width in tiles of a group of each kind but `building`, which is as wide
# as its copies.
KINDS = {"terminal": STEP, "through": STEP, "island": STEP, "dock": 2 * STEP}

WAYS = {
    "road": "way_desc_x.get_available_ways(wt_road, st_flat)[0]",
    "track": "way_desc_x.get_available_ways(wt_rail, st_flat)[0]",
    "tram": "way_desc_x.get_available_ways(wt_rail, st_tram)[0]",
    "monorail": "way_desc_x.get_available_ways(wt_monorail, st_flat)[0]",
    "maglev": "way_desc_x.get_available_ways(wt_maglev, st_flat)[0]",
    "narrowgauge": "way_desc_x.get_available_ways(wt_narrowgauge, st_flat)[0]",
    "air": "way_desc_x.get_available_ways(wt_air, st_flat)[0]",
    "water": "way_desc_x.get_available_ways(wt_water, st_flat)[0]",
}

SCENARIO_NUT = r'''// Written by tools/ingame_check.py.
map.file = "flat.sve"
scenario.short_description = "ingame_check"
scenario.author = "tools/ingame_check.py"
scenario.version = "1"

function get_rule_text(pl) { return "" }
function get_goal_text(pl) { return "" }
function get_info_text(pl) { return "" }
function get_result_text(pl) { return "" }
function is_tool_allowed(pl, tool_id, wt, name) { return true }
function is_scenario_completed(pl) { return 0 }

function report(what, e)
{
	if (e != null) print("ingame_check: error: " + what + ": " + e)
}

function clear(pl, c, r)
{
	for (local dx = -r; dx <= r; dx++) for (local dy = -r; dy <= r; dy++) {
		local t = square_x(c.x + dx, c.y + dy).get_ground_tile()
		for (local k = 0; k < 8 && t.find_object(mo_tree) != null; k++) {
			t.remove_object(pl, mo_tree)
		}
	}
}

function place(pl, at, desc)
{
	if (desc.get_type() == building_desc_x.depot) {
		report(desc.get_name() + " at " + at, command_x.build_depot(pl, at, desc))
	}
	else {
		report(desc.get_name() + " at " + at, command_x.build_station(pl, at, desc))
	}
}

function terminal(pl, c, way, desc)
{
	for (local i = 0; i < 6; i++) {
		local d = dir.to_coord(1 << i)
		local tip = coord3d(c.x + d.x, c.y + d.y, c.z)
		report("way", command_x.build_way(pl, c, tip, way, true))
		place(pl, tip, desc)
	}
}

function through(pl, c, way, desc)
{
	// the three axes side by side, three tiles apart along y
	foreach (i, d in [dir.south, dir.southeast, dir.southwest]) {
		local v = dir.to_coord(d)
		local m = coord3d(c.x, c.y + 3 * (i - 1), c.z)
		report("way", command_x.build_way(pl, m - v - v, m + v + v, way, true))
		local tiles = desc.get_type() == building_desc_x.depot ? [m] : [m - v, m, m + v]
		foreach (t in tiles) place(pl, t, desc)
	}
}

function island(pl, c, way, desc)
{
	// w is 60 degrees from v: the parallel way's tiles touch the first's,
	// on the side a lone stop's platform takes (left looking from the
	// S, SE or SW end), so the second way's stops mirror it into an island
	foreach (i, d in [[dir.south, dir.southwest], [dir.southeast, dir.south], [dir.southwest, dir.northwest]]) {
		local v = dir.to_coord(d[0])
		local m = coord3d(c.x, c.y + 4 * (i - 1), c.z)
		foreach (o in [m, m + dir.to_coord(d[1])]) {
			report("way", command_x.build_way(pl, o - v - v, o + v + v, way, true))
			foreach (t in [o - v, o, o + v]) place(pl, t, desc)
		}
	}
}

function dock(pl, c, way, desc)
{
	local faces = [[dir.south, slope.south_narrow], [dir.southeast, slope.southeast_narrow],
	               [dir.north, slope.north_narrow], [dir.northwest, slope.northwest_narrow]]
	foreach (i, f in faces) {
		local k = coord3d(c.x + (i % 2) * 6 - 3, c.y + (i / 2) * 6 - 3, c.z)
		local v = dir.to_coord(f[0])
		local m = coord3d(k.x + 2 * v.x, k.y + 2 * v.y, k.z)
		// the pond: the tile two out from the shore and its six neighbours
		local pond = [m]
		for (local j = 0; j < 6; j++) pond.append(m + dir.to_coord(1 << j))
		foreach (t in pond) report("water", command_x(tool_set_climate).work(pl, t, t, "" + cl_water))
		report("slope", command_x.set_slope(pl, k, f[1]))
		place(pl, k, desc)
	}
}

function building(pl, c, layouts, name, factory)
{
	for (local l = 0; l < layouts.len(); l++) {
		local at = coord3d(c.x + layouts[l], c.y, c.z)
		local e = factory ? command_x(tool_build_factory).work(pl, at, "1" + l + "100," + name)
		                  : command_x(tool_build_house).work(pl, at, "1" + l + name)
		report(name + " layout " + l, e)
	}
}

function extension(pl, c, layouts, name)
{
	local stop = building_desc_x.get_available_stations(building_desc_x.station, wt_road, good_desc_x.passenger)[0]
	local road = way_desc_x.get_available_ways(wt_road, st_flat)[0]
	for (local l = 0; l < layouts.len(); l++) {
		local at = coord3d(c.x + layouts[l], c.y, c.z)
		local s = coord3d(at.x, at.y + 1, at.z)
		report("road", command_x.build_way(pl, s, coord3d(s.x + 1, s.y, s.z), road, true))
		report("stop", command_x.build_station(pl, s, stop))
		report(name + " layout " + l, command_x.build_station(pl, at, building_desc_x(name), l))
	}
}
'''


def engine_paths(engine: Path):
    return (engine / "build" / "simutrans" / "simutrans",
            engine / "build" / "src" / "makeobj" / "makeobj",
            engine / "simutrans")


def make_pakset(makeobj: Path) -> None:
    subprocess.run(["make", "-j4", "pakset", f"MAKEOBJ={makeobj}"], cwd=REPO,
                   check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def any_year(dats: list[Path], makeobj: Path) -> None:
    """Rebuild each DAT's directory pak with its timeline lines dropped."""
    for folder in sorted({d.resolve().parent for d in dats}):
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "src"
            shutil.copytree(folder, copy)
            for d in dats:
                if d.resolve().parent == folder:
                    f = copy / d.name
                    f.write_text(re.sub(r"(?im)^\s*(intro|retire)_\w+\s*=.*\n",
                                        "", f.read_text(errors="replace")))
            pak = PAKDIR / (".".join(folder.relative_to(REPO).parts)
                            + ".all.pak")
            subprocess.run([str(makeobj), "quiet", "PAK128", str(pak),
                            "./"], cwd=copy, check=True,
                           stdout=subprocess.DEVNULL)


def flat_map(binary: Path, workdir: Path, size: int) -> Path:
    """An empty flat map, generated once per size and cached."""
    cached = CACHE / f"flat-{size}.sve"
    if cached.exists():
        return cached
    # -flatmap writes the user's pak128 autosave; this replaces it.
    save = Path.home() / "simutrans" / "autosave-pak128.sve"
    save.unlink(missing_ok=True)
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    proc = subprocess.Popen([str(binary), "-objects", "pak128", "-nosound",
                             "-nomidi", "-flatmap", str(size)], cwd=workdir,
                            env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    # It saves, then can hang in the headless teardown.
    for _ in range(600):
        if save.exists() and time.time() - save.stat().st_mtime > 2:
            break
        time.sleep(0.5)
    proc.kill()
    CACHE.mkdir(exist_ok=True)
    shutil.copy(save, cached)
    return cached


OBJ_BLOCK = re.compile(r"(?im)^\s*obj\s*=")


def find_object(name: str):
    """The .dat defining the building or factory `name`:
    `(path, kind, (x, y, layouts))`, kind `building`, `extension` or
    `factory`."""
    for dat in sorted(REPO.rglob("*.dat")):
        if dat.is_relative_to(PAKDIR) or "src" in dat.parts:
            continue
        text = dat.read_text(errors="replace")
        for block in OBJ_BLOCK.split(text):
            if not re.search(rf"(?im)^\s*name\s*=\s*{re.escape(name)}\s*$",
                             block):
                continue
            obj = re.match(r"\s*(\w+)", block).group(1).lower()
            if obj not in ("building", "factory"):
                continue
            if obj == "building" and re.search(
                    r"(?im)^\s*type\s*=\s*extension\s*$", block):
                obj = "extension"
            m = re.search(r"(?im)^\s*dims\s*=\s*(\d+)\s*,\s*(\d+)"
                          r"(?:\s*,\s*(\d+))?", block)
            dims = (int(m.group(1)), int(m.group(2)),
                    int(m.group(3) or 1)) if m else (1, 1, 1)
            return dat, obj, dims
    raise SystemExit(f"no .dat defines {name}")


def plan(places):
    """Each group's kind, way, name, width in tiles and, for `building`,
    `(pitch, layouts, is_factory)`."""
    groups = []
    for kind, way, name in places:
        if kind == "building":
            _, obj, (dx, dy, layouts) = find_object(name)
            pitch = max(dx, dy) + 1
            groups.append((kind, way, name, pitch * layouts,
                           (pitch, layouts, obj)))
        else:
            groups.append((kind, way, name, KINDS[kind], None))
    return groups


def write_scenario(groups, flat: Path, size: int) -> list[tuple[int, int]]:
    """Write the scenario; return the centre tile of each group."""
    y = size // 2
    x = (size - sum(g[3] for g in groups)) // 2
    calls, centres = [], []
    for kind, way, name, width, extra in groups:
        if kind == "building":
            pitch, layouts, obj = extra
            offsets = ", ".join(str(pitch * k) for k in range(layouts))
            centre = (x + width // 2, y)
            calls.append(f"\tclear(pl, coord3d({centre[0]}, {y}, z), "
                         f"{width // 2 + 2})")
            if obj == "extension":
                calls.append(f'\textension(pl, coord3d({x}, {y}, z), '
                             f'[{offsets}], "{name}")')
            else:
                calls.append(f'\tbuilding(pl, coord3d({x}, {y}, z), '
                             f'[{offsets}], "{name}", '
                             f'{str(obj == "factory").lower()})')
        else:
            centre = (x + width // 2, y)
            c = f"coord3d({centre[0]}, {y}, z)"
            way_expr = WAYS.get(way, f'way_desc_x("{way}")')
            calls.append(f"\tclear(pl, {c}, 5)")
            calls.append(f'\t{kind}(pl, {c}, {way_expr}, '
                         f'building_desc_x("{name}"))')
        centres.append(centre)
        x += width
    d = PAKDIR / "scenario" / SCENARIO
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(flat, d / "flat.sve")
    houses = any(g[0] == "building" and g[4][2] == "building"
                 for g in groups)
    city = ['\treport("city", command_x(tool_add_city).work(player_x(1), '
            'coord3d(3, 3, z), ""))'] if houses else []
    start = ["function start()", "{", "\tlocal pl = player_x(0)",
             f"\tlocal z = square_x({centres[0][0]}, {y}).get_ground_tile().z",
             *city, *calls, '\tprint("ingame_check: done")', "}"]
    (d / "scenario.nut").write_text(SCENARIO_NUT + "\n".join(start) + "\n")
    return centres


def xdo(*args):
    subprocess.run(["xdotool", *args], env=dict(os.environ, DISPLAY=DISPLAY),
                   check=True)


def screenshot(jump, out: Path, crop: int, scale: int) -> None:
    """Centre the view on tile `jump` through the jump dialog and save
    the screen round it."""
    xdo("key", "shift+j")
    time.sleep(0.8)
    xdo("key", "ctrl+a")
    xdo("type", f"{jump[0]},{jump[1]}")
    xdo("key", "Return")
    time.sleep(0.5)
    xdo("key", "Escape")
    # the tile under the mouse is highlighted: park it outside the crop
    xdo("mousemove", "4", str(SCREEN[1] - 40))
    xdo("mousemove_relative", "--", "2", "2")
    time.sleep(1.5)
    shot = out.with_suffix(".full.png")
    subprocess.run(["import", "-window", "root", str(shot)],
                   env=dict(os.environ, DISPLAY=DISPLAY), check=True)
    im = Image.open(shot)
    if crop:
        cx, cy = SCREEN[0] // 2, SCREEN[1] // 2
        w, h = crop, crop * 5 // 8
        im = im.crop((cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2))
    im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
    im.save(out)
    shot.unlink()


def run_game(binary: Path, workdir: Path, jumps, outs, log: Path,
             crop: int, scale: int) -> list[str]:
    if subprocess.run(["pgrep", "Xvfb"], stdout=subprocess.DEVNULL).returncode:
        subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0",
                          f"{SCREEN[0]}x{SCREEN[1]}x24"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    subprocess.run(["pkill", "-x", "simutrans"])
    env = dict(os.environ, DISPLAY=DISPLAY, SDL_AUDIODRIVER="dummy")
    with log.open("w") as f:
        proc = subprocess.Popen(
            [str(binary), "-objects", "pak128", "-nosound", "-nomidi",
             "-screensize", f"{SCREEN[0]}x{SCREEN[1]}", "-scenario", SCENARIO,
             "-debug", "2"], cwd=workdir, env=env, stdout=f,
            stderr=subprocess.STDOUT)
    try:
        for _ in range(240):
            text = log.read_text(errors="replace")
            if "ingame_check: done" in text or proc.poll() is not None:
                break
            time.sleep(0.5)
        else:
            raise SystemExit(f"timed out; see {log}")
        if proc.poll() is not None:
            raise SystemExit(f"the game quit; see {log}")
        time.sleep(2)
        xdo("mousemove", str(SCREEN[0] // 2), str(SCREEN[1] // 2), "click", "1")
        for _ in range(3):
            xdo("key", "Escape")
            time.sleep(0.2)
        for jump, out in zip(jumps, outs):
            screenshot(jump, out, crop, scale)
    finally:
        proc.kill()
    return re.findall(r"ingame_check: error: .*", log.read_text(errors="replace"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--place", nargs=3, action="append", required=True,
                    metavar=("KIND", "WAY", "BUILDING"))
    ap.add_argument("--any-year", nargs="*", type=Path, metavar="DAT")
    ap.add_argument("--out", type=Path, default=CACHE / "shot.png",
                    help="screenshot of the first group; the others get "
                         "-1, -2, ... before the suffix")
    ap.add_argument("--crop", type=int, default=800,
                    help="width in screen pixels round the group; "
                         "0 keeps the whole screen")
    ap.add_argument("--scale", type=int, default=1)
    ap.add_argument("--no-make", action="store_true",
                    help="use the pakset as last built")
    ap.add_argument("--engine", type=Path, default=REPO.parent / "hextrans")
    a = ap.parse_args()
    for kind, _, _ in a.place:
        if kind not in KINDS and kind != "building":
            ap.error(f"unknown KIND {kind}")

    binary, makeobj, workdir = engine_paths(a.engine)
    if not a.no_make:
        make_pakset(makeobj)
    if a.any_year is not None:
        any_year(a.any_year or [find_object(n)[0] for _, _, n in a.place],
                 makeobj)
    groups = plan(a.place)
    size = max(32, sum(g[3] for g in groups) + 24)
    jumps = write_scenario(groups, flat_map(binary, workdir, size), size)
    CACHE.mkdir(exist_ok=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    outs = [a.out if i == 0 else a.out.with_stem(f"{a.out.stem}-{i}")
            for i in range(len(jumps))]
    errors = run_game(binary, workdir, jumps, outs, CACHE / "game.log",
                      a.crop, a.scale)
    for out in outs:
        print(f"wrote {out}")
    for e in errors:
        print(e)
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
