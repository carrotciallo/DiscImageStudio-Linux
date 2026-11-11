"""Self-locating texture palette target: the disc is tiled with small patches, each
carrying its own ID and one swatch of every candidate texture.

Any photo that shows even a part of the disc yields, for every readable tile, where it
sits (ring, sector, hence the local track direction) and how every texture looks under
that tile's light and viewing angle. Comparing swatches inside one tile cancels uneven
lighting and stray rainbow.

Tile layout, in tile coordinates (row 0 = inner edge, column 0 = smallest angle, angle
counter-clockwise in the data-side view):

    6 rows x 7 columns of cells. Cells pair up radially (rows 0-1, 2-3, 4-5).
    Columns 0-3, 12 pairs ("slots", slot = 3 * column + pair):
        slot 0      A5 / A5   finder
        slot 1-10   ID bits, differential: 1 = A5 inner / 92 outer, 0 = 92 inner / A5 outer
        slot 11     92 / 92   finder
    Columns 4-6, 9 pairs: one swatch per palette texture, index = 3 * (column - 4) + pair.
    With a shuffle seed, swatches follow randomised Latin squares instead (swatch_slots):
    over every 9 consecutive tiles each texture sits once in each slot, so texture and
    position within the tile are not confounded.

ID bits (MSB first): ring (2 bits), sector (6 bits), parity of all 8, parity of bits 0, 2, 4, 6.
Each bit is read by comparing the two cells of its pair, so it survives the light/dark
flips and colour changes that diffraction causes.
"""

from __future__ import annotations

import json
import math

import numpy as np

from .imagedisc import CELL_MM, HALF_MM, SIZE

RING_EDGES_MM = (25.0, 33.0, 41.0, 49.0, 57.0)
TILE_MM = 8.0
GAP_MM = 0.5
ROWS, COLS, ID_COLS = 6, 7, 4
BACKGROUND = "RND"
DEFAULT_GEOMETRY = {"ring_edges_mm": RING_EDGES_MM, "tile_mm": TILE_MM, "gap_mm": GAP_MM, "rows": ROWS,
                    "cols": COLS, "id_cols": ID_COLS, "scale_mm": None, "shuffle_seed": None}


def geometry(lay: dict | None = None) -> dict:
    """Tile geometry from a layout record (older records lack some keys: defaults fill them)."""
    g = dict(DEFAULT_GEOMETRY)
    g.update({k: lay[k] for k in DEFAULT_GEOMETRY if lay and k in lay})
    return g


def sectors_per_ring(g: dict | None = None) -> list[int]:
    g = geometry(g)
    e = g["ring_edges_mm"]
    return [round(2 * math.pi * (a + b) / 2 / g["tile_mm"]) for a, b in zip(e, e[1:])]


def id_bits(ring: int, sector: int) -> list[int]:
    b = [(ring >> 1) & 1, ring & 1] + [(sector >> k) & 1 for k in range(5, -1, -1)]
    return b + [sum(b) & 1, (b[0] ^ b[2] ^ b[4] ^ b[6])]


def swatch_slots(ring: int, sector: int, n_palette: int, g: dict | None = None) -> np.ndarray:
    """Swatch slot (= (rows / 2) * (column - id_cols) + pair) of each palette texture in one tile."""
    g = geometry(g)
    n_slots = g["rows"] // 2 * (g["cols"] - g["id_cols"])
    n = min(n_palette, n_slots)
    if g["shuffle_seed"] is None:
        return np.arange(n)
    # Latin squares: in every block of n_slots consecutive tiles each texture visits each slot
    # once; rows, symbols and slots are permuted afresh per block so neighbours change too.
    t = sum(sectors_per_ring(g)[:ring]) + sector
    block, row = divmod(t, n_slots)
    rng = np.random.default_rng([int(g["shuffle_seed"]), block])
    pr, pc, ps = rng.permutation(n_slots), rng.permutation(n_slots), rng.permutation(n_slots)
    return ps[(pr[row] + pc[:n]) % n_slots]


def tile_cells(ring: int, sector: int, n_palette: int, g: dict | None = None) -> np.ndarray:
    """rows x cols cell contents: -1 = A5, -2 = 92, k >= 0 = palette swatch k (two radial cells each)."""
    g = geometry(g)
    rows, cols, idc = g["rows"], g["cols"], g["id_cols"]
    cells = np.zeros((rows, cols), np.int64)
    slots = [(1, 1)] + [(1, 0) if b else (0, 1) for b in id_bits(ring, sector)] + [(0, 0)]
    for s, (inner_a5, outer_a5) in enumerate(slots):
        col, pair = divmod(s, 3)
        cells[2 * pair, col] = -1 if inner_a5 else -2
        cells[2 * pair + 1, col] = -1 if outer_a5 else -2
    per_col = rows // 2
    for k, slot in enumerate(swatch_slots(ring, sector, n_palette, g)):
        col, pair = divmod(int(slot), per_col)
        cells[2 * pair:2 * pair + 2, idc + col] = k
    return cells


