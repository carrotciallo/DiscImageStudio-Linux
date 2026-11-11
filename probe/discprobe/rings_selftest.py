"""Checks for the texture-ring disc: scrambler, ISO round trip, synthetic scan analysis.

The synthetic scan uses an off-nominal geometry (r0 23.96 mm, pitch x sector length
0.8 % above nominal), lighting that changes with angle and radius, a per-ring scatter
of 0.01 in level, and a texture (66) that looks exactly like A5, as the repository
notes it sometimes does. The analysis has to recover the edges and levels and must not
put both A5 and 66 in the palette.
"""

from __future__ import annotations

import math
import os
import tempfile

import numpy as np

from . import dvd, ringscan
from .rings import RingLayout, verify_iso, write_iso

DPI = 600.0
TRUTH = {"A5": 0.0, "66": 0.0, "64": 0.32, "E4": 0.40, "B9": 0.55, "RND": 0.62, "92": 1.0}
R0_TRUE = 23.96
C_RATIO_TRUE = 1.008
LEVEL_TOL = 0.03


def _scrambler(c):
    print("DVD scrambler")
    c.check(dvd.lfsr_period() == 32767, f"x^15 + x^4 + 1 register period {dvd.lfsr_period()}")
    c.check(dvd.MASKS[0][0] == 0x01 and dvd.MASKS[1][0] == 0x00, "sequences start with the preset low byte")
    c.check(len({m.tobytes() for m in dvd.MASKS}) == 16, "16 distinct preset sequences")
    c.check(dvd.preset_index(0) == 0 and dvd.preset_index(15) == 0 and dvd.preset_index(16) == 1
            and dvd.preset_index(256) == 0, "preset follows PSN bits 7..4 (one per ECC block)")
    p = dvd.payload_for(0xA5, 1234)
    c.check(bool(np.all(dvd.recorded(p, 1234) == 0xA5)), "payload descrambles to the chosen byte")


def _iso(c):
    print("ring ISO round trip")
    lay = RingLayout(groups=2, ring_width_mm=0.01, start_mm=24.02).build()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.iso")
        write_iso(path, lay, log=lambda *_: None)
        problems = verify_iso(path, lay)
        c.check(not problems, f"{lay.total_sectors} sectors written and verified" + (f": {problems[:2]}" if problems else ""))
        ring = lay.rings[3]
        with open(path, "r+b") as f:
            f.seek(ring["lba_start"] * dvd.SECTOR_BYTES + 100)
            b = f.read(1)
            f.seek(-1, 1)
            f.write(bytes([b[0] ^ 0x01]))
        c.check(bool(verify_iso(path, lay)), "a flipped byte is reported")
    full = RingLayout().build()
    c.check(full.total_sectors < 2295104 and all(r["lba_end"] > r["lba_start"] for r in full.rings),
            f"default layout: {len(full.rings)} rings, {full.total_sectors} sectors")


def _actual_radius_of_lba(lay, n, r0_true=R0_TRUE):
    c_nom = (lay.radius_at(1e6) ** 2 - lay.r0_mm ** 2) / 1e6
    return math.sqrt(r0_true ** 2 + c_nom * C_RATIO_TRUE * n)


def synth_scan(lay: RingLayout, seed=3, canvas_mm=(140.0, 135.0), centre_mm=(70.4, 68.2), y_scale=1.002,
               truth=None, r0_true=R0_TRUE, refs=("A5", "92")):
    truth = TRUTH if truth is None else truth
    rng = np.random.default_rng(seed)
    edges = np.array([_actual_radius_of_lba(lay, r["lba_start"], r0_true) for r in lay.rings]
                     + [_actual_radius_of_lba(lay, lay.rings[-1]["lba_end"], r0_true)])
    ring_level = np.array([truth[r["texture"]] + (0 if r["texture"] in refs else rng.normal(0, 0.01))
                           for r in lay.rings])
    px = DPI / 25.4
    w, h = int(canvas_mm[0] * px), int(canvas_mm[1] * px * y_scale)
    out = np.empty((h, w, 3), dtype=np.float32)
    xs = (np.arange(w) + 0.5) / px - centre_mm[0]
    tint = np.array([1.0, 0.95, 1.08], dtype=np.float32)
    for i0 in range(0, h, 256):
        ys = centre_mm[1] - (np.arange(i0, min(h, i0 + 256)) + 0.5) / (px * y_scale)
        x, y = np.meshgrid(xs, ys)
        r = np.hypot(x, y)
        th = np.arctan2(y, x)
        idx = np.searchsorted(edges, r) - 1
        t = np.where((idx >= 0) & (idx < len(ring_level)), ring_level[np.clip(idx, 0, len(ring_level) - 1)],
                     np.where(r < edges[0], 1.0, 0.6))
        base = 0.30 + 0.04 * x / 60 + 0.05 * np.cos(2 * th + 0.4)
        gain = 0.25 * (1 + 0.3 * np.cos(2 * th)) * (1 + 0.004 * (r - 40) + 5e-5 * (r - 40) ** 2)
        data = base + gain * t
        v = np.select([r < 7.5, r < 22.0, r < 23.6, r <= 58.4, r < 59.9, r < 60.05],
                      [0.93, 0.78, 0.55, data, 0.70, 0.30], default=0.95)
        v = v + rng.normal(0, 0.04, v.shape)
        out[i0:i0 + len(ys)] = v[..., None] * tint
    return out


def _scan(c):
    print("synthetic ring scan")
    lay = RingLayout().build()
    img = synth_scan(lay)
    with tempfile.TemporaryDirectory() as tmp:
        s = ringscan.analyse(None, lay, tmp, dpi=DPI, images=[("synthetic", img)], log=lambda *_: None)
    info = s["scans"][0]
    fit = info["radial_fit"]
    c.check(fit is not None and info["edges_used"] >= 15,
            f"ring edges used {info['edges_used']} of {info['edges_expected']}")
    c.check(fit is not None and abs(fit["r0_mm"] - R0_TRUE) < 0.03
            and abs(fit["pitch_x_sector_length_vs_nominal"] - C_RATIO_TRUE) < 0.002,
            f"radial fit r0 {fit and fit['r0_mm']} mm (true {R0_TRUE}), pitch x length "
            f"{fit and fit['pitch_x_sector_length_vs_nominal']} (true {C_RATIO_TRUE}), "
            f"edge rms {fit and fit['edge_residual_rms_mm']} mm")
    lv = s["levels"]["L"]
    worst = max(abs(lv[t] - TRUTH[t]) for t in TRUTH)
    c.check(worst < LEVEL_TOL, f"levels within {worst:.3f} of truth "
                               f"({', '.join(f'{t} {lv[t]:.3f}' for t in s['order_dark_to_bright_L'])})")
    pal = s["palette_L"]
    c.check(not ({"A5", "66"} <= set(pal)) and len(pal) == 6,
            f"palette {' '.join(pal)} (pooled std {s['pooled_std_L']})")
    c.check(set(s["levels"]) == {"L", "R", "G", "B"}, "colour channels analysed")


def run(c) -> None:
    _scrambler(c)
    _iso(c)
    _scan(c)
