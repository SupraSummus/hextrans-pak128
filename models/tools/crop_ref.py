#!/usr/bin/env python3
"""Crop a single tile from a pak128 sprite sheet and emit RGBA PNG.

Pak128 uses (231, 255, 255) as the transparent placeholder color. This
script masks that color out to alpha=0 in the output.

Tile coordinates can be given directly with --row/--col, or looked up via
the accompanying .dat file with --dat/--image. The .dat references tiles
as `name.row.col` strings inside `Image[N][M]=...` lines.

Examples:
    crop_ref.py landscape/grounds/texture-lightmap.png --row 0 --col 14 -o flat.png
    crop_ref.py landscape/grounds/texture-lightmap.png \\
        --dat landscape/grounds/texture-lightmap.dat --image 0 -o flat.png
"""
import argparse
import re
import sys
from pathlib import Path

from PIL import Image

PAK128_TRANSPARENT = (231, 255, 255)
DEFAULT_TILE_SIZE = 128


def lookup_in_dat(dat_path: Path, image_index: int) -> tuple[int, int]:
    """Return (row, col) for Image[image_index][0] in a Simutrans .dat."""
    pattern = re.compile(
        rf"^\s*Image\[{image_index}\]\[0\]\s*=\s*[\w\-]+\.(\d+)\.(\d+)\b"
    )
    text = dat_path.read_text(errors="replace")
    for line in text.splitlines():
        m = pattern.match(line)
        if m:
            return int(m.group(1)), int(m.group(2))
    raise SystemExit(f"Image[{image_index}][0] not found in {dat_path}")


def crop_tile(sheet: Image.Image, row: int, col: int, ts: int) -> Image.Image:
    box = (col * ts, row * ts, col * ts + ts, row * ts + ts)
    if box[2] > sheet.width or box[3] > sheet.height:
        raise SystemExit(
            f"crop {box} exceeds sheet {sheet.size} (tile size {ts})"
        )
    return sheet.crop(box).convert("RGBA")


def mask_transparent(im: Image.Image, key: tuple[int, int, int]) -> Image.Image:
    px = im.load()
    w, h = im.size
    kr, kg, kb = key
    for y in range(h):
        for x in range(w):
            r, g, b, _ = px[x, y]
            if r == kr and g == kg and b == kb:
                px[x, y] = (0, 0, 0, 0)
    return im


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("sheet", type=Path, help="Path to sprite-sheet PNG")
    p.add_argument("--row", type=int, help="Tile row (0-based)")
    p.add_argument("--col", type=int, help="Tile column (0-based)")
    p.add_argument("--dat", type=Path, help="Companion .dat file for lookup")
    p.add_argument("--image", type=int, help="Image[N][0] index in the .dat")
    p.add_argument(
        "--tile-size", type=int, default=DEFAULT_TILE_SIZE,
        help=f"Tile size in px (default {DEFAULT_TILE_SIZE})",
    )
    p.add_argument("-o", "--output", type=Path, required=True)
    args = p.parse_args()

    if args.dat is not None and args.image is not None:
        row, col = lookup_in_dat(args.dat, args.image)
    elif args.row is not None and args.col is not None:
        row, col = args.row, args.col
    else:
        p.error("provide either --row/--col or --dat/--image")

    sheet = Image.open(args.sheet).convert("RGB")
    tile = crop_tile(sheet, row, col, args.tile_size)
    tile = mask_transparent(tile, PAK128_TRANSPARENT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tile.save(args.output)
    print(f"wrote {args.output} (row={row} col={col})", file=sys.stderr)


if __name__ == "__main__":
    main()
