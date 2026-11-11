"""Beacon target: a texture palette disc whose tiles can be found and read from one photo
with no whole-disc fit, even when most of the disc is dark.

Differences from tiledisc:
    Finding: each tile has three bullseyes, concentric A5 / 66 / 92 rings. They are looked for
    by their edges, so it does not matter which ring is bright or what colour it is.
    ID: 5 bits in a 16-bit first-order Reed-Muller code (minimum distance 8), against 8 bits
    with 2 parity bits on the older discs.
    Texture pairs: half of the bits use 92/66 and half A5/92. In the LUT v2 photos 92/66 had
    the best worst-photo contrast of all pairs (0.56 median normalised RGB distance, A5/92
    0.26), and A5/92 is what we know to work near the mirror direction.
    Pose: a ring of bullseyes at r = 56 mm gives points around the whole disc.

Tile layout, in tile coordinates (row 0 = inner edge, column 0 = smallest angle, angle
counter-clockwise in the data-side view):

    ID zone, ID_FRAC of the tile's angle, 8 rows x 6 columns of cells:
        bullseyes centred on the 2 x 2 cell blocks at rows 0-1 / columns 0-1 (A),
        rows 6-7 / columns 0-1 (B) and rows 6-7 / columns 4-5 (C). The fourth corner has none,
        so the tile's orientation can be read from the three.
        18 radial cell pairs, column by column: REFERENCE_SLOTS hold a pair in a fixed order,
        the other 16 hold one code bit each. 1 = first texture of the pair inner, 0 = outer.
    Swatch zone: 3 columns x 3 rows, one swatch per palette texture, in randomised Latin
    squares (tiledisc.swatch_slots).
"""

from __future__ import annotations

import json
import math

import numpy as np

from . import tiledisc
from .imagedisc import CELL_MM, HALF_MM, SIZE

RING_EDGES_MM = (25.0, 39.5, 54.0)
TILE_MM = 18.0
GAP_MM = 1.0
ROWS, ID_COLS = 8, 6
ID_FRAC = 9.5 / 17.0
SHUFFLE_SEED = 4
FINDER_BLOCKS = {"A": (0, 0), "B": (6, 0), "C": (6, 4)}      # (row, column) of each 2 x 2 block
FINDER_RADII_MM = (0.45, 0.85, 1.25)                         # A5 centre, 66 ring, 92 ring
MARK_BAND_MM = (54.4, 57.6)
MARK_RADIUS_MM = 56.0
MARK_RADII_MM = (0.54, 1.02, 1.5)
MARK_ANGLES_DEG = tuple(5 + 10 * k for k in range(36))       # between the 10 degree ticks of the scale
PALETTE = ("92", "66", "A5", "B9", "F9", "B797439866", "4AD4B2", "C0CDE6B2D1CB3E", "B7B2")
BACKGROUND = "RND"
PAIRS = (("92", "66"), ("A5", "92"))
REFERENCE_SLOTS = {0: 0, 17: 1}                              # slot -> pair index
# Which pair carries each of the 16 code bits, in slot order. Exhaustive search over the 8/8
# splits: all 16 bits keep distance 8 between used IDs, but either half alone only keeps 2,
# so one pair by itself can flag an ID but not confirm it (see bank_distances).
BIT_PAIR = (0, 0, 0, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1)


def _geometry() -> dict:
    return {"ring_edges_mm": RING_EDGES_MM, "tile_mm": TILE_MM, "gap_mm": GAP_MM, "rows": 6, "cols": 7, "id_cols": 4,
            "scale_mm": None, "shuffle_seed": SHUFFLE_SEED}


def sectors_per_ring() -> list[int]:
    return tiledisc.sectors_per_ring(_geometry())


def tile_id(ring: int, sector: int) -> int:
    return sum(sectors_per_ring()[:ring]) + sector


def ring_sector(tid: int) -> tuple[int, int] | None:
    for ring, n in enumerate(sectors_per_ring()):
        if tid < n:
            return ring, tid
        tid -= n
    return None


def codeword(tid: int) -> np.ndarray:
    """First-order Reed-Muller RM(1,4): 16 bits for a 5-bit ID, any two words differ in at least 8."""
    x = np.arange(16)
    bits = [(x >> k) & 1 for k in range(4)]
    return (((tid >> 4) & 1) ^ sum(((tid >> k) & 1) * bits[k] for k in range(4))) % 2