def design(palette: list[str], **geometry_overrides) -> tuple[np.ndarray, list[str], dict]:
    """Label map (SIZE x SIZE uint8), texture list for the labels, and the layout record."""
    g = geometry(geometry_overrides)
    edges, rows, cols, gap = g["ring_edges_mm"], g["rows"], g["cols"], g["gap_mm"]
    textures = [BACKGROUND, "A5", "92"] + [t for t in palette if t not in ("A5", "92", BACKGROUND)]
    index = {t: i for i, t in enumerate(textures)}
    pal_label = np.array([index[t] for t in palette])
    nsec = sectors_per_ring(g)
    tables = [np.stack([np.where(c == -1, 1, np.where(c == -2, 2, pal_label[np.clip(c, 0, None)]))
                        for c in (tile_cells(k, j, len(palette), g) for j in range(n))])
              for k, n in enumerate(nsec)]
    labels = np.zeros((SIZE, SIZE), np.uint8)
    c = (np.arange(SIZE) + 0.5) * CELL_MM - HALF_MM
    x = c[None, :]
    for y0 in range(0, SIZE, 500):
        y = -c[y0:y0 + 500, None]
        r = np.hypot(x, y)
        th = np.arctan2(y, x) % (2 * math.pi)
        out = np.zeros(r.shape, np.uint8)
        for k, n in enumerate(nsec):
            r_in, r_out = edges[k] + gap / 2, edges[k + 1] - gap / 2
            dth = 2 * math.pi / n
            j = np.floor(th / dth).astype(np.int64) % n
            a = th - j * dth - gap / 2 / np.maximum(r, 1e-6)
            span = dth - gap / np.maximum(r, 1e-6)
            m = (r >= r_in) & (r < r_out) & (a >= 0) & (a < span)
            row = np.clip(((r - r_in) / (r_out - r_in) * rows).astype(np.int64), 0, rows - 1)
            col = np.clip((a / np.where(m, span, 1) * cols).astype(np.int64), 0, cols - 1)
            out[m] = tables[k][j[m], row[m], col[m]]
        if g["scale_mm"]:
            _scale_ticks(out, r, th, g["scale_mm"])
        labels[y0:y0 + 500] = out
    if g["scale_mm"]:
        _scale_numbers(labels, g["scale_mm"])
    layout = {"kind": "tile-palette-target", **{k: (list(v) if isinstance(v, tuple) else v) for k, v in g.items()},
              "sectors_per_ring": nsec, "palette": palette,
              "background": BACKGROUND, "angle": "counter-clockwise from +x in the data-side view, y up",
              "id_bits": "ring(2) sector(6) parity(all) parity(0,2,4,6); 1 = A5 inner / 92 outer",
              "slots": "slot = 3 * column + pair; slot 0 = A5/A5, slot 11 = 92/92, slots 1-10 = ID bits",
              "swatch": ("index = (rows / 2) * (column - id_cols) + pair" if g["shuffle_seed"] is None else
                         "slot = (rows / 2) * (column - id_cols) + pair; texture per slot from swatch_slots() "
                         "(randomised Latin square per block of tiles, numpy default_rng([shuffle_seed, block]))")}
    return labels, textures, layout


def _scale_ticks(out, r, th, band):
    """Angle scale: an A5 band with 92 ticks every 10 degrees (long ones every 30)."""
    inb = (r >= band[0]) & (r <= band[1])
    out[inb] = 1
    deg = np.degrees(th) % 360
    d10 = np.abs((deg + 5) % 10 - 5)
    long_tick = np.abs((deg + 15) % 30 - 15) < 0.5
    reach = band[0] + np.where(long_tick, 1.0, 0.45) * (band[1] - band[0])
    out[inb & (np.radians(d10) * r < 0.09) & (r <= reach)] = 2


def _scale_numbers(labels, band, font=r"C:\Windows\Fonts\msyhbd.ttc"):
    """Numbers every 30 degrees beside the long ticks, and an outward arrow at 0 degrees, in 92."""
    from PIL import Image, ImageDraw, ImageFont

    def stamp(mask, cx, cy, up_deg):
        im = Image.fromarray((mask * 255).astype(np.uint8)).rotate(up_deg - 90.0, resample=Image.BILINEAR,
                                                                    expand=True)
        m = np.asarray(im) > 127
        h, w = m.shape
        x0, y0 = round((cx + HALF_MM) / CELL_MM - w / 2), round((HALF_MM - cy) / CELL_MM - h / 2)
        labels[y0:y0 + h, x0:x0 + w][m] = 2

    size = round(1.3 / CELL_MM)
    f = ImageFont.truetype(font, size)
    r_txt = band[0] + 0.55 * (band[1] - band[0]) + 0.35
    for a in range(0, 360, 30):
        im = Image.new("L", (size * 3, round(size * 1.3)), 0)
        ImageDraw.Draw(im).text((0, 0), str(a), font=f, fill=255)
        m = np.asarray(im) > 127
        m = m[:, m.any(0)]
        off = math.radians(a) + 1.6 / r_txt
        stamp(m, r_txt * math.cos(off), r_txt * math.sin(off), math.degrees(off))
    n = round(1.6 / CELL_MM)
    yy, xx = np.mgrid[0:n, 0:n]
    a = math.radians(-2.2)
    stamp(np.abs(xx - n / 2) < (yy + 1) / 2, (band[0] + 1.0) * math.cos(a), (band[0] + 1.0) * math.sin(a), -2.2)


def decode_slots(pairs: list[int]) -> tuple[int, int] | None:
    """Ring and sector from the 10 ID bits (1/0 per slot 1-10), or None if a parity fails."""
    b = list(pairs)
    if len(b) != 10 or (sum(b[:8]) & 1) != b[8] or (b[0] ^ b[2] ^ b[4] ^ b[6]) != b[9]:
        return None
    return (b[0] << 1) | b[1], int("".join(map(str, b[2:8])), 2)


def preview(labels: np.ndarray, textures: list[str], path: str, size: int = 1600) -> None:
    from PIL import Image
    colours = {"RND": (128, 128, 128), "A5": (25, 25, 60), "92": (235, 225, 200)}
    rng = np.random.default_rng(4)
    lut = np.array([colours.get(t, tuple(int(v) for v in rng.integers(40, 230, 3))) for t in textures], np.uint8)
    Image.fromarray(lut[labels]).resize((size, size), Image.NEAREST).save(path)


def save_layout(layout: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(layout, f, indent=2)
