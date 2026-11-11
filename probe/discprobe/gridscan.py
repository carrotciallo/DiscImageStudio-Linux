"""Check a burned picture against its design: rotation phi(r) of each thin ring.

The scan and the design are both resampled on thin rings around the disc centre. Per
ring, the angular profiles are band-passed (dropping the lamp shading and the
diffraction rainbow at low angular frequencies) and circularly cross-correlated; the
peak gives the ring's rotation phi(r). A correct geometry gives a flat phi(r) (one
rotation for the whole picture); a calibration error shows as phi drifting with
radius, exactly the bending the picture would show. Centre and x/y-scale errors move
a ring's samples once or twice per turn and cancel in the ring-wide correlation.

The test grid is nearly 90-degree symmetric, so every ring takes the peak closest to
the picture-wide rotation phi0; the mirror test compares the picture-wide peak of
the design with that of its mirror image.
"""

from __future__ import annotations

import csv
import json
import os

import numpy as np

from . import scan
from .imagedisc import CELL_MM, HALF_MM, SIZE

N_THETA = 8192
BAND = (20, 2500)          # angular frequencies kept, cycles per turn
WINDOW_DEG = 8.0           # per-ring peak must lie this close to the picture-wide one


def design_rings(design: np.ndarray, radii, mirrored=False) -> np.ndarray:
    th = np.arange(N_THETA) * (2 * np.pi / N_THETA)
    if mirrored:
        th = -th
    x = radii[:, None] * np.cos(th)[None, :]
    y = radii[:, None] * np.sin(th)[None, :]
    ix = np.clip(np.floor((x + HALF_MM) / CELL_MM).astype(int), 0, SIZE - 1)
    iy = np.clip(np.floor((HALF_MM - y) / CELL_MM).astype(int), 0, SIZE - 1)
    return np.where(design[iy, ix], -1.0, 0.0)  # dark lines as negative


def _band(f: np.ndarray) -> np.ndarray:
    F = np.fft.rfft(np.nan_to_num(f - np.nanmean(f, axis=1, keepdims=True)), axis=1)
    F[:, :BAND[0]] = 0
    F[:, BAND[1]:] = 0
    return F


def _peak(c: np.ndarray, centre_idx: float | None, half_width: int | None):
    n = len(c)
    if centre_idx is None:
        j = int(np.argmax(c))
    else:
        idx = (np.arange(-half_width, half_width + 1) + int(round(centre_idx))) % n
        j = int(idx[np.argmax(c[idx])])
    a, b, d = c[(j - 1) % n], c[j], c[(j + 1) % n]
    den = a - 2 * b + d
    off = 0.5 * (a - d) / den if den != 0 else 0.0
    return (j + off) % n, float(b)


