"""Refit a `geo` ladder with a track pitch that varies with radius.

`geo` assumes a constant pitch (u = r0/b, v = p/b). On some media the pitch drifts by ~1e-5
across the disc, which over ~20k turns leaves a smooth S-shaped angle residual of a degree or
two (DiscImageStudio issue #78, CD-R). This refits the measured rungs with

    p(r) = v / (1 + b1 x + b2 x^2 + b3 x^3),   x = (r - rc) / rs

(rc = 40 mm, rs = 15 mm, everything in units of the bit length b) plus a free phase constant,
and compares constant, quadratic and cubic models.

    python tools/geo_polyfit.py results/geo-H-...   [--plot out.png]

--write-correction saves the chosen polynomial as an angle-correction file for `image
--correction`, so a picture drawn with the constant-pitch u, v lands where this fit says:
a byte placed at the model angle -Theta_const(n) really sits at -Theta_poly(n).

A pitch polynomial of order 3 cannot follow a wave of period ~15 mm in radius (seen on CMC CD-R).
--phi-degree N instead fits phi(r) directly with a polynomial of degree N. The table of
leave-one-out errors printed with it shows which degree the rungs themselves support.
"""
import argparse
import csv
import json
import math
import os
import sys

import numpy as np
from scipy.optimize import least_squares

RC_MM, RS_MM = 40.0, 15.0


def model(n, u, v, bs, rc, rs):
    """Spiral angle (rad, up to a constant) and radius (bits) at channel bit n."""
    bs = list(bs) + [0.0] * (3 - len(bs))
    xu = (u - rc) / rs

    def E(x):
        # E0 = int_u^r e dr,  E1 = int_u^r r e dr  with e = b1 x + b2 x^2 + b3 x^3
        p0 = lambda t: bs[0] * t ** 2 / 2 + bs[1] * t ** 3 / 3 + bs[2] * t ** 4 / 4
        p1 = lambda t: bs[0] * t ** 3 / 3 + bs[1] * t ** 4 / 4 + bs[2] * t ** 5 / 5
        e0 = rs * (p0(x) - p0(xu))
        e1 = rs * (rc * (p0(x) - p0(xu)) + rs * (p1(x) - p1(xu)))
        return e0, e1

    r = np.sqrt(u * u + v * n / math.pi)
    for _ in range(4):  # n = (pi/v)(r^2 - u^2) + (2 pi/v) E1(r)
        _, e1 = E((r - rc) / rs)
        r = np.sqrt(u * u + v * n / math.pi - 2 * e1)
    e0, _ = E((r - rc) / rs)
    return 2 * math.pi / v * (r - u + e0), r


def load(run):
    rows = list(csv.DictReader(open(os.path.join(run, "targets.csv"))))
    summ = json.load(open(os.path.join(run, "summary.json")))["fit"]
    n = np.array([float(r["n_bits"]) for r in rows])
    y = np.radians([float(r["unwrapped_deg"]) for r in rows])
    s = np.radians([max(float(r["sigma_deg"]), 0.05) for r in rows])
    return n, y, s, summ


def fit(n, y, s, u0, v0, order, rc, rs):
    def unpack(z):
        return u0 * (1 + z[0] * 1e-5), v0 * (1 + z[1] * 1e-5), z[2:2 + order] * 1e-5, z[-1]

    def res(z):
        u, v, bs, c = unpack(z)
        th, _ = model(n, u, v, bs, rc, rs)
        return (th + c - y) / s

    th0, _ = model(n, u0, v0, [], rc, rs)
    z0 = np.zeros(3 + order)
    z0[-1] = np.mean(y - th0)
    sol = least_squares(res, z0, x_scale=np.r_[1, 1, [1] * order, 1], method="lm")
    u, v, bs, c = unpack(sol.x)
    r = sol.fun
    dof = len(n) - len(z0)
    th, rad = model(n, u, v, bs, rc, rs)
    return dict(u=u, v=v, b=list(bs), chi2=float(r @ r), dof=dof,
                rms_deg=float(np.degrees(np.sqrt(np.mean((th + c - y) ** 2)))),
                resid_deg=np.degrees(th + c - y), r_bits=rad)


def write_correction(path, f, summ, run, order, rc, rs, n):
    bit_nm = summ["bit_nm_assumed"]
    grid = np.linspace(n.min(), n.max(), 400)
    th_const, r_bits = model(grid, summ["u"], summ["v"], [], rc, rs)
    th_poly, _ = model(grid, f["u"], f["v"], f["b"], rc, rs)
    phi = np.degrees(th_const - th_poly)  # picture angles run as -Theta(n)
    phi -= phi.mean()
    r = r_bits * bit_nm * 1e-6
    coef = np.polyfit((r - 40.0) / 15.0, phi, 6)  # highest power first, as load_correction expects
    err = phi - np.polyval(coef, (r - 40.0) / 15.0)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"kind": "angle-correction",
                   "meaning": "a byte placed at model angle theta appears at theta + phi(r) (degrees, "
                              "counter-clockwise in data-side view); draw with the design sampled at theta + phi(r)",
                   "radius_valid_mm": [float(r.min()), float(r.max())], "poly_in_x": coef.tolist(),
                   "x": "(r_mm - 40) / 15", "source": f"tools/geo_polyfit.py {run}", "pitch_model": order,
                   "peak_to_peak_deg": float(phi.max() - phi.min())}, fh, indent=2)
    print(f"wrote {path}: phi peak to peak {phi.max() - phi.min():.3f} deg, polynomial error "
          f"{np.abs(err).max():.4f} deg")


