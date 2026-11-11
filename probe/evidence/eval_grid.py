"""Grid-disc bending statistics (registered criteria for grid disc 3, see docs/PREREG_remeasure.md).

  python evidence/eval_grid.py <phi.csv> [<phi.csv> ...]

Aggregated curve exactly as in make_figures.py: per scan, rings with good peaks and
within 1 deg of the scan median, 2 mm radial bins (a bin needs >= 3 rings), median per
scan, median across scans, constant rotation removed. Reported: peak-to-peak, RMS, and
the U component, i.e. the quadratic coefficient a of a fit a x^2 + b x + c with
x = (r_bin - 40) / 14.3 (x spans about [-1, 1] over 25.8-54.4 mm), so |a| is the
peak-to-peak size of the quadratic part across the range.
"""

from __future__ import annotations

import csv
import sys

import numpy as np

# Calibrated on the existing discs before grid 3 was burned: grid 2 (near-true geometry)
# must pass and grid 1 (old timing only) must fail. A U limit of 0.05 deg would have
# failed grid 2 itself (0.057 deg), so it is 0.10 deg; grid 1 measures 0.231 deg.
LIMITS = {"rms": 0.06, "pp": 0.20, "u": 0.10}


def read_phi(path):
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["good"] == "1"]
    r = np.array([float(x["radius_mm"]) for x in rows])
    p = np.array([float(x["phi_rel_deg"]) for x in rows])
    keep = np.abs(p - np.median(p)) < 1.0
    return r[keep], p[keep]


def aggregate(curves, lo=25, hi=56, step=2.0):
    mids, meds = [], []
    for a in np.arange(lo, hi, step):
        vals = [np.median(p[(r >= a) & (r < a + step)]) for r, p in curves if ((r >= a) & (r < a + step)).sum() >= 3]
        if vals:
            mids.append(a + step / 2)
            meds.append(np.median(vals))
    meds = np.array(meds)
    return np.array(mids), meds - np.median(meds)


def evaluate(paths):
    mids, curve = aggregate([read_phi(p) for p in paths])
    centred = curve - curve.mean()
    x = (mids - 40.0) / 14.3
    a, b, c = np.polyfit(x, curve, 2)
    st = {"bins": len(mids), "pp": float(np.ptp(curve)), "rms": float(np.sqrt(np.mean(centred ** 2))),
          "u": float(abs(a))}
    st["pass"] = st["rms"] <= LIMITS["rms"] and st["pp"] <= LIMITS["pp"] and st["u"] <= LIMITS["u"]
    return st


if __name__ == "__main__":
    s = evaluate(sys.argv[1:])
    print(f"bins {s['bins']}, p-p {s['pp']:.3f} deg (<= {LIMITS['pp']}), rms {s['rms']:.3f} deg (<= {LIMITS['rms']}), "
          f"U component {s['u']:.3f} deg (<= {LIMITS['u']}) -> {'PASS' if s['pass'] else 'FAIL'}")
