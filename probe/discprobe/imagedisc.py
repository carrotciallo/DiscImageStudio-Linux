"""Burnable DVD image of a picture, placed with a measured geometry (u = r0/b, v = p/b).

Every 16-byte group of every sector gets the picture's value at its position on the
disc: dark groups are recorded as one texture (A5), light ones as another. Positions
come from the same model the `geo` ladder fits,

    Theta(n) = 2n / (S + u),  S = sqrt(u^2 + v n / pi),  radius = b * S,

so u and v fix every angle exactly; the assumed bit length b only scales the picture
uniformly, which cannot bend a line. The disc turns counter-clockwise as seen by the
optical head (ECMA-267), so seen from the data side the track angle runs clockwise:
the picture is drawn in data-side view with y up, and its rotation on the disc is
arbitrary.
"""

from __future__ import annotations

import json
import math
import os

import numpy as np

from . import dvd, iso9660
from .calib import GROUP_BITS, GROUP_BYTES, SECTOR_BITS, theta

CELL_MM = 0.02
HALF_MM = 60.0
SIZE = int(2 * HALF_MM / CELL_MM)


def _grid_coords():
    c = (np.arange(SIZE) + 0.5) * CELL_MM - HALF_MM
    return c[None, :], -c[:, None]  # x right, y up


def grid_design(r_min=24.5, r_max=56.0, spacing=5.0, line=0.3) -> np.ndarray:
    """True = dark. Cartesian grid, radial lines every 30 degrees, circles every
    spacing mm, and a block letter F (asymmetric, so a mirrored burn is obvious)."""
    x, y = _grid_coords()
    r = np.hypot(x, y)
    th = np.degrees(np.arctan2(y, x))
    half = line / 2
    near = lambda v: np.abs((v + spacing / 2) % spacing - spacing / 2) < half
    dark = near(x) | near(y)
    dark |= np.abs(r - np.round(r / spacing) * spacing) < half
    for a in range(0, 360, 30):
        d = np.abs(((th - a + 180) % 360) - 180)
        dark |= (np.radians(d) * r < max(0.2, half)) & (d < 90)
    # Letter F, 10 mm tall, in the upper half (stroke 1.2 mm).
    fx, fy, s = -3.0, 33.0, 1.2
    dark |= (x >= fx) & (x < fx + s) & (y >= fy) & (y < fy + 10)
    dark |= (x >= fx) & (x < fx + 6) & (y >= fy + 10 - s) & (y < fy + 10)
    dark |= (x >= fx) & (x < fx + 4.5) & (y >= fy + 5 - s / 2) & (y < fy + 5 + s / 2)
    return dark & (r >= r_min) & (r <= r_max)


def picture_design(path: str, diameter_mm: float = 116.0, threshold: float = 0.5) -> np.ndarray:
    """A grey picture fitted to a circle of the given diameter, thresholded (dark = True).

    Its longer side spans the diameter and it keeps its shape; what it doesn't cover stays light.
    """
    from PIL import Image
    n = round(diameter_mm / CELL_MM)
    limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None       # Pillow's size limit guards against files from strangers; this one was chosen by hand
    try:
        with Image.open(path) as im:
            longer = max(im.size)
            size = tuple(max(1, round(n * side / longer)) for side in im.size)
            g = np.asarray(im.convert("L").resize(size), dtype=np.float32) / 255
    finally:
        Image.MAX_IMAGE_PIXELS = limit
    out = np.zeros((SIZE, SIZE), bool)
    y, x = (SIZE - g.shape[0]) // 2, (SIZE - g.shape[1]) // 2
    out[y:y + g.shape[0], x:x + g.shape[1]] = g < threshold
    return out


def clear_inside(design: np.ndarray, r_mm: float) -> np.ndarray:
    """The design with everything inside this radius turned to background."""
    x, y = _grid_coords()
    out = design.copy()
    out[np.hypot(x, y) < r_mm] = False
    return out


def load_correction(path: str):
    """phi(r) in degrees from an angle-correction file (polynomial, held constant outside its range)."""
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    lo, hi = c["radius_valid_mm"]
    coef = np.array(c["poly_in_x"])
    return lambda r: np.polyval(coef, (np.clip(r, lo, hi) - 40.0) / 15.0)