def bank_distances() -> tuple[int, int, int]:
    """Minimum distance between used IDs over all bits, and over each pair's bits alone."""
    words = np.array([codeword(t) for t in range(sum(sectors_per_ring()))])
    bank = np.array(BIT_PAIR)
    out = []
    for mask in (np.ones(16, bool), bank == 0, bank == 1):
        d = (words[:, None, mask] != words[None, :, mask]).sum(-1)
        out.append(int(d[~np.eye(len(words), dtype=bool)].min()))
    return tuple(out)


def slots() -> list[tuple[int, int]]:
    """(lower row, column) of the 18 radial cell pairs, in slot order."""
    out = []
    for col in range(ID_COLS):
        for row in range(0, ROWS, 2):
            if not any(row in (r, r + 1) and col in (c, c + 1) for r, c in FINDER_BLOCKS.values()):
                out.append((row, col))
    return out


def tile_cells(ring: int, sector: int) -> list[list[str]]:
    """ROWS x ID_COLS texture names of the ID zone (None under the bullseyes)."""
    cells = [[None] * ID_COLS for _ in range(ROWS)]
    word = codeword(tile_id(ring, sector))
    bit = 0
    for s, (row, col) in enumerate(slots()):
        if s in REFERENCE_SLOTS:
            first, second = PAIRS[REFERENCE_SLOTS[s]]
        else:
            first, second = PAIRS[BIT_PAIR[bit]]
            if not word[bit]:
                first, second = second, first
            bit += 1
        cells[row][col], cells[row + 1][col] = first, second
    return cells


def _tile_frame(ring: int, sector: int) -> tuple[float, float, float, float]:
    """Inner radius, radial size (mm), and the start angle and dth of a tile's sector."""
    r_in = RING_EDGES_MM[ring] + GAP_MM / 2
    return r_in, RING_EDGES_MM[ring + 1] - GAP_MM / 2 - r_in, sector * 2 * math.pi / sectors_per_ring()[ring], \
        2 * math.pi / sectors_per_ring()[ring]


def id_point(ring: int, sector: int, row: float, col: float) -> tuple[float, float]:
    """(r mm, angle rad) of a point of the ID zone, in cell coordinates (a cell's centre is +0.5)."""
    r_in, dr, a0, dth = _tile_frame(ring, sector)
    r = r_in + row / ROWS * dr
    pad = GAP_MM / 2 / r
    return r, a0 + pad + col / ID_COLS * ID_FRAC * (dth - 2 * pad)


def finder_centres(ring: int, sector: int) -> dict[str, tuple[float, float]]:
    return {k: id_point(ring, sector, row + 1.0, col + 1.0) for k, (row, col) in FINDER_BLOCKS.items()}


def swatch_centres(ring: int, sector: int) -> dict[str, tuple[float, float]]:
    """(r mm, angle rad) of the centre of each palette swatch."""
    r_in, dr, a0, dth = _tile_frame(ring, sector)
    out = {}
    for name, slot in zip(PALETTE, tiledisc.swatch_slots(ring, sector, len(PALETTE), _geometry())):
        col, row = divmod(int(slot), 3)
        r = r_in + (row + 0.5) / 3 * dr
        pad = GAP_MM / 2 / r
        out[name] = (r, a0 + pad + (ID_FRAC + (col + 0.5) / 3 * (1 - ID_FRAC)) * (dth - 2 * pad))
    return out


def _paint_bullseye(labels, index, x_mm, y_mm, radii):
    n = int(radii[-1] / CELL_MM) + 2
    ci, cj = round((x_mm + HALF_MM) / CELL_MM - 0.5), round((HALF_MM - y_mm) / CELL_MM - 0.5)
    jj, ii = np.mgrid[cj - n:cj + n + 1, ci - n:ci + n + 1]
    d = np.hypot((ii + 0.5) * CELL_MM - HALF_MM - x_mm, HALF_MM - (jj + 0.5) * CELL_MM - y_mm)
    for r, tex in zip(radii[::-1], ("92", "66", "A5")):
        labels[jj[d <= r], ii[d <= r]] = index[tex]


