#!/usr/bin/env python3
# kepubverto for calibre — a placeholder icon
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Write `plugin.png`: a **placeholder** until the family icon is designed.

    python3 kepubverto/make_icon.py

A rounded tile in the family's yellow with its ink outline, and an ink arrow
for "convert". The real icon (the family's tick monogram in a container that
names kepubverto, drawn by epubveri-plugins' `icon.py` method) comes once the
plugin works as it should (Baris, 2026-10-24).

stdlib only, and deterministic: the same script writes the same bytes, so a
test can hold the shipped file to it.
"""

import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 128
SAMPLES = 4

INK = (0x11, 0x11, 0x11)
YELLOW = (0xf5, 0xc5, 0x18)

# Geometry on a 64 grid.
TILE = (4.0, 4.0, 60.0, 60.0)
RADIUS = 10.0
OUTLINE = 2.6


def _in_round_rect(x, y, box, r):
    x0, y0, x1, y1 = box
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _in_arrow(x, y):
    # Shaft, then a head pointing right.
    if 14.0 <= x <= 36.0 and 27.0 <= y <= 37.0:
        return True
    if 34.0 <= x <= 52.0:
        half = (52.0 - x) * (14.0 / 18.0)
        return abs(y - 32.0) <= half
    return False


def colour_at(x, y):
    """The colour at one point on the 64 grid, or None outside the mark."""
    if _in_arrow(x, y):
        return INK
    inner = (TILE[0] + OUTLINE, TILE[1] + OUTLINE,
             TILE[2] - OUTLINE, TILE[3] - OUTLINE)
    if _in_round_rect(x, y, inner, RADIUS - OUTLINE):
        return YELLOW
    if _in_round_rect(x, y, TILE, RADIUS):
        return INK
    return None


def pixels():
    scale = 64.0 / SIZE
    rows = []
    for py in range(SIZE):
        row = bytearray()
        for px in range(SIZE):
            r = g = b = a = 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x = (px + (sx + 0.5) / SAMPLES) * scale
                    y = (py + (sy + 0.5) / SAMPLES) * scale
                    c = colour_at(x, y)
                    if c is not None:
                        r += c[0]
                        g += c[1]
                        b += c[2]
                        a += 1
            n = SAMPLES * SAMPLES
            if a:
                # Straight alpha: the colour is the average of what covered.
                row += bytes((r // a, g // a, b // a, 255 * a // n))
            else:
                row += b'\0\0\0\0'
        rows.append(bytes(row))
    return rows


def png(rows):
    def chunk(kind, data):
        body = kind + data
        return (struct.pack('>I', len(data)) + body
                + struct.pack('>I', zlib.crc32(body) & 0xffffffff))
    raw = b''.join(b'\0' + row for row in rows)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', SIZE, SIZE, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9))
            + chunk(b'IEND', b''))


def main():
    path = os.path.join(HERE, 'plugin.png')
    with open(path, 'wb') as handle:
        handle.write(png(pixels()))
    return path


if __name__ == '__main__':
    print(main())