def sectors_to_radius(u: float, v: float, bit_nm: float, r_mm: float) -> int:
    s = r_mm / (bit_nm * 1e-6)
    n = math.pi * (s * s - u * u) / v
    return int(n // SECTOR_BITS) // 16 * 16


CHUNK = 2048

# Column of each user byte in its data-frame row (12 header bytes, 172 bytes per row);
# repeating sequences are phased by column so the period runs on along the recorded row.
_COL = (12 + np.arange(dvd.SECTOR_BYTES)) % 172


def _hash(lbas: np.ndarray, salt: int) -> np.ndarray:
    """Deterministic pseudo-random uint64 per (sector, byte) (splitmix64 finaliser)."""
    with np.errstate(over="ignore"):
        x = (lbas[:, None].astype(np.uint64) * np.uint64(2048) + np.arange(dvd.SECTOR_BYTES, dtype=np.uint64)[None, :]
             + np.uint64(salt) * np.uint64(0x9E3779B97F4A7C15))
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return x ^ (x >> np.uint64(31))


def texture_bytes(spec: str, lbas: np.ndarray) -> np.ndarray:
    """Recorded-domain bytes Q (sectors x 2048) of one texture:
    "A5" one byte; "8B00" a byte sequence repeated along each row; "RND" random bytes;
    "MIX:92,4F" a random choice from the listed bytes."""
    n = len(lbas)
    if spec == "RND":
        return (_hash(lbas, 1) & np.uint64(0xFF)).astype(np.uint8)
    if spec.startswith("MIX:"):
        pool = np.array([int(b, 16) for b in spec[4:].split(",")], np.uint8)
        return pool[(_hash(lbas, 2) % np.uint64(len(pool))).astype(np.int64)]
    seq = np.frombuffer(bytes.fromhex(spec), np.uint8)
    return np.broadcast_to(seq[_COL % len(seq)], (n, dvd.SECTOR_BYTES)).copy()


def _sample(design, u, v, bit_mm, lba0, count, correction=None):
    """Design value at every 16-byte group of the given sectors (False / 0 outside)."""
    lbas = np.arange(lba0, lba0 + count)
    n = lbas[:, None].astype(np.float64) * SECTOR_BITS + GROUP_BITS[None, :]
    s = np.sqrt(u * u + v * n / math.pi)
    th = -theta(n, u, v)  # clockwise in data-side view
    r = bit_mm * s
    if correction is not None:
        # A byte at model angle th shows up at th + phi(r): give it the design there.
        th = th + np.radians(correction(r))
    ix = np.floor((r * np.cos(th) + HALF_MM) / CELL_MM).astype(np.int64)
    iy = np.floor((HALF_MM - r * np.sin(th)) / CELL_MM).astype(np.int64)
    ok = (ix >= 0) & (ix < SIZE) & (iy >= 0) & (iy < SIZE)
    return np.where(ok, design[np.clip(iy, 0, SIZE - 1), np.clip(ix, 0, SIZE - 1)], 0).astype(design.dtype)


def _textures(design: np.ndarray, dark: str, light: str, textures):
    """A boolean design picks light/dark; a label design (uint8) indexes `textures`."""
    if design.dtype == bool:
        return [light, dark]
    if not textures or int(design.max()) >= len(textures):
        raise ValueError("a label design needs one texture per label")
    return list(textures)


def _sector_q(design, texs, u, v, bit_mm, lba0, count, correction):
    lbas = np.arange(lba0, lba0 + count)
    labels = np.repeat(_sample(design, u, v, bit_mm, lba0, count, correction).astype(np.int64), GROUP_BYTES, axis=1)
    stack = np.stack([texture_bytes(t, lbas) for t in texs])
    return np.take_along_axis(stack, labels[None], 0)[0]


def write_iso(path: str, design: np.ndarray, u: float, v: float, bit_nm: float, total_sectors: int,
              dark: str = "A5", light: str = "B9", log=print, meta: dict | None = None, correction=None,
              textures=None) -> str:
    texs = _textures(design, dark, light, textures)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    bit_mm = bit_nm * 1e-6
    done, next_report = 0, 0.0
    with open(path, "wb") as f:
        while done < total_sectors:
            n = min(CHUNK, total_sectors - done)
            q = _sector_q(design, texs, u, v, bit_mm, done, n, correction)
            presets = ((np.arange(done, done + n) + dvd.DATA_START_PSN) >> 4) & 0xF
            f.write((q ^ dvd.MASKS[presets]).tobytes())
            done += n
            if done / total_sectors >= next_report:
                log(f"  {100 * done / total_sectors:5.1f} %")
                next_report += 0.2
    iso9660.add(path, total_sectors, "DISCPROBE_IMAGE")
    spec = {"kind": "dvd-picture", "u": u, "v": v, "bit_nm": bit_nm, "total_sectors": total_sectors,
            "textures": texs, "cell_mm": CELL_MM, **(meta or {})}
    if design.dtype == bool:
        spec.update(dark=dark, light=light)
    spec_path = os.path.splitext(path)[0] + ".image.json"
    with open(spec_path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2)
    return spec_path


def verify_iso(path: str, design: np.ndarray, u: float, v: float, bit_nm: float, total_sectors: int,
               dark: str = "A5", light: str = "B9", samples: int = 300, seed: int = 3, correction=None,
               textures=None) -> list[str]:
    """Descramble random sectors and compare every byte with a recomputation from the design."""
    problems = []
    if os.path.getsize(path) != total_sectors * dvd.SECTOR_BYTES:
        return ["size mismatch"]
    texs = _textures(design, dark, light, textures)
    rng = np.random.default_rng(seed)
    with open(path, "rb") as f:
        for lba in rng.integers(32, total_sectors, samples):
            f.seek(int(lba) * dvd.SECTOR_BYTES)
            rec = dvd.recorded(np.frombuffer(f.read(dvd.SECTOR_BYTES), dtype=np.uint8), int(lba))
            want = _sector_q(design, texs, u, v, bit_nm * 1e-6, int(lba), 1, correction)[0]
            if not np.array_equal(rec, want):
                problems.append(f"LBA {lba} differs from the design")
    return problems


def preview(design: np.ndarray, path: str, size: int = 1200) -> None:
    from PIL import Image
    img = Image.fromarray(np.where(design, 0, 255).astype(np.uint8)).resize((size, size))
    img.save(path)
