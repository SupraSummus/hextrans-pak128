#!/usr/bin/env python3
"""Score a candidate render against a reference tile.

Phase 1 (shape-only) metrics:
- alpha_iou:    intersection-over-union of the alpha masks (1 = perfect shape)
- lum_rmse:     RMSE of luminance over the alpha intersection (0..255)
- alpha_xor:    fraction of pixels where exactly one image is opaque

Combined `score` is a single number (lower = better) suitable for an
optimization loop. It blends shape and shading; tweak the weights as needed.

Both inputs must be the same size and RGBA. Use --debug to write a 4-panel
visualization (ref | candidate | luminance diff | alpha xor).
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def load_rgba(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8)


def luminance(rgba: np.ndarray) -> np.ndarray:
    r, g, b = rgba[..., 0], rgba[..., 1], rgba[..., 2]
    return (0.2126 * r + 0.7152 * g + 0.0722 * b).astype(np.float32)


def score(ref: np.ndarray, cand: np.ndarray) -> dict:
    if ref.shape != cand.shape:
        raise SystemExit(f"shape mismatch: ref {ref.shape} vs cand {cand.shape}")

    ra = ref[..., 3] > 0
    ca = cand[..., 3] > 0
    union = np.logical_or(ra, ca)
    inter = np.logical_and(ra, ca)
    xor = np.logical_xor(ra, ca)

    alpha_iou = float(inter.sum() / union.sum()) if union.any() else 1.0
    alpha_xor = float(xor.sum() / ra.size)

    if inter.any():
        diff = luminance(ref)[inter] - luminance(cand)[inter]
        lum_rmse = float(np.sqrt(np.mean(diff * diff)))
    else:
        lum_rmse = 0.0

    # Combined score: heavy on shape (1 - IoU dominates when shape is wrong),
    # plus normalized luminance error.
    combined = (1.0 - alpha_iou) + lum_rmse / 255.0

    return {
        "alpha_iou": alpha_iou,
        "alpha_xor": alpha_xor,
        "lum_rmse": lum_rmse,
        "score": combined,
    }


def make_debug(ref: np.ndarray, cand: np.ndarray, out: Path) -> None:
    h, w, _ = ref.shape
    panel = np.full((h, w * 4 + 12, 4), 255, dtype=np.uint8)

    def paste(img, idx):
        x0 = idx * (w + 4)
        panel[:, x0 : x0 + w] = img

    paste(ref, 0)
    paste(cand, 1)

    lum_d = np.zeros_like(ref)
    inter = (ref[..., 3] > 0) & (cand[..., 3] > 0)
    if inter.any():
        d = np.abs(luminance(ref) - luminance(cand)).astype(np.uint8)
        lum_d[..., 0] = lum_d[..., 1] = lum_d[..., 2] = d
        lum_d[..., 3] = 255 * inter
    paste(lum_d, 2)

    xor_img = np.zeros_like(ref)
    only_ref = (ref[..., 3] > 0) & ~(cand[..., 3] > 0)
    only_cand = (cand[..., 3] > 0) & ~(ref[..., 3] > 0)
    xor_img[only_ref] = (255, 0, 0, 255)   # red: missing in candidate
    xor_img[only_cand] = (0, 0, 255, 255)  # blue: extra in candidate
    paste(xor_img, 3)

    Image.fromarray(panel, mode="RGBA").save(out)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("reference", type=Path)
    p.add_argument("candidate", type=Path)
    p.add_argument("--debug", type=Path, help="Write side-by-side debug PNG")
    args = p.parse_args()

    ref = load_rgba(args.reference)
    cand = load_rgba(args.candidate)
    metrics = score(ref, cand)
    json.dump(metrics, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if args.debug:
        make_debug(ref, cand, args.debug)


if __name__ == "__main__":
    main()