def analyse(path: str, design: np.ndarray, out_dir: str, dpi: float = 600.0, r_min=25.5, r_max=55.5,
            dr=0.1, avoid_circles_mm=5.0, force_mirrored: bool | None = None, log=print) -> dict:
    img, meta = scan.load_gray(path)
    px = (dpi or (meta[0] if meta else 600.0)) / 25.4
    outer, _ = scan.locate_disc(img, px)
    cx, cy = outer["cx"], outer["cy"]
    sx, sy = px, px * outer["ry"] / outer["rx"]
    radii = np.arange(r_min, r_max, dr)
    if avoid_circles_mm:
        # A circle of the design lies along a ring and has no angular structure; skip it.
        d = np.abs((radii + avoid_circles_mm / 2) % avoid_circles_mm - avoid_circles_mm / 2)
        radii = radii[d > 0.35]
    f, _ = scan.polar_rings(img, cx, cy, sx, sy, radii, n_theta=N_THETA, sub=1)
    S = _band(f)
    results = {}
    for mirrored in (False, True):
        D = _band(design_rings(design, radii, mirrored))
        C = S * np.conj(D)
        total = np.fft.irfft(C.sum(axis=0), n=N_THETA)
        j0, h0 = _peak(total, None, None)
        results[mirrored] = (C, j0, h0, float(np.std(total)))
    mirrored = results[True][2] / results[True][3] > results[False][2] / results[False][3]
    if force_mirrored is not None:  # a nearly symmetric design makes the automatic test weak
        mirrored = force_mirrored
    C, j0, h0, sd = results[mirrored]
    half = int(WINDOW_DEG / 360 * N_THETA)
    phi, strength = [], []
    for i in range(len(radii)):
        c = np.fft.irfft(C[i], n=N_THETA)
        j, h = _peak(c, j0, half)
        phi.append(j * 360.0 / N_THETA)
        strength.append(h / (np.std(c) + 1e-12))
    phi = np.unwrap(np.radians(phi)) * 180 / np.pi
    strength = np.array(strength)
    good = strength > 4.0
    rel = phi - np.median(phi[good])
    r_ok, p_ok = radii[good], rel[good]
    lin = np.polyfit(r_ok - 40, p_ok, 1)
    quad = np.polyfit(r_ok - 40, p_ok, 2)
    resid = p_ok - np.polyval(quad, r_ok - 40)
    noise = float(np.median(np.abs(resid)) * 1.4826)

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "phi.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["radius_mm", "phi_rel_deg", "peak_strength", "good"])
        for r, p, s, g in zip(radii, rel, strength, good):
            w.writerow([f"{r:.2f}", f"{p:.4f}", f"{s:.2f}", int(g)])
    summary = {
        "scan": os.path.abspath(path),
        "mirrored_relative_to_design": bool(mirrored),
        "mirror_scores": {"design": round(results[False][2] / results[False][3], 2),
                          "mirrored": round(results[True][2] / results[True][3], 2)},
        "picture_rotation_deg": round(j0 * 360.0 / N_THETA, 3),
        "rings": len(radii), "rings_good": int(good.sum()),
        "phi_range_deg": round(float(p_ok.max() - p_ok.min()), 4),
        "phi_rms_deg": round(float(np.sqrt(np.mean(p_ok ** 2))), 4),
        "trend_deg_per_mm": round(float(lin[0]), 5),
        "trend_over_25_55_mm_deg": round(float(lin[0] * 30), 4),
        "curvature_deg_per_mm2": round(float(quad[0]), 6),
        "noise_per_ring_deg": round(noise, 4),
        "y_over_x_scale": round(outer["ry"] / outer["rx"], 6),
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    log(f"{os.path.basename(path)}: mirrored {mirrored} (scores {summary['mirror_scores']}), "
        f"rings {good.sum()}/{len(radii)}, phi range {summary['phi_range_deg']} deg, rms {summary['phi_rms_deg']} deg, "
        f"trend {summary['trend_over_25_55_mm_deg']} deg over 25-55 mm, noise/ring {summary['noise_per_ring_deg']} deg")
    summary["_radii"], summary["_rel"], summary["_good"] = radii, rel, good
    return summary


def fit_correction(phi_csvs: list[str], out_path: str, degree: int = 4, r_lo: float = 25.5,
                   r_hi: float = 55.5, geometry: str | None = None) -> dict:
    """Fit phi(r) over several grid scans into an angle-correction file for `image --correction`.

    Each scan's curve is zeroed by its own median (its overall rotation is arbitrary),
    rings more than 1 degree off are dropped as mis-peaks, the polynomial in
    x = (r - 40) / 15 is fitted, and points beyond 4 robust sigma are rejected once.
    """
    rs, ps = [], []
    for path in phi_csvs:
        with open(path, encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r["good"] == "1"]
        r = np.array([float(x["radius_mm"]) for x in rows])
        p = np.array([float(x["phi_rel_deg"]) for x in rows])
        p = p - np.median(p)
        keep = np.abs(p) < 1.0
        rs.append(r[keep])
        ps.append(p[keep])
    r, p = np.concatenate(rs), np.concatenate(ps)
    x = (r - 40.0) / 15.0
    coef = np.polyfit(x, p, degree)
    res = p - np.polyval(coef, x)
    keep = np.abs(res) < 4 * np.median(np.abs(res)) * 1.4826
    coef = np.polyfit(x[keep], p[keep], degree)
    res = p[keep] - np.polyval(coef, x[keep])
    out = {"kind": "angle-correction",
           "meaning": "a byte placed at model angle theta appears at theta + phi(r) (degrees, counter-clockwise "
                      "in data-side view); draw with the design sampled at theta + phi(r)",
           "radius_valid_mm": [r_lo, r_hi], "poly_in_x": [float(c) for c in coef], "x": "(r_mm - 40) / 15",
           "source": [os.path.basename(pth) for pth in phi_csvs], "geometry": geometry,
           "points_used": int(keep.sum()), "residual_rms_deg": float(np.sqrt(np.mean(res ** 2)))}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    return out
