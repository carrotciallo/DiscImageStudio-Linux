"""Analyse a flatbed scan of a burned spoke disc: spoke rotation delta(r) versus radius.

Pipeline:
  1. Locate the disc: FFT circle search for the 120 mm outer edge on a downsampled
     edge map, then an axis-aligned ellipse fit to the outermost strong edge along
     rays at full resolution (the ellipse absorbs scanner x/y scale mismatch).
  2. Resample rings of constant actual radius around that centre.
  3. Per ring, take the Fourier coefficients at the pattern's k values. Each gives
     the ring's rotation modulo 360/k; k = 3 is unwrapped across radius, then k = 21
     and k = 63 are snapped to it in turn, so the final delta has k = 63 precision.
  4. Detect the grey marker rings as dips in spoke amplitude: actual vs model radius.

Centre and scale errors move a ring's samples by an amount that varies once or
twice per revolution, so they cancel in the ring-average phase to first order; the
result is insensitive to how precisely the disc is located.
"""

from __future__ import annotations

import csv
import json
import math
import os

import numpy as np

from .spokes import SpokeSpec

DISC_RADIUS_MM = 60.0
HOLE_RADIUS_MM = 7.5
N_THETA = 8192
GOOD_SNR = 4.0


# ---------------------------------------------------------------- loading

def load_gray(path: str) -> tuple[np.ndarray, tuple[float, float] | None]:
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(path) as im:
        dpi = im.info.get("dpi")
        if im.mode in ("I;16", "I;16B", "I;16L", "I"):
            a = np.asarray(im, dtype=np.float32) / 65535.0
        else:
            a = np.asarray(im.convert("L"), dtype=np.float32) / 255.0
    if dpi:
        dpi = (float(dpi[0]), float(dpi[1]))
    return a, dpi