def phi_table(r_mm, phi):
    """Leave-one-out error of a degree-d polynomial phi(x), for choosing d from the rungs alone."""
    x = (r_mm - RC_MM) / RS_MM
    print("\nphi(r) polynomial, fit and leave-one-out rms (deg):")
    for d in range(2, min(13, len(x) - 2)):
        H = np.vander(x, d + 1)
        hat = H @ np.linalg.pinv(H)
        e = phi - hat @ phi
        print(f"  degree {d:2d}  fit {np.sqrt(np.mean(e ** 2)):.3f}  leave-one-out "
              f"{np.sqrt(np.mean((e / (1 - np.diag(hat))) ** 2)):.3f}")


def write_phi_correction(path, r_mm, phi, degree, run):
    """Angle correction fitted straight to the rungs, relative to the u, v in summary.json."""
    x = (r_mm - RC_MM) / RS_MM
    coef = np.polyfit(x, phi, degree)
    lo, hi = float(r_mm.min()), float(r_mm.max())
    curve = np.polyval(coef, (np.linspace(lo, hi, 400) - RC_MM) / RS_MM)
    coef[-1] -= curve.mean()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"kind": "angle-correction",
                   "meaning": "a byte placed at model angle theta appears at theta + phi(r) (degrees, "
                              "counter-clockwise in data-side view); draw with the design sampled at theta + phi(r)",
                   "radius_valid_mm": [lo, hi], "poly_in_x": coef.tolist(),
                   "x": "(r_mm - 40) / 15", "source": f"tools/geo_polyfit.py {run}",
                   "pitch_model": f"phi polynomial, degree {degree}",
                   "peak_to_peak_deg": float(curve.max() - curve.min())}, fh, indent=2)
    print(f"wrote {path}: phi peak to peak {curve.max() - curve.min():.3f} deg, "
          f"fit rms {np.sqrt(np.mean((phi - np.polyval(np.polyfit(x, phi, degree), x)) ** 2)):.3f} deg")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run", help="geo results folder (targets.csv, summary.json)")
    ap.add_argument("--plot", help="write a residual plot here")
    ap.add_argument("--write-correction", help="write an angle-correction file for `image --correction`")
    ap.add_argument("--order", choices=("quadratic", "cubic"), default="quadratic",
                    help="which fit --write-correction uses")
    ap.add_argument("--phi-degree", type=int,
                    help="--write-correction fits phi(r) directly with this polynomial degree")
    a = ap.parse_args()
    n, y, s, summ = load(a.run)
    bit_nm = summ["bit_nm_assumed"]
    mm = lambda bits: bits * bit_nm * 1e-6
    rc, rs = RC_MM / (bit_nm * 1e-6), RS_MM / (bit_nm * 1e-6)
    fits = {}
    for name, order in (("constant", 0), ("quadratic", 2), ("cubic", 3)):
        if len(n) <= 3 + order:
            continue
        f = fits[name] = fit(n, y, s, summ["u"], summ["v"], order, rc, rs)
        print(f"{name:9s} chi2/dof {f['chi2'] / f['dof']:8.2f}  rms {f['rms_deg']:.3f} deg  "
              f"r0 {mm(f['u']):.5f} mm  pitch(40 mm) {mm(f['v']) * 1e3:.6f} um  "
              f"b = {', '.join(f'{x:+.3e}' for x in f['b']) or '-'}")
    c = fits["constant"]
    order = np.argsort(c["r_bits"])
    print("\nconstant-pitch residual vs radius:")
    for i in order:
        print(f"  {mm(c['r_bits'][i]):7.3f} mm  {c['resid_deg'][i]:+7.3f} deg  (+/- {np.degrees(s[i]):.3f})")
    th, rad = model(n, summ["u"], summ["v"], [], rc, rs)
    phi = np.degrees(th - y)
    phi -= phi.mean()
    phi_table(mm(rad), phi)
    if a.write_correction and a.phi_degree:
        write_phi_correction(a.write_correction, mm(rad), phi, a.phi_degree, a.run)
    elif a.write_correction:
        write_correction(a.write_correction, fits[a.order], summ, a.run, a.order, rc, rs, n)
    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(7, 3.5))
        for name, f in fits.items():
            o = np.argsort(f["r_bits"])
            ax.errorbar(mm(f["r_bits"][o]), f["resid_deg"][o], yerr=np.degrees(s[o]), fmt="o-", ms=3,
                        capsize=2, label=f"{name} (rms {f['rms_deg']:.2f} deg)")
        ax.axhline(0, color="k", lw=0.5)
        ax.set_xlabel("radius (mm)")
        ax.set_ylabel("model - measured (deg)")
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(a.plot, dpi=130)
        print(f"\nplot: {a.plot}")


if __name__ == "__main__":
    sys.exit(main())
