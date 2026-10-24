#!/usr/bin/env python3
# kepubverto for calibre — the plugin icon
# Copyright (C) 2026 Baris Kayadelen
# SPDX-License-Identifier: GPL-3.0-only
# See the LICENSE file at the root of this repository.
"""Write `plugin.png`: a **k** on calibre's book, in the family's yellow.

    python3 kepubverto/make_icon.py

**The book is the library plugin's**, from epubveri-plugins' `icon.py`
(`BOOK_*`, measured off calibre's own `add_book.png`): a flat yellow cover, a
white page block behind it on the right, a short rule near the top, and a
dark glyph in the middle, which is how calibre's toolbar draws its own books.
The plugin lives only in calibre, so the book carries no ink outline, as in
the library plugin.

**The glyph is a k, not the family's tick** (Baris, 2026-10-24). Three
variants were rendered at 16, 24, 32 and 128 px on light, mid and dark grounds:
a k inside two half-circle arrows, the arrows alone, and the k alone. At 16
and 24 px the arrows lost their heads and read as an O around a blurred
letter, and the k alone was the only one still legible. It also sets this
icon apart from the library plugin's tick on the same book.

**The k is KF Libron Bold's**, by Nico Verbruggen, from
https://github.com/nicoverbruggen/libron (SIL Open Font License 1.1; the
font's own copyright: "Libron (c) 2026 Nico Verbruggen, with Reserved Font
Name Libron", a revision of Readerly and Newsreader). KF Libron is the build
made for Kobo devices. The OFL covers the font, not artwork made with it, and
no font is shipped or derived here: only the outline of one glyph, read from
`KF_Libron-Bold.ttf` (sha256 97f24ada…3f485), is kept below as data, so the
icon builds without the font.

stdlib only and deterministic: the same script writes the same bytes, and a
test holds the shipped file to it.
"""

import math
import os
import struct
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 128
SAMPLES = 6
GRID = 64.0

PAGE = (0xf5, 0xc5, 0x18)          #: the cover, the family's yellow
BOOK_DARK = (0x4a, 0x35, 0x03)     #: the rule and the glyph, calibre-style
BOOK_PAPER = (0xff, 0xff, 0xff)    #: the pages behind the cover

# epubveri-plugins' `icon.py`, unchanged, on its 64 grid.
BOOK_COVER = (8.5, 6.8, 50.0, 63.0)
BOOK_PAGES = (10.6, 4.5, 52.4, 58.4)
BOOK_PAGE_OUTLINE = 2.1
BOOK_RULE = (17.0, 13.4, 41.5, 16.4)
BOOK_RADIUS = 1.2

#: Where the k sits and how tall it is, in grid units. Centred across the
#: cover's open area below the rule; 30 units tall, so its thinnest strokes
#: stay above about 1 px at 16 px.
K_CENTRE = (29.25, 41.0)
K_HEIGHT = 30.0

#: KF Libron Bold, glyph "k": one TrueType contour in font units (2000 per
#: em, y up), as `(x, y, on_curve)`. Off-curve points are quadratic controls.
K_BBOX = (3, 0, 1355, 1591)
K_POINTS = [
    (504, 141, 1), (634, 98, 1), (634, 0, 1), (51, 0, 1), (51, 98, 1),
    (187, 141, 1), (187, 1283, 1), (175, 1294, 0), (117, 1331, 0),
    (41, 1374, 0), (3, 1395, 1), (3, 1493, 1), (455, 1591, 1),
    (524, 1591, 1), (504, 1328, 1), (504, 684, 1), (657, 684, 1),
    (911, 940, 1), (769, 977, 1), (769, 1071, 1), (1280, 1071, 1),
    (1280, 977, 1), (1132, 939, 1), (870, 695, 1), (1241, 147, 1),
    (1355, 91, 1), (1355, 0, 1), (984, 0, 1), (639, 500, 1), (504, 500, 1),
]


