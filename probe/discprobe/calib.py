"""Multi-hypothesis calibration disc for DVD±R: bracket the geometry, then fit it.

A DVD byte at channel-bit position n (counted from LBA 0) lies at accumulated track
angle

    Theta(n) = 2 pi (S - u) / v,   S = sqrt(u^2 + v n / pi),   u = r0 / b,   v = p / b,

with r0 the radius of LBA 0, p the track pitch and b the channel bit length. Only the
ratios u and v matter for angles. The local rate is dTheta/dn = 1 / S = b / r.

The disc is split into thin bands separated by plain guard rings. Band j draws a
spoke pattern f(theta) = 0.5 + w3 cos(3 theta + phi3) + w9 cos(9 theta + phi9) at the
angle a hypothesis assigns to each byte, Theta_j(n) = (1 + s_j) Theta_nominal(n): the
nominal geometry with its local rate scaled by 1 + s_j, s_j swept over a range
(default -1.2 % .. +1.2 % in 0.2 % steps). On the real disc the band shows the spokes
rotated by delta_j(n) = Theta(n) - Theta_j(n). Where s_j is within about 0.15 % of
the true local rate error, delta changes slowly enough across the band for the scan to
resolve it; other bands blur to grey. Each readable band measures the true local rate,
and the phases of all readable bands share one unknown rotation, so together they fix
u and v (see calscan.py).

The hypotheses are repeated in several groups from inner to outer radius (ascending
in even groups, descending in odd ones), so readable bands occur at several radii.

Each byte is A5 (dark) with probability f and 92 (bright) otherwise, so the scanner
sees the mean brightness f. The 9-fold term is phase-locked to the 3-fold one with a
90 degree offset; that makes the pattern chiral, so the analysis can tell a mirrored
scan from a normal one, and a dark/light inversion does not change the test.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field

import numpy as np

from . import dvd, iso9660
from .rings import DVD_PLUS_R_SECTORS

SECTOR_BITS = 38688
GROUP_BYTES = 16  # angle evaluated once per 16 bytes (about 34 um of track)


def _byte_bit_offsets() -> np.ndarray:
    """Channel-bit offset of each user byte from the start of its sector.

    A recorded sector is 13 rows of two sync frames (1488 bits each: 32 sync bits and
    91 bytes). The data frame (4 ID, 2 IED, 6 CPR_MAI, 2048 user, 4 EDC bytes) fills
    12 rows of 172 bytes; the 10 PI bytes end each row and the 13th row is PO parity.
    """
    j = np.arange(dvd.SECTOR_BYTES) + 12
    row, col = j // 172, j % 172
    inrow = np.where(col < 91, 32 + 16 * col, 1488 + 32 + 16 * (col - 91))
    return (row * 2976 + inrow + 8).astype(np.float64)  # +8: middle of the byte


BYTE_BITS = _byte_bit_offsets()
GROUP_BITS = BYTE_BITS.reshape(-1, GROUP_BYTES).mean(axis=1)


def theta(n, u, v):
    """Accumulated track angle in radians at channel bit n."""
    n = np.asarray(n, dtype=np.float64)
    s = np.sqrt(u * u + v * n / math.pi)
    # 2 pi (s - u) / v, with s - u written as (s^2 - u^2) / (s + u) to keep precision.
    return 2.0 * n / (s + u)


def rate(n, u, v):
    """dTheta/dn in radians per channel bit."""
    return 1.0 / np.sqrt(u * u + v * np.asarray(n, dtype=np.float64) / math.pi)


@dataclass
class CalLayout:
    s_range: float = 0.012
    s_step: float = 0.002
    groups: int = 3
    start_mm: float = 25.0
    end_mm: float = 57.0
    guard_mm: float = 0.2
    r0_mm: float = 24.0
    pitch_um: float = 0.74
    bit_nm: float = 133.3
    ks: tuple = (3, 9)
    phases_deg: tuple = (0.0, 90.0)
    weights: tuple = (0.3, 0.2)
    guard: str = "92"
    seed: int = 1
    bands: list = field(default_factory=list)
    guards_lba: list = field(default_factory=list)
    total_sectors: int = 0
    kind: str = "dvd-multi-hypothesis-calibration"
    version: int = 1

    @property
    def u0(self) -> float:
        return self.r0_mm / (self.bit_nm * 1e-6)

    @property
    def v0(self) -> float:
        return self.pitch_um * 1e-3 / (self.bit_nm * 1e-6)

    def hypotheses(self) -> list[float]:
        m = int(round(self.s_range / self.s_step))
        return [round(i * self.s_step, 6) for i in range(-m, m + 1)]

    def sector_at(self, r_mm: float) -> int:
        b = self.bit_nm * 1e-6
        n_bits = math.pi * ((r_mm / b) ** 2 - self.u0 ** 2) / self.v0
        return int(round(n_bits / SECTOR_BITS / dvd.BLOCK_SECTORS)) * dvd.BLOCK_SECTORS

    def build(self) -> "CalLayout":
        hyp = self.hypotheses()
        slots = self.groups * len(hyp)
        width = (self.end_mm - self.start_mm - self.guard_mm) / slots
        if width - self.guard_mm < 0.3:
            raise ValueError(f"bands would be {width - self.guard_mm:.2f} mm wide; use fewer hypotheses or groups")
        self.bands, self.guards_lba = [], []
        for g in range(self.groups):
            order = hyp if g % 2 == 0 else hyp[::-1]
            for j, s in enumerate(order):
                i = g * len(hyp) + j
                a = self.start_mm + i * width
                self.guards_lba.append([self.sector_at(a), self.sector_at(a + self.guard_mm)])
                self.bands.append({"index": i, "group": g, "s": s,
                                   "r_start_mm": round(a + self.guard_mm, 4), "r_end_mm": round(a + width, 4),
                                   "lba_start": self.sector_at(a + self.guard_mm),
                                   "lba_end": self.sector_at(a + width)})
        end = self.start_mm + slots * width
        self.guards_lba.append([self.sector_at(end), self.sector_at(end + self.guard_mm)])
        self.total_sectors = self.guards_lba[-1][1]
        return self

    def edge_lbas(self) -> list[int]:
        """Every guard/band boundary, inner to outer."""
        out = []
        for g, b in zip(self.guards_lba, self.bands):
            out += [g[0], b["lba_start"]]
        return out + list(self.guards_lba[-1])

    def pattern(self, th: np.ndarray) -> np.ndarray:
        f = np.full(th.shape, 0.5)
        for k, ph, w in zip(self.ks, self.phases_deg, self.weights):
            f += w * np.cos(k * th + math.radians(ph))
        return f

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "CalLayout":
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        for key in ("ks", "phases_deg", "weights"):
            d[key] = tuple(d[key])
        return cls(**d)


def refine_layout(fit: dict, groups: int = 20, **kw) -> CalLayout:
    """Second disc: every band drawn with the fitted geometry, so every band is matched
    and its phase no longer depends on how well the scan maps radius to LBA."""
    return CalLayout(r0_mm=fit["r0_mm_at_bit"], pitch_um=fit["pitch_um_at_bit"], bit_nm=fit["bit_nm_assumed"],
                     s_range=0.0, groups=groups, **kw).build()


CHUNK_SECTORS = 2048


def _band_sectors(layout: CalLayout, band: dict, lba0: int, count: int, rng) -> np.ndarray:
    lbas = np.arange(lba0, lba0 + count)
    n0 = lbas.astype(np.float64) * SECTOR_BITS
    scale = 1.0 + band["s"]
    th0 = scale * theta(n0, layout.u0, layout.v0)
    rt = scale * rate(n0 + SECTOR_BITS / 2, layout.u0, layout.v0)
    th = th0[:, None] + rt[:, None] * GROUP_BITS[None, :]
    f = np.clip(layout.pattern(th), 0.0, 1.0)
    thresh = np.repeat(np.round(f * 256).astype(np.int16), GROUP_BYTES, axis=1)
    dark = rng.integers(0, 256, thresh.shape, dtype=np.int16) < thresh
    q = np.where(dark, np.uint8(0xA5), np.uint8(0x92))
    presets = ((lbas + dvd.DATA_START_PSN) >> 4) & 0xF
    return q ^ dvd.MASKS[presets]


def _plain_sectors(q: int, lba0: int, count: int) -> np.ndarray:
    lbas = np.arange(lba0, lba0 + count)
    presets = ((lbas + dvd.DATA_START_PSN) >> 4) & 0xF
    return dvd.MASKS[presets] ^ np.uint8(q)


def segments(layout: CalLayout):
    """(lba_start, lba_end, band or None) for the whole image; None is plain guard texture."""
    out = [(0, layout.guards_lba[0][0], None)] if layout.guards_lba[0][0] > 0 else []
    for g, b in zip(layout.guards_lba, layout.bands):
        out += [(g[0], b["lba_start"], None), (b["lba_start"], b["lba_end"], b)]
    out.append((layout.guards_lba[-1][0], layout.guards_lba[-1][1], None))
    return out


def write_iso(path: str, layout: CalLayout, log=print) -> str:
    if layout.total_sectors > DVD_PLUS_R_SECTORS:
        raise ValueError(f"layout needs {layout.total_sectors} sectors, more than a single-layer disc "
                         f"({DVD_PLUS_R_SECTORS}); lower --end-mm")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    rng = np.random.default_rng(layout.seed)
    q_guard = int(layout.guard, 16)
    done, next_report = 0, 0.0
    with open(path, "wb") as fh:
        for start, end, band in segments(layout):
            lba = start
            while lba < end:
                n = min(CHUNK_SECTORS, end - lba)
                data = (_plain_sectors(q_guard, lba, n) if band is None
                        else _band_sectors(layout, band, lba, n, rng))
                fh.write(data.tobytes())
                lba += n
                done += n
                if done / layout.total_sectors >= next_report:
                    log(f"  {100 * done / layout.total_sectors:5.1f} %")
                    next_report += 0.1
    iso9660.add(path, layout.total_sectors, "DISCPROBE_CAL")
    spec_path = os.path.splitext(path)[0] + ".cal.json"
    layout.save(spec_path)
    return spec_path


def verify_iso(path: str, layout: CalLayout, samples: int = 6, seed: int = 9) -> list[str]:
    """Descramble sampled sectors: guards are pure, bands use only A5/92 and follow the pattern."""
    problems = []
    size = os.path.getsize(path)
    if size != layout.total_sectors * dvd.SECTOR_BYTES:
        return [f"size {size} bytes, expected {layout.total_sectors * dvd.SECTOR_BYTES}"]
    rng = np.random.default_rng(seed)
    q_guard = int(layout.guard, 16)
    with open(path, "rb") as fh:
        for start, end, band in segments(layout):
            for lba in sorted({start, end - 1, *rng.integers(start, end, samples).tolist()}):
                if lba in iso9660.SECTORS:
                    continue
                fh.seek(lba * dvd.SECTOR_BYTES)
                rec = dvd.recorded(np.frombuffer(fh.read(dvd.SECTOR_BYTES), dtype=np.uint8), lba)
                if band is None:
                    if not np.all(rec == q_guard):
                        problems.append(f"guard LBA {lba} is not all {layout.guard}")
                    continue
                if not np.all((rec == 0xA5) | (rec == 0x92)):
                    problems.append(f"band {band['index']} LBA {lba} has bytes other than A5/92")
                    continue
                th = (1 + band["s"]) * theta(lba * SECTOR_BITS + BYTE_BITS, layout.u0, layout.v0)
                f = layout.pattern(th)
                dark = (rec == 0xA5).astype(float)
                # Each byte is A5 with probability f: the A5 share must match the mean of f,
                # and where f varies the bytes must correlate with it (z > 3 over 2048 bytes).
                if abs(dark.mean() - f.mean()) > 5 * 0.5 / math.sqrt(len(f)) or (
                        f.std() > 0.05 and np.corrcoef(f, dark)[0, 1] * math.sqrt(len(f)) < 3):
                    problems.append(f"band {band['index']} LBA {lba}: A5 bytes do not follow the pattern")
    return problems


def describe(layout: CalLayout) -> list[str]:
    hyp = layout.hypotheses()
    b0 = layout.bands[0]
    lines = [f"{len(layout.bands)} bands = {layout.groups} groups x {len(hyp)} hypotheses "
             f"(s = {hyp[0]:+.3%} .. {hyp[-1]:+.3%}, step {layout.s_step:.3%})",
             f"band width {b0['r_end_mm'] - b0['r_start_mm']:.3f} mm, guard {layout.guard_mm} mm of "
             f"{layout.guard}, radius {layout.start_mm}-{layout.end_mm} mm",
             f"nominal geometry r0 {layout.r0_mm} mm, pitch {layout.pitch_um} um, bit {layout.bit_nm} nm",
             f"{layout.total_sectors} sectors ({layout.total_sectors * dvd.SECTOR_BYTES / 1e9:.2f} GB)"]
    return lines
