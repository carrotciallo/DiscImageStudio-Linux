"""Pre-registered evaluation of the timing re-measurement (see docs/PREREG_remeasure.md).

  python evidence/eval_remeasure.py <new geo summary.json>

Reference ("truth"): the earlier timing fit plus the grid-scan angle correction.
Statistic D: peak-to-peak of (new timing-only angle map - reference) over 25.8-54.4 mm,
after removing one constant rotation. Pass if D <= 3 * sqrt(sigma_new^2 + 0.04^2), where
sigma_new is the new run's own reported 1 sigma (angle_sigma_measured_span_deg) and 0.04
deg is the scan noise of the reference.
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

R_LO, R_HI, SCAN_NOISE, B = 25.8, 54.4, 0.04, 133.3e-6


def main(new_path: str) -> dict:
    with open(os.path.join(HERE, "geo", "random_disc_summary.json"), encoding="utf-8") as f:
        old = json.load(f)["fit"]
    with open(os.path.join(HERE, "angle_correction.json"), encoding="utf-8") as f:
        corr = json.load(f)
    with open(new_path, encoding="utf-8") as f:
        new = json.load(f)["fit"]
    lo, hi = corr["radius_valid_mm"]
    phi = lambda r: np.polyval(corr["poly_in_x"], (np.clip(r, lo, hi) - 40.0) / 15.0)
    u0, v0 = old["u"], old["v"]
    n = np.linspace(math.pi * ((R_LO / B) ** 2 - u0 * u0) / v0, math.pi * ((R_HI / B) ** 2 - u0 * u0) / v0, 4001)
    truth = theta(n, u0, v0) - np.radians(phi(B * np.sqrt(u0 * u0 + v0 * n / math.pi)))
    pp = lambda d: float(np.ptp(np.degrees(d - d.mean())))
    d_new = pp(theta(n, new["u"], new["v"]) - truth)
    d_old = pp(theta(n, u0, v0) - truth)
    sig_new = float(new["angle_sigma_measured_span_deg"])
    sig_old = float(old["angle_sigma_measured_span_deg"])
    comb_new = math.hypot(sig_new, SCAN_NOISE)
    comb_old = math.hypot(sig_old, SCAN_NOISE)
    span = new.get("measured_span_mm", [None, None])
    covered = span[0] is not None and span[0] <= R_LO + 0.5 and span[1] >= R_HI - 0.5
    verdict = ("INCOMPLETE (measured span does not cover 25.8-54.4 mm)" if not covered else
               "STRONG PASS (<= 2 sigma)" if d_new <= 2 * comb_new else
               "PASS (<= 3 sigma)" if d_new <= 3 * comb_new else
               "FAIL (> 3 sigma): a systematic u/v-like offset remains")
    out = {"D_new_deg": d_new, "sigma_new_deg": sig_new, "combined_sigma_new_deg": comb_new,
           "D_new_over_sigma": d_new / comb_new, "threshold_3sigma_deg": 3 * comb_new,
           "D_old_deg": d_old, "D_old_over_sigma": d_old / comb_old,
           "new_vs_old_timing_pp_deg": pp(theta(n, new["u"], new["v"]) - theta(n, u0, v0)),
           "measured_span_mm": span, "chi2_per_dof": new.get("chi2_per_dof"),
           "reference_lba": new.get("reference_lba"), "verdict": verdict}
    for k, val in out.items():
        print(f"{k:28s} {val:.4f}" if isinstance(val, float) else f"{k:28s} {val}")
    return out


if __name__ == "__main__":
    main(sys.argv[1])
