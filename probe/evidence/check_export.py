"""Independent check of the exported DiscImageStudio preset, with exact arc length.

Integrates each cubic-pitch preset the way DiscImageStudio defines it (arc length
sqrt(1 + (2 pi r / p)^2), p0 from the total track length) without using
discprobe.disexport, and compares angle along the track with our corrected timing map.
An overall rotation is removed before each comparison.

  python evidence/check_export.py
"""

from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from discprobe.calib import theta  # noqa: E402

B_NM, N, R_LO, R_HI = 133.3, 2298496, 25.8, 54.4
COMMUNITY = {"innerRadiusMm": 24.063109184084034, "outerRadiusMm": 58.23373375457525,
             "pitchLinear": -3.2229430281730407e-06, "pitchQuadratic": 1.0507210681810583e-05,
             "pitchCubic": -8.562064227346657e-06}   # DiscImageStudio ritek-dvd-r-e-series (#45 / #53)


def exact_map(p):
    """(n, theta) of a preset on a fine radius grid, exact arc length."""
    ri, ro = p["innerRadiusMm"], p["outerRadiusMm"]
    r = np.linspace(ri, ro, 400001)
    x = (r - ri) / (ro - ri)
    shape = 1 + p["pitchLinear"] * x + p["pitchQuadratic"] * x ** 2 + p["pitchCubic"] * x ** 3
    cum = lambda y: np.concatenate([[0.0], np.cumsum((y[1:] + y[:-1]) / 2 * np.diff(r))])
    b = B_NM * 1e-6
    length = N * 38688 * b
    lo, hi = 0.7e-3, 0.8e-3
    for _ in range(100):
        p0 = (lo + hi) / 2
        s = cum(np.sqrt(1 + (2 * np.pi * r / (p0 * shape)) ** 2))
        lo, hi = (p0, hi) if s[-1] > length else (lo, p0)
    return s / b, cum(2 * np.pi / (p0 * shape))


def stats(d):
    d = np.degrees(d - d.mean())
    return f"max |diff| {np.max(np.abs(d)):.4f} deg, rms {np.sqrt(np.mean(d * d)):.4f} deg, p-p {d.max() - d.min():.4f} deg"


def main():
    with open(os.path.join(HERE, "geo", "random_disc_summary.json"), encoding="utf-8") as f:
        geo = json.load(f)["fit"]
    with open(os.path.join(HERE, "angle_correction.json"), encoding="utf-8") as f:
        corr = json.load(f)
    with open(os.path.join(HERE, "dis_preset_ritekf1.json"), encoding="utf-8") as f:
        exported = json.load(f)["preset"]
    lo, hi = corr["radius_valid_mm"]
    phi = lambda r: np.polyval(corr["poly_in_x"], (np.clip(r, lo, hi) - 40.0) / 15.0)
    b = B_NM * 1e-6
    u, v = geo["u"], geo["v"]
    n_eval = np.linspace(math.pi * ((R_LO / b) ** 2 - u * u) / v, math.pi * ((R_HI / b) ** 2 - u * u) / v, 20001)
    ours = theta(n_eval, u, v) - np.radians(phi(b * np.sqrt(u * u + v * n_eval / math.pi)))
    n_e, th_e = exact_map(exported)
    n_c, th_c = exact_map(COMMUNITY)
    exp_at = np.interp(n_eval, n_e, th_e)
    com_at = np.interp(n_eval, n_c, th_c)
    print(f"Evaluated over {R_LO}-{R_HI} mm (our model radius), {len(n_eval)} positions, overall rotation removed")
    print("exported preset  vs our corrected map :", stats(exp_at - ours))
    print("community preset vs our corrected map :", stats(com_at - ours))
    print("community preset vs exported preset   :", stats(com_at - exp_at))
    print("community preset vs our timing map    :", stats(com_at - theta(n_eval, u, v)))


if __name__ == "__main__":
    main()