def _downsample(a: np.ndarray, f: int) -> np.ndarray:
    h, w = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    return a[:h, :w].reshape(h // f, f, w // f, f).mean(axis=(1, 3))


def _sample(img: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Bilinear sampling; points outside the image read as NaN."""
    h, w = img.shape
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx = x - x0
    fy = y - y0
    inside = (x0 >= 0) & (y0 >= 0) & (x0 < w - 1) & (y0 < h - 1)
    x0c = np.clip(x0, 0, w - 2)
    y0c = np.clip(y0, 0, h - 2)
    v = (img[y0c, x0c] * (1 - fx) * (1 - fy) + img[y0c, x0c + 1] * fx * (1 - fy)
         + img[y0c + 1, x0c] * (1 - fx) * fy + img[y0c + 1, x0c + 1] * fx * fy)
    return np.where(inside, v, np.nan)


# ---------------------------------------------------------------- disc location

def coarse_centre(img: np.ndarray, px_per_mm: float) -> tuple[float, float]:
    f = max(1, int(round(px_per_mm / 4.0)))
    small = _downsample(img, f)
    s = px_per_mm / f
    gy, gx = np.gradient(small)
    edges = np.hypot(gx, gy)
    edges = np.minimum(edges, np.percentile(edges, 99.5))
    radius = DISC_RADIUS_MM * s
    k = int(math.ceil(radius)) + 3
    yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
    ring = (np.abs(np.hypot(xx, yy) - radius) < 1.5).astype(np.float64)
    shape = (edges.shape[0] + ring.shape[0], edges.shape[1] + ring.shape[1])
    acc = np.fft.irfft2(np.fft.rfft2(edges, shape) * np.fft.rfft2(ring, shape), shape)
    acc = acc[k:k + edges.shape[0], k:k + edges.shape[1]]
    cy, cx = np.unravel_index(np.argmax(acc), acc.shape)
    return (cx + 0.5) * f - 0.5, (cy + 0.5) * f - 0.5


def _edge_points(img, cx, cy, px_per_mm, r_mm, window_mm, outermost):
    n_rays = 1440
    th = np.linspace(0, 2 * np.pi, n_rays, endpoint=False)
    step = 0.25
    rr = np.arange((r_mm - window_mm) * px_per_mm, (r_mm + window_mm) * px_per_mm, step)
    x = cx + rr[None, :] * np.cos(th)[:, None]
    y = cy - rr[None, :] * np.sin(th)[:, None]
    prof = _sample(img, x, y)
    kernel = np.ones(5) / 5
    pts = []
    for i in range(n_rays):
        p = prof[i]
        if np.isnan(p).any():
            continue
        g = np.abs(np.gradient(np.convolve(p, kernel, mode="same")))
        g[:4] = g[-4:] = 0
        if g.max() <= 0:
            continue
        strong = np.nonzero(g > 0.35 * g.max())[0]
        j = strong[-1] if outermost else int(np.argmax(g))
        # Walk up to the local maximum of that edge, then parabolic sub-sample.
        while 0 < j < len(g) - 1 and g[j + 1] > g[j]:
            j += 1
        while 0 < j < len(g) - 1 and g[j - 1] > g[j]:
            j -= 1
        if 0 < j < len(g) - 1:
            den = g[j - 1] - 2 * g[j] + g[j + 1]
            off = 0.5 * (g[j - 1] - g[j + 1]) / den if den != 0 else 0.0
        else:
            off = 0.0
        r = rr[0] + (j + off) * step
        pts.append((cx + r * math.cos(th[i]), cy - r * math.sin(th[i])))
    return np.array(pts)


def fit_axis_ellipse(pts: np.ndarray) -> dict:
    """Least-squares x^2 + B y^2 + C x + D y + E = 0, with outlier rejection."""
    keep = np.ones(len(pts), bool)
    for _ in range(4):
        x, y = pts[keep, 0], pts[keep, 1]
        A = np.column_stack([y * y, x, y, np.ones_like(x)])
        sol, *_ = np.linalg.lstsq(A, -x * x, rcond=None)
        B, C, D, E = sol
        cx, cy = -C / 2, -D / (2 * B)
        rhs = cx * cx + B * cy * cy - E
        rx, ry = math.sqrt(rhs), math.sqrt(rhs / B)
        res = np.hypot((pts[:, 0] - cx) / rx, (pts[:, 1] - cy) / ry) - 1
        med = np.median(res[keep])
        mad = np.median(np.abs(res[keep] - med)) * 1.4826
        keep = np.abs(res - med) < max(4 * mad, 2e-4)
    return {"cx": float(cx), "cy": float(cy), "rx": float(rx), "ry": float(ry),
            "used": int(keep.sum()), "total": len(pts),
            "rms_px": float(np.sqrt(np.mean((res[keep] * (rx + ry) / 2) ** 2)))}


def locate_disc(img, px_per_mm, centre=None):
    cx, cy = centre if centre else coarse_centre(img, px_per_mm)
    outer = None
    for window in (4.0, 2.0):
        pts = _edge_points(img, cx, cy, px_per_mm, DISC_RADIUS_MM, window, outermost=True)
        if len(pts) < 100:
            raise RuntimeError("could not locate the disc edge; pass --centre X,Y in pixels")
        outer = fit_axis_ellipse(pts)
        cx, cy = outer["cx"], outer["cy"]
    hole = None
    pts = _edge_points(img, cx, cy, px_per_mm, HOLE_RADIUS_MM, 2.0, outermost=False)
    if len(pts) >= 100:
        hole = fit_axis_ellipse(pts)
    return outer, hole


# ---------------------------------------------------------------- rings

def polar_rings(img, cx, cy, sx, sy, radii_mm, n_theta=N_THETA, sub=3, chunk=40):
    """Ring samples f[ring, theta]. sx, sy are pixels per mm along x and y."""
    th = np.arange(n_theta) * (2 * np.pi / n_theta)
    c, s = np.cos(th), np.sin(th)
    dr = radii_mm[1] - radii_mm[0] if len(radii_mm) > 1 else 0.05
    offs = (np.arange(sub) - (sub - 1) / 2) * dr / sub
    out = np.empty((len(radii_mm), n_theta), dtype=np.float32)
    for i0 in range(0, len(radii_mm), chunk):
        r = radii_mm[i0:i0 + chunk]
        acc = 0
        for o in offs:
            rr = (r + o)[:, None]
            acc = acc + _sample(img, cx + rr * sx * c[None, :], cy - rr * sy * s[None, :])
        out[i0:i0 + len(r)] = acc / sub
    return out, th


def ring_coefficients(f: np.ndarray, ks) -> tuple[np.ndarray, np.ndarray]:
    """Fourier coefficient at each k, and its ratio to the local noise floor.

    The floor is the median magnitude of the bins k+-2..k+-12, so strong content at
    other frequencies (the diffraction rainbow at k = 2, lighting at k = 1) does not
    lower the score the way a ratio to the ring's total variance would.
    """
    valid = ~np.isnan(f).any(axis=1)
    g = np.where(np.isnan(f), 0, f).astype(np.float64)
    spec = np.fft.rfft(g - g.mean(axis=1, keepdims=True), axis=1) / f.shape[1]
    mag = np.abs(spec)
    coef = np.empty((len(f), len(ks)), dtype=complex)
    snr = np.empty((len(f), len(ks)))
    for i, k in enumerate(ks):
        coef[:, i] = spec[:, k]
        nb = [j for j in range(k - 12, k + 13) if abs(j - k) >= 2 and j >= 1]
        floor = np.median(mag[:, nb], axis=1)
        snr[:, i] = mag[:, k] / np.where(floor > 0, floor, np.inf)
    coef[~valid] = np.nan
    snr[~valid] = np.nan
    return coef, snr


def _wrap(a, period):
    return (a + period / 2) % period - period / 2


def unwrap_delta(coef: np.ndarray, good: np.ndarray, spec: SpokeSpec) -> dict:
    """Rotation delta (degrees) per ring, using the k ladder to remove ambiguity."""
    k1, k2, k3 = spec.ks
    psi = np.degrees(np.angle(coef))
    d = [(p - psi[:, i]) / k for i, (k, p) in enumerate(zip(spec.ks, spec.phases_deg))]
    idx = np.nonzero(good)[0]
    out = np.full(len(coef), np.nan)
    cons = np.zeros(len(coef), bool)
    if len(idx) < 3:
        return {"delta": out, "consistent": cons}
    coarse = np.degrees(np.unwrap(np.radians(d[0][idx] * k1))) / k1
    mid = d[1][idx] + np.round((coarse - d[1][idx]) / (360 / k2)) * (360 / k2)
    fine = d[2][idx] + np.round((mid - d[2][idx]) / (360 / k3)) * (360 / k3)
    cons[idx] = (np.abs(mid - coarse) < 0.3 * 360 / k2) & (np.abs(fine - mid) < 0.3 * 360 / k3)
    out[idx] = fine
    return {"delta": out, "consistent": cons}


def detect_markers(radii, amp, spec: SpokeSpec, model_to_actual=lambda r: r):
    found = []
    dr = radii[1] - radii[0]
    for rm in spec.marker_radii_mm:
        guess = model_to_actual(rm)
        win = (radii > guess - 2.0) & (radii < guess + 2.0)
        if win.sum() < 20 or np.isnan(amp[win]).all():
            continue
        r_w, a_w = radii[win], amp[win]
        base = np.nanmedian(a_w)
        depth = 1 - a_w / base
        j = int(np.nanargmax(depth))
        if depth[j] < 0.5:
            continue
        sel = (np.abs(r_w - r_w[j]) < spec.marker_width_mm) & (depth > 0.5 * depth[j])
        w = depth[sel]
        found.append({"model_mm": rm, "actual_mm": round(float((r_w[sel] * w).sum() / w.sum()), 4),
                      "depth": round(float(depth[j]), 3), "width_mm": round(float(sel.sum() * dr), 3)})
    return found


# ---------------------------------------------------------------- top level

def analyse(path: str | None, spec: SpokeSpec, out_dir: str, dpi: float | None = None,
            centre=None, r_min: float = 20.0, r_max: float = 59.0, dr: float = 0.05,
            img=None, log=print) -> dict:
    meta_dpi = None
    if img is None:
        img, meta_dpi = load_gray(path)
    if dpi:
        px_per_mm = dpi / 25.4
    elif meta_dpi:
        px_per_mm = meta_dpi[0] / 25.4
    else:
        px_per_mm = 600 / 25.4
        log("No DPI in file and none given; assuming 600 dpi.")
    outer, hole = locate_disc(img, px_per_mm, centre)
    cx, cy = outer["cx"], outer["cy"]
    # Absolute scale from the scanner's DPI, anisotropy from the edge ellipse.
    sx = px_per_mm
    sy = px_per_mm * outer["ry"] / outer["rx"]
    edge_radius_mm = outer["rx"] / px_per_mm
    log(f"Disc centre ({cx:.2f}, {cy:.2f}) px, outer edge radius {edge_radius_mm:.3f} mm at "
        f"{px_per_mm * 25.4:.1f} dpi, y/x scale {outer['ry'] / outer['rx']:.5f}")

    radii = np.arange(r_min, r_max + dr / 2, dr)
    f, _ = polar_rings(img, cx, cy, sx, sy, radii)
    coef, norm = ring_coefficients(f, spec.ks)

    # Mirror check: psi21 - 7*psi3 equals phi21 - 7*phi3 (90 deg) normally and its
    # negative when the scan is mirrored; dark/light inversion does not change it.
    k1, k2, k3 = spec.ks
    p1, p2, p3 = spec.phases_deg
    good = np.nan_to_num(norm, nan=0.0).min(axis=1) > GOOD_SNR
    if good.sum() < 20:
        raise RuntimeError("fewer than 20 rings show the spoke pattern; check the scan and the spec file")
    psi = np.angle(coef)
    design = math.radians(p2 - (k2 // k1) * p1)
    inv = psi[:, 1] - (k2 // k1) * psi[:, 0]
    score = float(np.mean(np.cos(inv[good] - design)))
    mirrored = score < 0
    if mirrored:
        coef = np.conj(coef)
        psi = np.angle(coef)
        inv = psi[:, 1] - (k2 // k1) * psi[:, 0]
    chirality_err = np.degrees(_wrap(inv - design, 2 * np.pi))
    design2 = math.radians(p3 - (k3 // k2) * p2)
    ladder_err = np.degrees(_wrap(psi[:, 2] - (k3 // k2) * psi[:, 1] - design2, 2 * np.pi))

    res = unwrap_delta(coef, good, spec)
    delta = res["delta"]
    ok = good & res["consistent"]
    first = np.nonzero(ok)[0][0]
    rel = delta - delta[first]

    # Per-ring noise from the second difference of three adjacent rings (robust, and
    # never across a gap, where the curve's own curvature would dominate).
    i = np.nonzero(ok[:-2] & ok[1:-1] & ok[2:])[0]
    d2 = rel[i] - 2 * rel[i + 1] + rel[i + 2]
    noise = float(np.median(np.abs(d2 - np.median(d2))) * 1.4826 / math.sqrt(6)) if len(i) > 5 else float("nan")
    markers = detect_markers(radii, norm[:, 2], spec)

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "phase.csv"), "w", newline="", encoding="utf-8") as fcsv:
        w = csv.writer(fcsv)
        w.writerow(["radius_mm", "delta_deg", "delta_rel_deg", "snr_k%d" % k1, "snr_k%d" % k2,
                    "snr_k%d" % k3, "good", "chirality_err_deg", "ladder_err_deg"])
        for i, r in enumerate(radii):
            w.writerow([f"{r:.3f}", _fmt(delta[i]), _fmt(rel[i]), _fmt(norm[i, 0]), _fmt(norm[i, 1]),
                        _fmt(norm[i, 2]), int(ok[i]), _fmt(chirality_err[i]), _fmt(ladder_err[i])])

    summary = {
        "scan": os.path.abspath(path) if path else None,
        "dpi_used": round(px_per_mm * 25.4, 3),
        "centre_px": [round(cx, 3), round(cy, 3)],
        "outer_edge": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in outer.items()},
        "outer_edge_radius_mm": round(edge_radius_mm, 4),
        "y_over_x_scale": round(outer["ry"] / outer["rx"], 6),
        "hole_edge": None if hole is None else {
            "centre_offset_mm": [round((hole["cx"] - cx) / sx, 4), round((hole["cy"] - cy) / sy, 4)],
            "radius_mm": round(hole["rx"] / sx, 4), "rms_px": round(hole["rms_px"], 3)},
        "mirrored": bool(mirrored),
        "chirality_score": round(score, 4),
        "rings": len(radii), "rings_used": int(ok.sum()),
        "radius_range_used_mm": [round(float(radii[ok][0]), 3), round(float(radii[ok][-1]), 3)],
        "delta_rel_range_deg": [round(float(np.nanmin(rel[ok])), 3), round(float(np.nanmax(rel[ok])), 3)],
        "noise_per_ring_deg": round(noise, 4),
        "ladder_err_median_deg": round(float(np.nanmedian(np.abs(ladder_err[ok]))), 3),
        "markers": markers,
        "sign_convention": "delta > 0: pattern rotated counter-clockwise (y up) relative to the model",
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fj:
        json.dump(summary, fj, indent=2)
    _write_images(img, outer, hole, f, rel, ok, out_dir, px_per_mm, mirrored)
    log(f"Rings used {ok.sum()}/{len(radii)} ({summary['radius_range_used_mm'][0]}-"
        f"{summary['radius_range_used_mm'][1]} mm), mirrored {mirrored}, "
        f"bending {summary['delta_rel_range_deg'][0]}..{summary['delta_rel_range_deg'][1]} deg, "
        f"noise {summary['noise_per_ring_deg']} deg/ring")
    for m in markers:
        log(f"Marker model {m['model_mm']} mm -> actual {m['actual_mm']} mm (depth {m['depth']})")
    summary["_delta_rel"] = rel
    summary["_ok"] = ok
    summary["_radii"] = radii
    return summary


def _fmt(v):
    if v is None:
        return ""
    v = float(v)
    return "" if math.isnan(v) else f"{v:.5f}"


def _write_images(img, outer, hole, f, rel, ok, out_dir, px_per_mm, mirrored):
    from PIL import Image, ImageDraw
    fct = max(1, int(round(px_per_mm / 4)))
    small = _downsample(img, fct)
    lo, hi = np.percentile(small, (1, 99))
    grey = np.clip((small - lo) / (hi - lo + 1e-9) * 255, 0, 255).astype(np.uint8)
    rgb = Image.fromarray(grey).convert("RGB")
    d = ImageDraw.Draw(rgb)
    for e, colour in ((outer, (255, 64, 0)), (hole, (0, 160, 255))):
        if e:
            x, y, rx, ry = e["cx"] / fct, e["cy"] / fct, e["rx"] / fct, e["ry"] / fct
            d.ellipse([x - rx, y - ry, x + rx, y + ry], outline=colour, width=2)
            d.line([x - 6, y, x + 6, y], fill=colour)
            d.line([x, y - 6, x, y + 6], fill=colour)
    rgb.save(os.path.join(out_dir, "detect.png"))

    g = np.where(np.isnan(f), np.nanmean(f), f).astype(np.float64)
    if mirrored:
        g = np.concatenate([g[:, :1], g[:, :0:-1]], axis=1)  # theta -> -theta
    g = g - g.mean(axis=1, keepdims=True)
    g = g / (g.std(axis=1, keepdims=True) + 1e-9)
    n = g.shape[1]
    shift = np.where(ok, np.nan_to_num(rel), 0.0)
    corrected = np.empty_like(g)
    for i in range(len(g)):
        # A pattern rotated by +delta sits at larger theta, so roll it back.
        corrected[i] = np.roll(g[i], -int(round(shift[i] / 360 * n)))
    for arr, name in ((g, "unrolled.png"), (corrected, "unrolled_corrected.png")):
        small = arr.reshape(arr.shape[0], n // 4, 4).mean(axis=2)
        Image.fromarray(np.clip(small * 50 + 128, 0, 255).astype(np.uint8)).save(os.path.join(out_dir, name))
