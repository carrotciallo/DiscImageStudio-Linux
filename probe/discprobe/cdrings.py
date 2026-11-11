"""CD-R texture rings, retaining the media-independent ringscan layout interface."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

import numpy as np

from . import cd, cdimage, iso9660
from .rings import RingLayout as DvdRingLayout


@dataclass
class RingLayout(DvdRingLayout):
    textures: tuple = cd.DEFAULT_TEXTURES
    ring_width_mm: float = 2.0
    start_mm: float = 26.0
    r0_mm: float = cd.R0_MM
    pitch_um: float = cd.PITCH_UM
    bit_nm: float = cd.BIT_NM
    filler: str = "AA"
    kind: str = "cd-texture-rings"

    def sector_at(self, r_mm):
        length = cd.SECTOR_BITS * self.bit_nm * 1e-6
        return round(math.pi * (r_mm ** 2 - self.r0_mm ** 2) / (self.pitch_um * 1e-3 * length))

    def radius_at(self, sector):
        length = cd.SECTOR_BITS * self.bit_nm * 1e-6
        return math.sqrt(self.r0_mm ** 2 + self.pitch_um * 1e-3 * sector * length / math.pi)

    def build(self):
        if self.groups < 2 or self.ring_width_mm <= 0 or self.start_mm <= self.r0_mm:
            raise ValueError("CD rings need >=2 groups, positive width and start radius above r0")
        super().build()
        cd.check_capacity(self.total_sectors)
        if self.rings[0]["lba_start"] <= 20:
            raise ValueError("ISO 9660 sectors overlap the first CD ring")
        for t in (*self.textures, self.filler):
            if t != "RND" and (len(t) != 2 or not 0 <= int(t, 16) <= 255):
                raise ValueError("CD ring texture must be a hex byte or RND; use tiles for sequences")
        if not {"0D", "AA"} <= set(self.textures):
            raise ValueError("CD rings need 0D and AA references (ringscan --refs 0D,AA)")
        if any(r["lba_end"] <= r["lba_start"] for r in self.rings):
            raise ValueError("ring narrower than one CD sector")
        return self


def write_iso(path, layout, log=print):
    cd.check_capacity(layout.total_sectors)
    cdimage._new_paths(path, ".rings.json")
    rng = np.random.default_rng(layout.seed)
    with open(path, "xb") as fh:
        for start, end, texture in layout.segments():
            for a in range(start, end, 8192):
                count = min(8192, end - a)
                if texture == "RND":
                    data = rng.integers(0, 256, (count, 2048), dtype=np.uint8)
                else:
                    data = np.broadcast_to(cd.payload_for(int(texture, 16)), (count, 2048))
                fh.write(data.tobytes())
            log(f"  {100 * end / layout.total_sectors:5.1f} %")
    iso9660.add(path, layout.total_sectors, "DISCPROBE_CD_RINGS")
    spec = os.path.splitext(path)[0] + ".rings.json"
    layout.save(spec)
    return spec


def verify_iso(path, layout, samples_per_ring=12, seed=5):
    if os.path.getsize(path) != layout.total_sectors * 2048:
        return ["size mismatch"]
    problems, rng = [], np.random.default_rng(seed)
    with open(path, "rb") as fh:
        for start, end, t in layout.segments():
            picks = {start, end - 1, *rng.integers(start, end, samples_per_ring).tolist()}
            for lba in sorted(picks):
                if lba in iso9660.SECTORS:
                    continue
                fh.seek(lba * 2048)
                rec = np.frombuffer(fh.read(2048), np.uint8) ^ cd.MASK
                if t == "RND":
                    bad = np.bincount(rec, minlength=256).max() > 40
                else:
                    bad = np.any(rec != int(t, 16))
                if bad:
                    problems.append(f"LBA {lba}: unexpected {t} texture")
    return problems