def _flatten(points, steps=8):
    """The contour as a polygon: quadratic segments cut into `steps` lines,
    with the on-curve point TrueType implies between two off-curve ones."""
    full = []
    n = len(points)
    for i in range(n):
        p, q = points[i], points[(i + 1) % n]
        full.append(p)
        if not p[2] and not q[2]:
            full.append(((p[0] + q[0]) / 2.0, (p[1] + q[1]) / 2.0, 1))
    while not full[0][2]:
        full = full[1:] + full[:1]
    out = []
    n = len(full)
    i = 0
    while i < n:
        p, q = full[i], full[(i + 1) % n]
        if q[2]:
            out.append((p[0], p[1]))
            i += 1
            continue
        r = full[(i + 2) % n]
        for s in range(steps):
            t = s / float(steps)
            out.append(((1 - t) ** 2 * p[0] + 2 * (1 - t) * t * q[0] + t * t * r[0],
                        (1 - t) ** 2 * p[1] + 2 * (1 - t) * t * q[1] + t * t * r[1]))
        i += 2
    return out


def _k_polygon():
    """The k on the 64 grid (y down), centred on `K_CENTRE`."""
    x0, y0, x1, y1 = K_BBOX
    scale = K_HEIGHT / (y1 - y0)
    cx, cy = K_CENTRE
    return [(cx + (x - (x0 + x1) / 2.0) * scale,
             cy - (y - (y0 + y1) / 2.0) * scale)
            for x, y in _flatten(K_POINTS)]


K_POLYGON = _k_polygon()


def _in_k(x, y):
    """Non-zero winding, as TrueType fills."""
    winding = 0
    n = len(K_POLYGON)
    for i in range(n):
        ax, ay = K_POLYGON[i]
        bx, by = K_POLYGON[(i + 1) % n]
        if ay <= y < by or by <= y < ay:
            if ax + (y - ay) * (bx - ax) / (by - ay) > x:
                winding += 1 if by > ay else -1
    return winding != 0


def _rrect(box, radius, grow=0.0):
    x0, y0, x1, y1 = box
    X0, Y0, X1, Y1 = x0 - grow, y0 - grow, x1 + grow, y1 + grow
    r = max(0.01, radius + grow)

    def at(x, y):
        cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
        hx, hy = (X1 - X0) / 2 - r, (Y1 - Y0) / 2 - r
        qx, qy = abs(x - cx) - hx, abs(y - cy) - hy
        if qx <= 0 or qy <= 0:
            return max(qx, qy) <= r
        return math.hypot(qx, qy) <= r

    return at


_COVER = _rrect(BOOK_COVER, BOOK_RADIUS)
_PAGES = _rrect(BOOK_PAGES, BOOK_RADIUS)
_EDGE = _rrect(BOOK_PAGES, BOOK_RADIUS, BOOK_PAGE_OUTLINE)
_RULE = _rrect(BOOK_RULE, 1.0)


def colour_at(x, y):
    """The colour at one point on the 64 grid, or None outside the mark."""
    if _COVER(x, y):
        if _RULE(x, y) or _in_k(x, y):
            return BOOK_DARK
        return PAGE
    if _PAGES(x, y):
        return BOOK_PAPER
    if _EDGE(x, y):
        return PAGE
    return None


def pixels(size=SIZE):
    """RGBA rows, straight alpha: the colour is the average of what covered."""
    rows = []
    step = GRID / size
    sub = step / SAMPLES
    total = SAMPLES * SAMPLES
    for py in range(size):
        row = bytearray()
        for px in range(size):
            r = g = b = hits = 0
            for sy in range(SAMPLES):
                y = py * step + (sy + 0.5) * sub
                for sx in range(SAMPLES):
                    c = colour_at(px * step + (sx + 0.5) * sub, y)
                    if c is not None:
                        r += c[0]
                        g += c[1]
                        b += c[2]
                        hits += 1
            if hits:
                row += bytes(((r + hits // 2) // hits, (g + hits // 2) // hits,
                              (b + hits // 2) // hits,
                              (255 * hits + total // 2) // total))
            else:
                row += b'\0\0\0\0'
        rows.append(bytes(row))
    return rows


def png(rows):
    def chunk(kind, data):
        body = kind + data
        return (struct.pack('>I', len(data)) + body
                + struct.pack('>I', zlib.crc32(body) & 0xffffffff))
    size = len(rows)
    raw = b''.join(b'\0' + row for row in rows)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9))
            + chunk(b'IEND', b''))


def main():
    path = os.path.join(HERE, 'plugin.png')
    with open(path, 'wb') as handle:
        handle.write(png(pixels()))
    return path


if __name__ == '__main__':
    print(main())