def design() -> tuple[np.ndarray, list[str], dict]:
    """Label map (SIZE x SIZE uint8), texture list for the labels, and the layout record."""
    textures = [BACKGROUND, "A5", "92"] + [t for t in PALETTE if t not in (BACKGROUND, "A5", "92")]
    index = {t: i for i, t in enumerate(textures)}
    nsec = sectors_per_ring()
    labels = np.zeros((SIZE, SIZE), np.uint8)
    c = (np.arange(SIZE) + 0.5) * CELL_MM - HALF_MM
    x = c[None, :]
    id_tables = [np.array([[[index[t] if t else 0 for t in row] for row in tile_cells(k, j)] for j in range(n)],
                          np.uint8) for k, n in enumerate(nsec)]
    swatch_tables = []
    for k, n in enumerate(nsec):
        t = np.zeros((n, 3, 3), np.uint8)
        for j in range(n):
            for name, slot in zip(PALETTE, tiledisc.swatch_slots(k, j, len(PALETTE), _geometry())):
                col, row = divmod(int(slot), 3)
                t[j, row, col] = index[name]
        swatch_tables.append(t)
    for y0 in range(0, SIZE, 500):
        y = -c[y0:y0 + 500, None]
        r = np.hypot(x, y)
        th = np.arctan2(y, x) % (2 * math.pi)
        out = np.zeros(r.shape, np.uint8)
        for k, n in enumerate(nsec):
            r_in, r_out = RING_EDGES_MM[k] + GAP_MM / 2, RING_EDGES_MM[k + 1] - GAP_MM / 2
            dth = 2 * math.pi / n
            j = np.floor(th / dth).astype(np.int64) % n
            pad = GAP_MM / 2 / np.maximum(r, 1e-6)
            a = (th - j * dth - pad) / np.maximum(dth - 2 * pad, 1e-6)
            m = (r >= r_in) & (r < r_out) & (a >= 0) & (a < 1)
            fr = (r - r_in) / (r_out - r_in)
            in_id = m & (a < ID_FRAC)
            row = np.clip((fr * ROWS).astype(np.int64), 0, ROWS - 1)
            col = np.clip((a / ID_FRAC * ID_COLS).astype(np.int64), 0, ID_COLS - 1)
            out[in_id] = id_tables[k][j[in_id], row[in_id], col[in_id]]
            in_sw = m & (a >= ID_FRAC)
            row = np.clip((fr * 3).astype(np.int64), 0, 2)
            col = np.clip(((a - ID_FRAC) / (1 - ID_FRAC) * 3).astype(np.int64), 0, 2)
            out[in_sw] = swatch_tables[k][j[in_sw], row[in_sw], col[in_sw]]
        tiledisc._scale_ticks(out, r, th, MARK_BAND_MM)
        labels[y0:y0 + 500] = out
    tiledisc._scale_numbers(labels, MARK_BAND_MM)
    tiles = []
    for k, n in enumerate(nsec):
        for j in range(n):
            f = finder_centres(k, j)
            for r_mm, a in f.values():
                _paint_bullseye(labels, index, r_mm * math.cos(a), r_mm * math.sin(a), FINDER_RADII_MM)
            tiles.append({"id": tile_id(k, j), "ring": k, "sector": j,
                          "finders": {name: [round(v[0], 4), round(math.degrees(v[1]), 4)] for name, v in f.items()},
                          "swatches": {name: [round(v[0], 4), round(math.degrees(v[1]), 4)]
                                       for name, v in swatch_centres(k, j).items()}})
    for a_deg in MARK_ANGLES_DEG:
        a = math.radians(a_deg)
        _paint_bullseye(labels, index, MARK_RADIUS_MM * math.cos(a), MARK_RADIUS_MM * math.sin(a), MARK_RADII_MM)
    layout = {"kind": "beacon-target", "ring_edges_mm": list(RING_EDGES_MM), "tile_mm": TILE_MM, "gap_mm": GAP_MM,
              "sectors_per_ring": nsec, "palette": list(PALETTE), "background": BACKGROUND, "shuffle_seed": SHUFFLE_SEED,
              "angle": "counter-clockwise from +x in the data-side view, y up; [r_mm, angle_deg] pairs",
              "id_rows": ROWS, "id_cols": ID_COLS, "id_frac": ID_FRAC, "pairs": [list(p) for p in PAIRS],
              "finder_radii_mm": list(FINDER_RADII_MM), "bit_pair": list(BIT_PAIR),
              "reference_slots": {str(k): v for k, v in REFERENCE_SLOTS.items()},
              "marks": {"radius_mm": MARK_RADIUS_MM, "angles_deg": list(MARK_ANGLES_DEG), "radii_mm": list(MARK_RADII_MM)},
              "scale_band_mm": list(MARK_BAND_MM), "tiles": tiles}
    return labels, textures, layout


def preview(labels: np.ndarray, textures: list[str], path: str, size: int = 1600) -> None:
    tiledisc.preview(labels, textures, path, size)


def save_layout(layout: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(layout, f, indent=1)
