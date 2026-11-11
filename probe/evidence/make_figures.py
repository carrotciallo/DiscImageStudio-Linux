"""Regenerate the evidence figures from the data in this folder (numpy + Pillow only).

  python evidence/make_figures.py
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from discprobe.calib import theta  # noqa: E402

W, H, PAD_L, PAD_R, PAD_T, PAD_B = 1200, 700, 110, 40, 70, 80
COLOURS = [(31, 119, 180), (214, 39, 40), (44, 160, 44), (255, 127, 14), (148, 103, 189), (140, 86, 75)]


def font(size):
    try:
        return ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


class Plot:
    def __init__(self, title, xlabel, ylabel, xlim, ylim):
        self.im = Image.new("RGB", (W, H), "white")
        self.d = ImageDraw.Draw(self.im)
        self.xlim, self.ylim = xlim, ylim
        d, f = self.d, font(18)
        d.text((W / 2, 24), title, fill="black", font=font(24), anchor="mm")
        d.rectangle([PAD_L, PAD_T, W - PAD_R, H - PAD_B], outline="black")
        for xv in np.arange(math.ceil(xlim[0] / 5) * 5, xlim[1] + 1e-9, 5):
            x = self.px(xv, ylim[0])[0]
            d.line([x, H - PAD_B, x, H - PAD_B + 6], fill="black")
            d.text((x, H - PAD_B + 20), f"{xv:g}", fill="black", font=f, anchor="mm")
        for yv in np.linspace(*ylim, 7):
            y = self.px(xlim[0], yv)[1]
            d.line([PAD_L - 6, y, PAD_L, y], fill="black")
            d.line([PAD_L, y, W - PAD_R, y], fill=(232, 232, 232))
            d.text((PAD_L - 10, y), f"{yv:+.2f}", fill="black", font=f, anchor="rm")
        d.text((W / 2, H - 25), xlabel, fill="black", font=f, anchor="mm")
        d.text((PAD_L, PAD_T - 14), ylabel, fill="black", font=f, anchor="lm")
        self.legend_y = PAD_T + 12

    def px(self, x, y):
        (x0, x1), (y0, y1) = self.xlim, self.ylim
        return (PAD_L + (x - x0) / (x1 - x0) * (W - PAD_L - PAD_R),
                H - PAD_B - (y - y0) / (y1 - y0) * (H - PAD_T - PAD_B))

    def points(self, xs, ys, colour, r=2):
        for x, y in zip(xs, ys):
            if np.isfinite(y):
                px, py = self.px(x, y)
                self.d.ellipse([px - r, py - r, px + r, py + r], fill=colour)

    def line(self, xs, ys, colour, width=3):
        pts = [self.px(x, y) for x, y in zip(xs, ys) if np.isfinite(y)]
        if len(pts) > 1:
            self.d.line(pts, fill=colour, width=width)

    def legend(self, text, colour):
        x = W - PAD_R - 480
        self.d.rectangle([x, self.legend_y - 6, x + 24, self.legend_y + 6], fill=colour)
        self.d.text((x + 34, self.legend_y), text, fill="black", font=font(17), anchor="lm")
        self.legend_y += 26

    def save(self, name):
        self.im.save(os.path.join(HERE, "figures", name))


def read_phi(path):
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["good"] == "1"]
    r = np.array([float(x["radius_mm"]) for x in rows])
    p = np.array([float(x["phi_rel_deg"]) for x in rows])
    keep = np.abs(p - np.median(p)) < 1.0
    return r[keep], p[keep]


def binned(curves, lo=25, hi=56, step=2.0):
    edges = np.arange(lo, hi + step, step)
    mids, meds = [], []
    for a in edges[:-1]:
        vals = []
        for r, p in curves:
            sel = (r >= a) & (r < a + step)
            if sel.sum() >= 3:
                vals.append(np.median(p[sel]))
        mids.append(a + step / 2)
        meds.append(np.median(vals) if vals else np.nan)
    meds = np.array(meds)
    return np.array(mids), meds - np.nanmedian(meds)


def fig_bending():
    g1 = [read_phi(os.path.join(HERE, "gridscan", f"grid1_scan{i}.phi.csv")) for i in range(1, 7)]
    g2 = [read_phi(os.path.join(HERE, "gridscan", f"grid2_scan{i}.phi.csv")) for i in range(1, 5)]
    g3 = [read_phi(os.path.join(HERE, "gridscan", f"grid3_scan{i}.phi.csv")) for i in range(1, 9)]
    pl = Plot("Grid test discs: picture rotation vs radius (flat = undistorted)",
              "radius (mm)", "rotation (deg)", (25, 56), (-0.3, 0.3))
    for r, p in g1:
        pl.points(r, p - np.median(p), (170, 200, 235), 2)
    for r, p in g2:
        pl.points(r, p - np.median(p), (245, 185, 185), 2)
    for r, p in g3:
        pl.points(r, p - np.median(p), (180, 225, 180), 2)
    m1, b1 = binned(g1)
    m2, b2 = binned(g2)
    m3, b3 = binned(g3)
    pl.line(m1, b1, COLOURS[0])
    pl.line(m2, b2, COLOURS[1])
    pl.line(m3, b3, COLOURS[2])
    pl.legend(f"grid 1, first timing run: {np.nanmax(b1) - np.nanmin(b1):.2f} deg p-p (6 scans)", COLOURS[0])
    pl.legend(f"grid 2, + scan correction: {np.nanmax(b2) - np.nanmin(b2):.2f} deg p-p (4 scans)", COLOURS[1])
    pl.legend(f"grid 3, re-measured timing only: {np.nanmax(b3) - np.nanmin(b3):.2f} deg p-p (8 scans)", COLOURS[2])
    pl.save("bending_before_after.png")


def fig_ladder():
    pl = Plot("Timing ladder: residual of every rung after the fit",
              "radius (mm)", "residual (deg)", (25, 56), (-0.5, 0.5))
    for k, (name, label) in enumerate((("random_disc", "random-data disc, 26 rungs"),
                                       ("rings_disc", "texture-ring disc, 21 rungs"))):
        with open(os.path.join(HERE, "geo", f"{name}_summary.json"), encoding="utf-8") as f:
            fit = json.load(f)["fit"]
        with open(os.path.join(HERE, "geo", f"{name}_targets.csv"), encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        b = fit["bit_nm_assumed"] * 1e-6
        r = [b * math.sqrt(fit["u"] ** 2 + fit["v"] * float(x["n_bits"]) / math.pi) for x in rows]
        res = [float(x["residual_deg"]) for x in rows]
        pl.points(r, res, COLOURS[k], 5)
        pl.legend(f"{label}: rms {np.sqrt(np.mean(np.square(res))):.3f} deg", COLOURS[k])
    pl.save("ladder_residuals.png")


def fig_preset():
    """Angle difference between the DiscImageStudio preset ritek-dvd-r-e-series (an
    independent photo calibration) and our timing model, without and with the angle
    correction measured on grid 1."""
    ri, ro, N, b_nm = 24.063109184084034, 58.23373375457525, 2298496, 133.3
    c1, c2, c3 = -3.2229430281730407e-06, 1.0507210681810583e-05, -8.562064227346657e-06
    b = b_nm * 1e-6
    L = N * 38688 * b
    r = np.linspace(ri, ro, 200001)
    x = (r - ri) / (ro - ri)
    shape = 1 + c1 * x + c2 * x ** 2 + c3 * x ** 3
    integ = lambda y: np.concatenate([[0], np.cumsum((y[1:] + y[:-1]) / 2 * np.diff(r))])
    lo, hi = 0.7e-3, 0.8e-3
    for _ in range(100):
        p0 = (lo + hi) / 2
        s = integ(np.sqrt(1 + (2 * np.pi * r / (p0 * shape)) ** 2))
        lo, hi = (p0, hi) if s[-1] > L else (lo, p0)
    th_dis = integ(2 * np.pi / (p0 * shape))
    n = s / b
    with open(os.path.join(HERE, "geo", "random_disc_summary.json"), encoding="utf-8") as f:
        fit = json.load(f)["fit"]
    with open(os.path.join(HERE, "angle_correction.json"), encoding="utf-8") as f:
        corr = json.load(f)
    clo, chi = corr["radius_valid_mm"]
    phi = lambda rr: np.polyval(corr["poly_in_x"], (np.clip(rr, clo, chi) - 40.0) / 15.0)
    th_ours = theta(n, fit["u"], fit["v"])
    r_ours = b * np.sqrt(fit["u"] ** 2 + fit["v"] * n / math.pi)
    sel = (r >= 25.8) & (r <= 54.4)
    d1 = np.degrees(th_dis - th_ours)[sel]
    d2 = np.degrees(th_dis - (th_ours - np.radians(phi(r_ours))))[sel]
    d1 -= d1.mean()
    d2 -= d2.mean()
    pl = Plot("DiscImageStudio preset 'ritek-dvd-r-e-series' minus our measurement",
              "radius (mm)", "angle difference (deg)", (25, 56), (-0.3, 0.3))
    rs = r[sel][::500]
    pl.line(rs, d1[::500], COLOURS[0])
    pl.line(rs, d2[::500], COLOURS[1])
    pl.legend(f"vs timing model: {d1.max() - d1.min():.3f} deg p-p", COLOURS[0])
    pl.legend(f"vs timing + angle correction: {d2.max() - d2.min():.3f} deg p-p", COLOURS[1])
    pl.save("preset_comparison.png")


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "figures"), exist_ok=True)
    fig_bending()
    fig_ladder()
    fig_preset()
    print("figures written to", os.path.join(HERE, "figures"))
