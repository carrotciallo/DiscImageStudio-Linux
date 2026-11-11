"""Concentric texture-ring test disc for DVD±R.

Every ring is filled with one recorded (scrambled-domain) byte Q, or with random
data. A ring depends only on radius, so the disc needs no angle calibration: a
1 % error in the nominal geometry moves ring edges by about 0.25 mm at most, and the
scan analysis measures the edges anyway.

Layout: G groups (inner, middle, outer), each containing every texture once. The
order is rotated by 3 places per group and reversed in odd groups, so no texture
always sits at the same relative radius. The references A5 (darkest so far) and 92
(brightest) are among the textures; the analysis interpolates them across groups to
remove radius-dependent lighting.

The ISO is raw 2048-byte sectors with no file system. Burn it with "write image",
any write mode; note the write speed, since it may change the result.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field

import numpy as np

from . import dvd, iso9660
from .geometry import DVD_SECTOR_MM

DEFAULT_TEXTURES = ("A5", "B9", "66", "64", "E4", "92", "RND")
DVD_PLUS_R_SECTORS = 2295104  # the smaller of DVD+R and DVD-R single layer


@dataclass
class RingLayout:
    textures: tuple = DEFAULT_TEXTURES
    groups: int = 3
    ring_width_mm: float = 1.4
    start_mm: float = 25.0
    r0_mm: float = 24.0
    pitch_um: float = 0.74
    bit_nm: float = 133.3
    filler: str = "92"
    seed: int = 1
    rings: list = field(default_factory=list)
    total_sectors: int = 0
    kind: str = "dvd-texture-rings"
    version: int = 1

    def sector_at(self, r_mm: float) -> int:
        sector_mm = DVD_SECTOR_MM * self.bit_nm / 133.3
        n = math.pi * (r_mm ** 2 - self.r0_mm ** 2) / (self.pitch_um * 1e-3 * sector_mm)
        return int(round(n / dvd.BLOCK_SECTORS)) * dvd.BLOCK_SECTORS

    def radius_at(self, sector: float) -> float:
        sector_mm = DVD_SECTOR_MM * self.bit_nm / 133.3
        return math.sqrt(self.r0_mm ** 2 + self.pitch_um * 1e-3 * sector * sector_mm / math.pi)

    def build(self) -> "RingLayout":
        n = len(self.textures)
        self.rings = []
        for g in range(self.groups):
            order = [self.textures[(i + 3 * g) % n] for i in range(n)]
            if g % 2:
                order.reverse()
            for j, tex in enumerate(order):
                i = g * n + j
                ra = self.start_mm + i * self.ring_width_mm
                rb = ra + self.ring_width_mm
                self.rings.append({"index": i, "group": g, "texture": tex,
                                   "r_start_mm": round(ra, 4), "r_end_mm": round(rb, 4),
                                   "lba_start": self.sector_at(ra), "lba_end": self.sector_at(rb)})
        self.total_sectors = self.rings[-1]["lba_end"]
        return self

    def segments(self):
        """(lba_start, lba_end, texture) covering the whole image, filler first."""
        out = [(0, self.rings[0]["lba_start"], self.filler)] if self.rings[0]["lba_start"] > 0 else []
        return out + [(r["lba_start"], r["lba_end"], r["texture"]) for r in self.rings]

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "RingLayout":
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        d["textures"] = tuple(d["textures"])
        if d.get("kind") == "cd-texture-rings":
            from .cdrings import RingLayout as CdRingLayout
            return CdRingLayout(**d)
        return cls(**d)


def _q(texture: str) -> int | None:
    return None if texture.upper() == "RND" else int(texture, 16)


def _check(layout: RingLayout) -> None:
    for t in (*layout.textures, layout.filler):
        if t.upper() != "RND" and not (len(t) == 2 and 0 <= int(t, 16) <= 255):
            raise ValueError(f"texture {t!r} is neither a hex byte nor RND")
    if "A5" not in layout.textures or "92" not in layout.textures:
        raise ValueError("A5 and 92 must be among the textures; they are the analysis references")
    if layout.groups < 2:
        raise ValueError("at least two groups are needed to interpolate the references")
    if layout.total_sectors > DVD_PLUS_R_SECTORS:
        raise ValueError(f"layout needs {layout.total_sectors} sectors, more than a single-layer disc "
                         f"({DVD_PLUS_R_SECTORS}); reduce groups, ring width or start radius")


CHUNK_BLOCKS = 512  # 16 MiB per write


def write_iso(path: str, layout: RingLayout, log=print) -> str:
    _check(layout)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    rng = np.random.default_rng(layout.seed)
    cycles = {}
    done, total = 0, layout.total_sectors
    next_report = 0.0
    with open(path, "wb") as f:
        for start, end, tex in layout.segments():
            q = _q(tex)
            if q is not None and q not in cycles:
                # One ECC block per preset; block b uses preset (b + 0x3000) & 15 = b & 15.
                cycles[q] = np.concatenate([np.tile(dvd.MASKS[k] ^ np.uint8(q), dvd.BLOCK_SECTORS)
                                            for k in range(16)] * 2)
            b = start // dvd.BLOCK_SECTORS
            b_end = end // dvd.BLOCK_SECTORS
            while b < b_end:
                n = min(CHUNK_BLOCKS, b_end - b)
                if q is None:
                    buf = rng.integers(0, 256, n * dvd.BLOCK_SECTORS * dvd.SECTOR_BYTES, dtype=np.uint8)
                    f.write(buf.tobytes())
                else:
                    block_bytes = dvd.BLOCK_SECTORS * dvd.SECTOR_BYTES
                    k = 0
                    while k < n:
                        m = min(16, n - k)
                        off = ((b + k) & 15) * block_bytes
                        f.write(cycles[q][off:off + m * block_bytes].tobytes())
                        k += m
                b += n
                done += n * dvd.BLOCK_SECTORS
                if done / total >= next_report:
                    log(f"  {100 * done / total:5.1f} %")
                    next_report += 0.1
    iso9660.add(path, layout.total_sectors, "DISCPROBE_RINGS")
    spec_path = os.path.splitext(path)[0] + ".rings.json"
    layout.save(spec_path)
    return spec_path


def verify_iso(path: str, layout: RingLayout, samples_per_ring: int = 12, seed: int = 5) -> list[str]:
    """Descramble sampled sectors independently of the writer; return a list of problems."""
    problems = []
    size = os.path.getsize(path)
    if size != layout.total_sectors * dvd.SECTOR_BYTES:
        problems.append(f"size {size} bytes, expected {layout.total_sectors * dvd.SECTOR_BYTES}")
        return problems
    rng = np.random.default_rng(seed)
    with open(path, "rb") as f:
        for start, end, tex in layout.segments():
            q = _q(tex)
            picks = {start, end - 1, *rng.integers(start, end, samples_per_ring).tolist()}
            for lba in sorted(picks):
                if lba in iso9660.SECTORS:
                    continue
                f.seek(lba * dvd.SECTOR_BYTES)
                payload = np.frombuffer(f.read(dvd.SECTOR_BYTES), dtype=np.uint8)
                rec = dvd.recorded(payload, lba)
                if q is None:
                    if np.bincount(rec, minlength=256).max() > 40:
                        problems.append(f"LBA {lba} ({tex}) does not look random")
                elif not np.all(rec == q):
                    problems.append(f"LBA {lba} ({tex}) records {np.unique(rec)[:4]} instead of {q:02X}")
    return problems


def describe(layout: RingLayout) -> list[str]:
    lines = [f"{'ring':>4} {'group':>5} {'texture':>7} {'radius mm':>13} {'LBA':>19}"]
    for r in layout.rings:
        lines.append(f"{r['index']:>4} {r['group']:>5} {r['texture']:>7} "
                     f"{r['r_start_mm']:6.2f}-{r['r_end_mm']:6.2f} {r['lba_start']:>9}-{r['lba_end']:<9}")
    gb = layout.total_sectors * dvd.SECTOR_BYTES / 1e9
    lines.append(f"{layout.total_sectors} sectors ({gb:.2f} GB), filler {layout.filler} below "
                 f"{layout.rings[0]['r_start_mm']} mm; nominal geometry r0 {layout.r0_mm} mm, "
                 f"pitch {layout.pitch_um} um, bit {layout.bit_nm} nm")
    return lines
