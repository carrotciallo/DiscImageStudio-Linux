"""End-to-end test of the multi-hypothesis calibration disc.

A disc with true geometry r0 23.95 mm, pitch 0.7365 um, bit 133.6 nm (local rate
0.36-0.43 % above nominal, varying with radius) is rendered as a 600 dpi scan: each
pixel shows the mean of the band's pattern at the angle its bytes were drawn for,
averaged over three radial sub-samples like a scanner pixel would. Lighting gradient,
k = 2 rainbow, noise, scanner y/x scale, rotation, and optionally a mirrored and
dark/light-inverted image. Up to a common rotation, the bracketing disc must get the
angle of every byte across 24-58 mm right to within 10 degrees and report an honest
uncertainty; the refinement disc drawn with that fit must get it within 0.5 degrees.
"""

from __future__ import annotations

import math
import os
import tempfile

import numpy as np

from . import calib, calscan
from .calib import CalLayout, SECTOR_BITS, theta

DPI = 600.0
TRUE_R0, TRUE_P, TRUE_B = 23.95, 0.7365e-3, 133.6e-6
ROUND1_TOL_DEG = 10.0  # the bracketing disc only has to get the refinement disc in range
ROUND2_TOL_DEG = 0.5


def true_uv():
    return TRUE_R0 / TRUE_B, TRUE_P / TRUE_B


def synth_scan(lay: CalLayout, mirrored=False, inverted=False, seed=4, canvas_mm=(140.0, 135.0),
               centre_mm=(69.7, 67.4), y_scale=1.0015, rot_deg=-52.0):
    rng = np.random.default_rng(seed)
    ut, vt = true_uv()
    band_of = {b["lba_start"]: b for b in lay.bands}
    starts = np.array(sorted(band_of))
    ends = np.array([band_of[s]["lba_end"] for s in starts])
    scales = np.array([1 + band_of[s]["s"] for s in starts])
    px = DPI / 25.4
    w, h = int(canvas_mm[0] * px), int(canvas_mm[1] * px * y_scale)
    out = np.empty((h, w), dtype=np.float32)
    xs = (np.arange(w) + 0.5) / px - centre_mm[0]
    for i0 in range(0, h, 128):
        ys = centre_mm[1] - (np.arange(i0, min(h, i0 + 128)) + 0.5) / (px * y_scale)
        x, y = np.meshgrid(xs, ys)
        r = np.hypot(x, y)
        th_view = np.arctan2(y, x)
        sigma = -1.0 if mirrored else 1.0
        acc = np.zeros_like(r)
        in_band = np.zeros(r.shape, bool)
        for dr in (-0.014, 0.0, 0.014):
            rr = np.maximum(r + dr, TRUE_R0)
            n = math.pi * ((rr / TRUE_B) ** 2 - ut * ut) / vt
            lba = n / SECTOR_BITS
            j = np.clip(np.searchsorted(starts, lba, side="right") - 1, 0, len(starts) - 1)
            inside = (lba >= starts[j]) & (lba < ends[j])
            delta = theta(n, ut, vt) - scales[j] * theta(n, lay.u0, lay.v0)
            drawn = sigma * th_view - math.radians(rot_deg) - delta
            fval = lay.pattern(drawn)
            acc += np.where(inside, fval, 0.0) / 3
            in_band |= inside
        written = (r >= lay.start_mm - 1.0) & (r < math.sqrt(TRUE_R0 ** 2 + vt * TRUE_B ** 2 * lay.total_sectors * SECTOR_BITS / math.pi))
        dark = np.where(in_band, acc, 0.0)  # guards and filler are 92: never dark
        t = 1 - dark if not inverted else dark
        base = 0.30 + 0.04 * x / 60 + 0.06 * np.cos(2 * th_view + 0.4)
        gain = 0.22 * (1 + 0.25 * np.cos(2 * th_view))
        data = np.where(written | in_band, base + gain * t, 0.42)
        v = np.select([r < 7.5, r < 22.0, r < 23.6, r <= 58.4, r < 59.9, r < 60.05],
                      [0.93, 0.78, 0.55, data, 0.70, 0.30], default=0.95)
        out[i0:i0 + len(ys)] = v + rng.normal(0, 0.04, v.shape)
    return out


