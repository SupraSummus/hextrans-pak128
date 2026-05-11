"""Lightmap encoding shared across hex pakset bakers.

A pakset *lightmap* is an RGBA cell whose RGB carries a uniform grey
Lambert ramp (`(g, g, g)`) and whose alpha is the covered-pixel mask.
The engine reads it via `descriptor/ground_desc.cc::create_textured_tile`,
which walks the RLE and per-pixel multiplies each 5-bit grey channel
into the matching climate-texture 5-bit channel divided by 16:

    rc = (red5(grey) * red5(texture)) / 16

So `grey5 == 16` is the identity multiplier (~1.0×), `grey5 == 0`
black-outs the pixel, `grey5 == 31` is the brightest peak.

This module owns the encoding: `lambert_grey_rgb(nx, ny, nz)` is the
canonical per-region/per-face Lambert helper that ground bakers
(texture_lightmap) and bespoke-geometry bakers (way_wall) both feed
their face normals through.  Keeping it here means
`brightness_to_grey_rgb`'s rounding convention and the reserved-palette
dodge live in one place.
"""
from __future__ import annotations

from .hex_synth import lambert_brightness


# Engine reserved palette (engine `descriptor/image.cc::rgbtab`).  Any
# opaque pixel whose RGB888 matches one of these is encoded by makeobj
# (`descriptor/writer/image_writer.cc::pixrgb_to_pixval`) as a
# special-color PIXVAL `0x8000+i` instead of a normal RGB555.  The
# runtime `create_textured_tile` then mis-reads the `0x80…` bits as
# RGB555 channels, producing a bogus tint that scales with the climate
# texture.  The lightmap's uniform-grey Lambert ramp lands exactly on
# `0x6B6B6B` (= 107) at one brightness level, hence the dodge below.
RGBTAB_RESERVED = frozenset({
    0x244B67, 0x395E7C, 0x4C7191, 0x6084A7,
    0x7497BD, 0x88ABD3, 0x9CBEE9, 0xB0D2FF,
    0x7B5803, 0x8E6F04, 0xA18605, 0xB49D07,
    0xC6B408, 0xD9CB0A, 0xECE20B, 0xFFF90D,
    0x57656F, 0x7F9BF1, 0xFFFF53, 0xFF211D,
    0x01DD01, 0x6B6B6B, 0x9B9B9B, 0xB3B3B3,
    0xC9C9C9, 0xDFDFDF, 0xE3E3FF, 0xC1B1D1,
    0x4D4D4D, 0xFF017F, 0x0101FF,
})


def safe_face_rgb(gray8: int) -> tuple[int, int, int]:
    """Uniform-grey `(g, g, g)` unless that triple is one of the engine's
    reserved palette entries, in which case nudge blue by ±1.

    The pakset side has to dodge the reserved palette because makeobj
    encodes any matching opaque pixel as a special-color PIXVAL —
    perceptually identical 5-bit grey, catastrophic at multiply time.
    Nudging by 1 RGB8 unit shifts under the same RGB555 quantisation
    bucket as the original on every collision (the reserved greys are
    spaced by ≥ 16 RGB8 units), so `create_textured_tile` produces
    bit-identical output on the non-collision path.
    """
    triple = (gray8 << 16) | (gray8 << 8) | gray8
    if triple not in RGBTAB_RESERVED:
        return (gray8, gray8, gray8)
    nudged = gray8 - 1 if gray8 > 0 else gray8 + 1
    return (gray8, gray8, nudged)


def brightness_to_grey_rgb(brightness: int) -> tuple[int, int, int]:
    """Encode a `hex_synth.lambert_brightness` value (~128..352) as a
    Lambert grey RGB triple under `create_textured_tile`'s multiplier
    convention: `gray5 = brightness/16` (clamped 0..31), RGB8 expanded
    with `(gray5*255 + 15) / 31` rounding.  Brightness 256 (1.0×) lands
    at 5-bit value 16, RGB8 ~132 — the pak128 identity-multiplier point
    so a flat-up face returns the biome texture unchanged.

    The reserved-palette dodge from `safe_face_rgb` is folded in so the
    caller can stamp the triple directly into the cell without a second
    pass.
    """
    gray5 = max(0, min(brightness // 16, 31))
    gray8 = (gray5 * 255 + 15) // 31
    return safe_face_rgb(gray8)


def lambert_grey_rgb(nx: float, ny: float, nz: float) -> tuple[int, int, int]:
    """One-shot helper: Lambert brightness from an `(nx, ny, nz)` normal
    (using `hex_synth.LIGHT`), encoded as a grey RGB triple ready to
    rasterise.  The normal need not be unit-length —
    `lambert_brightness` normalises internally.
    """
    return brightness_to_grey_rgb(lambert_brightness(nx, ny, nz))
