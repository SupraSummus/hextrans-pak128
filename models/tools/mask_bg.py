#!/usr/bin/env python3
"""Mask a single solid background color out of a PNG, producing RGBA output.

Used to convert OpenSCAD's solid-color preview backgrounds (e.g. Sunset's
(170, 68, 68)) into a proper alpha channel for diff-tool consumption.
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument(
        "--bg", default="170,68,68",
        help="Background RGB to make transparent (default 170,68,68)",
    )
    p.add_argument(
        "--tolerance", type=int, default=2,
        help="Max per-channel deviation to still count as bg (default 2)",
    )
    args = p.parse_args()

    bg = tuple(int(c) for c in args.bg.split(","))
    if len(bg) != 3:
        raise SystemExit("--bg must be R,G,B")

    arr = np.asarray(Image.open(args.input).convert("RGB"), dtype=np.int16)
    diff = np.abs(arr - np.array(bg, dtype=np.int16))
    mask = np.all(diff <= args.tolerance, axis=-1)

    out = np.zeros((*arr.shape[:2], 4), dtype=np.uint8)
    out[..., :3] = arr.astype(np.uint8)
    out[..., 3] = np.where(mask, 0, 255)
    Image.fromarray(out, mode="RGBA").save(args.output)


if __name__ == "__main__":
    main()