def _case(c, lay, mirrored, inverted, tol, label="bracketing disc"):
    print(f"synthetic scan of the {label}: mirrored={mirrored}, inverted={inverted}")
    img = synth_scan(lay, mirrored=mirrored, inverted=inverted, seed=4 + 2 * mirrored + inverted)
    with tempfile.TemporaryDirectory() as tmp:
        s = calscan.analyse(None, lay, tmp, dpi=DPI, img=img, log=lambda *_: None)
    c.check(s["mirrored"] == mirrored, f"mirror detected as {s['mirrored']} (score {s['chirality_score']})")
    a_true = TRUE_R0 ** 2
    c_true = TRUE_P * TRUE_B * SECTOR_BITS / math.pi
    worst = max(abs(math.sqrt(s["_geo"]["a"] + s["_geo"]["c"] * n) - math.sqrt(a_true + c_true * n))
                for n in (0, lay.total_sectors))
    c.check(worst < 0.01, f"guard edges {s['edges_used']}/{s['edges_expected']}, radius map error {worst * 1000:.1f} um")
    bands = s["_bands"]
    c.check(len(bands) >= 3, f"readable bands {len(bands)}: "
            + ", ".join(f"{b['s']:+.1%}@{b['r_in_mm']:.1f}mm" for b in bands))
    fit = s["fit"]
    c.check(fit is not None, "two-parameter fit produced")
    if not fit:
        return
    joined = [k for k, v in s["_status"].items() if isinstance(v, tuple)]
    coarse = _angle_error(fit["coarse_u"], fit["coarse_v"])
    fine = _angle_error(fit["u"], fit["v"])
    sig = fit.get("angle_sigma_deg", float("nan"))
    print(f"  info  coarse fit angle error over 24-58 mm: {coarse:.1f} deg")
    c.check(fine < tol and fine < 3 * sig + 0.3,
            f"fine fit with {len(joined)} bands: angle error over 24-58 mm {fine:.3f} deg "
            f"(reported 1 sigma {sig:.3f}; nominal layout was off {fit['nominal_error_deg']:.0f} deg)")
    return fit


def _angle_error(u, v) -> float:
    ut, vt = true_uv()
    nn = np.linspace(0, math.pi * ((58.0 / TRUE_B) ** 2 - ut * ut) / vt, 600)
    e = np.degrees(theta(nn, u, v) - theta(nn, ut, vt))
    return float(e.max() - e.min())


def run(c) -> None:
    lay = CalLayout().build()
    print("calibration disc layout")
    c.check(lay.total_sectors < 2295104, f"{len(lay.bands)} bands, {lay.total_sectors} sectors")
    with tempfile.TemporaryDirectory() as tmp:
        tiny = CalLayout(s_range=0.002, s_step=0.002, groups=2, start_mm=24.2, end_mm=26.6, guard_mm=0.05).build()
        path = os.path.join(tmp, "c.iso")
        calib.write_iso(path, tiny, log=lambda *_: None)
        problems = calib.verify_iso(path, tiny)
        c.check(not problems, f"small calibration ISO ({tiny.total_sectors} sectors) verified"
                + (f": {problems[:2]}" if problems else ""))
    fit = _case(c, lay, mirrored=False, inverted=False, tol=ROUND1_TOL_DEG)
    _case(c, lay, mirrored=True, inverted=True, tol=ROUND1_TOL_DEG)
    if fit:
        lay2 = calib.refine_layout(fit)
        _case(c, lay2, mirrored=True, inverted=False, tol=ROUND2_TOL_DEG, label="refinement disc")
