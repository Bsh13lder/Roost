#!/usr/bin/python3
"""Builds the computer's wallpaper at image build time: a graphite gradient, a faint dot grid and one soft
teal glow (a calm, Linux-like screen with no logos), as a PNG.
Standard library only (zlib and struct), so the image needs no imaging package."""

from __future__ import annotations

import math
import struct
import sys
import zlib

WIDTH, HEIGHT = 1280, 800
TOP_LEFT, BOTTOM_RIGHT = (24, 26, 31), (13, 14, 17)
GLOWS = (  # (centre x, centre y, radius, colour, strength), positions as fractions of the screen
    (0.78, 0.30, 0.70, (44, 92, 90), 0.35),
)
GRID_STEP, DOT_LIFT = 32, 9  # a dot every 32 px, this much lighter than the background


def pixel(x: int, y: int) -> tuple[int, int, int]:
    t = (x / WIDTH + y / HEIGHT) / 2
    colour = [a + (b - a) * t for a, b in zip(TOP_LEFT, BOTTOM_RIGHT)]
    for gx, gy, radius, glow, strength in GLOWS:
        dx, dy = x / WIDTH - gx, (y / HEIGHT - gy) * HEIGHT / WIDTH
        weight = strength * math.exp(-(dx * dx + dy * dy) / (radius * radius * 0.18))
        colour = [c + (g - c) * weight for c, g in zip(colour, glow)]
    if x % GRID_STEP == 0 and y % GRID_STEP == 0:
        colour = [c + DOT_LIFT for c in colour]
    return tuple(max(0, min(255, round(c))) for c in colour)


def png(width: int, height: int) -> bytes:
    rows = b"".join(b"\x00" + bytes(v for x in range(width) for v in pixel(x, y)) for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    with open(sys.argv[1], "wb") as fh:
        fh.write(png(WIDTH, HEIGHT))
