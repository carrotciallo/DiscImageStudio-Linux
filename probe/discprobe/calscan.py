"""Fit the disc geometry from a flatbed scan of the multi-hypothesis calibration disc.

Steps:
  1. Locate the disc, resample thin rings (0.025 mm), and fit r^2 = a + c * LBA through
     the guard-ring edges so every ring has a channel-bit position n.
  2. Per ring, the phase of the 3-fold spoke term gives the rotation delta = Theta(n) -
     Theta_j(n) of the band's pattern (mod 120 deg). The 9-fold term only serves to
     detect a mirrored scan.
  3. Coarse: a band is readable when most of its rings carry the spokes and delta
     unwraps smoothly. A straight-line fit of delta against n gives the true local
     rate dTheta/dn = 1/S(n), and 1/rate^2 = u^2 + (v/pi) n is linear in u^2 and v, so
     two or more readable bands at different radii give u and v directly.
  4. Fine: the deltas of all readable bands share one unknown rotation c. Starting from
     the band with the cleanest data, bands are added nearest first, and u, v, c are
     refined by Gauss-Newton on the wrapped phase residuals. A band whose residuals
     stay large after joining is set aside as inconsistent.
The result is u = r0/b and v = p/b, i.e. the angle of every byte up to a rotation.
"""

from __future__ import annotations

import csv
import json
import math
import os

import numpy as np

from . import scan
from .calib import SECTOR_BITS, CalLayout, rate, theta
from .ringscan import fit_edges

DR_MM = 0.025
N_THETA = 4096
GOOD_SNR = 4.0
EDGE_MARGIN_MM = 0.05
MIN_RINGS = 6
MIN_GOOD_FRACTION = 0.7
MAX_STEP_RAD = 2.0          # largest allowed change of 3*delta between adjacent rings
MAX_BAND_RMS_DEG = 5.0      # straight-line residual for a readable band
MAX_JOIN_RMS_DEG = 6.0      # residual of a band after it joins the global fit
RADIUS_SIGMA_MM = 0.01      # prior on the scan's local radius error, per band
PERIOD = 2 * math.pi / 3


def _wrap(x, period=PERIOD):
    return (x + period / 2) % period - period / 2


def _dtheta(n, u, v):
    """Partial derivatives of theta(n) with respect to u and v."""
    s = np.sqrt(u * u + v * n / math.pi)
    return -2 * n / (s * (s + u)), -n * n / (math.pi * s * (s + u) ** 2)


def _model(n, s_j, u, v, layout):
    return theta(n, u, v) - (1 + s_j) * theta(n, layout.u0, layout.v0)


def coarse_fit(bands: list[dict]):
    """u, v from the measured local rates; None if the bands do not span enough radius."""
    if len(bands) < 2:
        return None
    n = np.array([b["n_mid"] for b in bands])
    rt = np.array([b["rate"] for b in bands])
    sr = np.array([b["rate_sigma"] for b in bands])
    if n.max() - n.min() < 0.15 * n.max():
        return None
    y = 1 / rt ** 2
    sy = np.maximum(2 * sr / rt ** 3, 1e-12 * y)
    A = np.column_stack([np.ones_like(n), n / math.pi]) / sy[:, None]
    (u2, v), *_ = np.linalg.lstsq(A, y / sy, rcond=None)
    if u2 <= 0 or v <= 0:
        return None
    return math.sqrt(u2), float(v)


def _gauss_newton(data, u, v, c, layout, sigma_d, fit_uv=True, iters=12):
    """Weighted Gauss-Newton on the wrapped phase residuals.

    Parameters: u, v, the common rotation c, and per band a shift dn of its bit
    positions. The shift stands for the error of the scan's radius-to-LBA map; it has a
    Gaussian prior of sigma_n bits. A band whose hypothesis matches the true local rate
    is insensitive to it (its delta hardly changes with n), so well-matched bands anchor
    the common phase while poorly matched ones mainly contribute their slopes.
    """
    m = len(data)
    for _ in range(iters):
        rs, Js = [], []
        for j, d in enumerate(data):
            n = d["n"] + d["dn"]
            rs.append(_wrap(d["delta"] - _model(n, d["s"], u, v, layout) - c) / sigma_d)
            du, dv = _dtheta(n, u, v)
            J = np.zeros((len(n), 3 + m))
            J[:, 0], J[:, 1], J[:, 2] = du, dv, 1.0
            J[:, 3 + j] = rate(n, u, v) - (1 + d["s"]) * rate(n, layout.u0, layout.v0)
            Js.append(J / sigma_d)
        for j, d in enumerate(data):
            row = np.zeros((1, 3 + m))
            row[0, 3 + j] = 1.0 / d["sigma_n"]
            Js.append(row)
            rs.append(np.array([-d["dn"] / d["sigma_n"]]))
        J = np.concatenate(Js)
        r = np.concatenate(rs)
        cols = list(range(3 + m)) if fit_uv else [2] + list(range(3, 3 + m))
        Jc = J[:, cols]
        scale = np.sqrt((Jc ** 2).sum(axis=0))
        step, *_ = np.linalg.lstsq(Jc / scale, r, rcond=None)
        step = step / scale
        full = np.zeros(3 + m)
        full[cols] = step
        u, v, c = u + full[0], v + full[1], c + full[2]
        for j, d in enumerate(data):
            d["dn"] += full[3 + j]
        if np.all(np.abs(step * scale) < 1e-7):
            break
    res = [_wrap(d["delta"] - _model(d["n"] + d["dn"], d["s"], u, v, layout) - c) for d in data]
    return u, v, c, res, J


def _band_data(b, layout: CalLayout) -> dict:
    r_mm = layout.bit_nm * 1e-6 * math.sqrt(layout.u0 ** 2 + layout.v0 * b["n_mid"] / math.pi)
    bits_per_mm = 2 * math.pi * r_mm / (layout.v0 * (layout.bit_nm * 1e-6) ** 2)
    return {"n": b["n"], "delta": b["delta"], "s": b["s"], "index": b["index"], "dn": 0.0,
            "sigma_n": RADIUS_SIGMA_MM * bits_per_mm}


def fine_fit(bands: list[dict], u, v, layout: CalLayout):
    """Phase-linked fit; returns (u, v, c, covariance of u, v or None, per-band status dict)."""
    status = {}
    sigma_d = max(math.radians(float(np.median([b["rms_deg"] for b in bands]))), math.radians(0.1))
    order = sorted(bands, key=lambda b: (b["rms_deg"], -len(b["n"])))
    ref = order[0]
    data = [_band_data(ref, layout)]
    c = float(np.angle(np.mean(np.exp(3j * (ref["delta"] - _model(ref["n"], ref["s"], u, v, layout))))) / 3)
    u, v, c, _, _ = _gauss_newton(data, u, v, c, layout, sigma_d, fit_uv=False)
    status[ref["index"]] = "reference"
    remaining = [b for b in bands if b is not ref]
    while remaining:
        used_n = np.array([d["n"].mean() for d in data])
        nxt = min(remaining, key=lambda b: np.min(np.abs(used_n - b["n_mid"])))
        remaining.remove(nxt)
        trial = [dict(d) for d in data] + [_band_data(nxt, layout)]
        tu, tv, tc, res, _ = _gauss_newton(trial, u, v, c, layout, sigma_d)
        rms = [math.degrees(float(np.sqrt(np.mean(r ** 2)))) for r in res]
        if max(rms) < MAX_JOIN_RMS_DEG:
            data, u, v, c = trial, tu, tv, tc
            status[nxt["index"]] = "joined"
        else:
            status[nxt["index"]] = f"inconsistent ({rms[-1]:.1f} deg)"
    cov = None
    if len(data) > 1:
        u, v, c, res, J = _gauss_newton(data, u, v, c, layout, sigma_d)
        chi2 = float(sum(np.sum((r / sigma_d) ** 2) for r in res))
        dof = max(1, sum(len(r) for r in res) - 3)
        sc = np.sqrt((J ** 2).sum(axis=0))
        cov = (np.linalg.inv((J / sc).T @ (J / sc)) / np.outer(sc, sc))[:2, :2] * max(1.0, chi2 / dof)
    else:
        res = [_wrap(d["delta"] - _model(d["n"], d["s"], u, v, layout) - c) for d in data]
    for d, rr in zip(data, res):
        status[d["index"]] = (status[d["index"]], math.degrees(float(np.sqrt(np.mean(rr ** 2)))),
                              d["dn"] / d["sigma_n"] * RADIUS_SIGMA_MM * 1000)
    return u, v, c, cov, status


def analyse(path: str | None, layout: CalLayout, out_dir: str, dpi: float | None = None,
            centre=None, img=None, log=print) -> dict:
    meta_dpi = None
    if img is None:
        img, meta_dpi = scan.load_gray(path)
    px_per_mm = (dpi or (meta_dpi[0] if meta_dpi else None) or 600.0) / 25.4
    outer, hole = scan.locate_disc(img, px_per_mm, centre)
    cx, cy = outer["cx"], outer["cy"]
    sx, sy = px_per_mm, px_per_mm * outer["ry"] / outer["rx"]
    radii = np.arange(layout.start_mm - 0.6, min(layout.end_mm + 0.6, 59.0), DR_MM)
    f, _ = scan.polar_rings(img, cx, cy, sx, sy, radii, n_theta=N_THETA, sub=2)
    profile = np.nanmedian(f, axis=1)
    b_mm = layout.bit_nm * 1e-6
    a0 = layout.r0_mm ** 2
    c0 = layout.pitch_um * 1e-3 * b_mm * SECTOR_BITS / math.pi
    # Guard start and guard end change brightness in opposite directions; which one
    # rises depends on whether 92 scans brighter than the band average, so try both.
    lbas = layout.edge_lbas()
    alternating = [1 if i % 2 == 0 else -1 for i in range(len(lbas) - 1)] + [0]
    candidates = [fit_edges(radii, profile, lbas, a0, c0, signs=[sg * x for x in alternating],
                            windows=(0.4, 0.15)) for sg in (1, -1)]
    geo = max(candidates, key=lambda g: (g["fitted"], sum(1 for e in g["edges"] if e[3])))
    if not geo["fitted"]:
        raise RuntimeError("could not fit the guard-ring edges; check the scan and the layout file")
    a, c_edge = geo["a"], geo["c"]
    n_of_r = SECTOR_BITS * (radii ** 2 - a) / c_edge

    coef, snr = scan.ring_coefficients(f, layout.ks)
    snr = np.nan_to_num(snr, nan=0.0)
    psi = np.angle(coef)
    inv = psi[:, 1] - 3 * psi[:, 0]
    design = math.radians(layout.phases_deg[1] - 3 * layout.phases_deg[0])
    chiral = (snr[:, 0] > GOOD_SNR) & (snr[:, 1] > GOOD_SNR)
    if chiral.sum() < 5:
        raise RuntimeError("no band shows the pattern clearly; the geometry may be outside the hypothesis "
                           "range, or the burn is not visible in the scan")
    score = float(np.mean(np.cos(inv[chiral] - design)))
    mirrored = score < 0
    if mirrored:
        psi = -psi
    delta_all = (math.radians(layout.phases_deg[0]) - psi[:, 0]) / 3

    bands, rows, recs = [], [], []
    for band in layout.bands:
        r_in = math.sqrt(a + c_edge * band["lba_start"])
        r_out = math.sqrt(a + c_edge * band["lba_end"])
        idx = np.nonzero((radii >= r_in + EDGE_MARGIN_MM) & (radii <= r_out - EDGE_MARGIN_MM))[0]
        good = idx[snr[idx, 0] > GOOD_SNR]
        rec = {"index": band["index"], "group": band["group"], "s": band["s"], "r_in_mm": r_in,
               "r_out_mm": r_out, "rings": len(idx), "good": len(good), "readable": False, "reason": ""}
        rec["s_local_needed"] = None
        if len(good) < MIN_RINGS or len(good) < MIN_GOOD_FRACTION * len(idx):
            rec["reason"] = "blurred"
        else:
            d3 = np.unwrap(3 * delta_all[good])
            if np.max(np.abs(np.diff(d3))) > MAX_STEP_RAD:
                rec["reason"] = "turns too fast"
            else:
                d = d3 / 3
                n = n_of_r[good]
                A = np.column_stack([np.ones_like(n), n - n.mean()])
                (icpt, slope), *_ = np.linalg.lstsq(A, d, rcond=None)
                resid = d - A @ np.array([icpt, slope])
                rms = math.degrees(float(np.sqrt(np.mean(resid ** 2))))
                if rms > MAX_BAND_RMS_DEG:
                    rec["reason"] = f"not straight ({rms:.1f} deg rms)"
                else:
                    sig = float(np.sqrt(np.sum(resid ** 2) / max(1, len(n) - 2) / np.sum((n - n.mean()) ** 2)))
                    n_mid = float(n.mean())
                    rt = (1 + band["s"]) * float(rate(n_mid, layout.u0, layout.v0)) + slope
                    rec.update(readable=True, rms_deg=rms, n_mid=n_mid, rate=rt, rate_sigma=max(sig, 1e-15),
                               s_local_needed=rt / float(rate(n_mid, layout.u0, layout.v0)) - 1,
                               n=n, delta=delta_all[good])
                    bands.append(rec)
        for i in idx:
            rows.append((band["index"], radii[i], n_of_r[i], snr[i, 0], snr[i, 1], delta_all[i]))
        recs.append(rec)

    result = {"mirrored": bool(mirrored), "chirality_score": round(score, 3),
              "edges_used": sum(1 for e in geo["edges"] if e[3]), "edges_expected": len(layout.edge_lbas()),
              "readable_bands": [b["index"] for b in bands]}
    coarse = coarse_fit(bands)
    fit = None
    status = {}
    if coarse:
        u, v, c_rot, cov, status = fine_fit(bands, coarse[0], coarse[1], layout)
        fit = _report(u, v, cov, coarse, layout, n_of_r)
    elif bands:
        log("Readable bands do not span enough radius for a two-parameter fit; local rates only.")
    result["fit"] = fit

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "bands.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["band", "group", "s", "r_in_mm", "r_out_mm", "rings", "good_rings", "readable",
                    "reason", "line_rms_deg", "s_local_needed", "fine_fit", "fine_rms_deg", "radius_shift_um"])
        for rec in recs:
            st = status.get(rec["index"], "")
            st_name, st_rms, st_dr = (st if isinstance(st, tuple) else (st, None, None))
            w.writerow([rec["index"], rec["group"], f"{rec['s']:+.4f}", f"{rec['r_in_mm']:.4f}",
                        f"{rec['r_out_mm']:.4f}", rec["rings"], rec["good"], int(rec["readable"]), rec["reason"],
                        f"{rec['rms_deg']:.3f}" if rec["readable"] else "",
                        f"{rec['s_local_needed']:+.5f}" if rec["s_local_needed"] is not None else "",
                        st_name, f"{st_rms:.3f}" if st_rms is not None else "",
                        f"{st_dr:.2f}" if st_dr is not None else ""])
    with open(os.path.join(out_dir, "phase.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["band", "radius_mm", "n_bits", "snr_k3", "snr_k9", "delta_deg_mod120"])
        for b_i, r, n, s3, s9, d in rows:
            w.writerow([b_i, f"{r:.4f}", f"{n:.0f}", f"{s3:.2f}", f"{s9:.2f}", f"{math.degrees(_wrap(d)):.3f}"])
    summary = {
        "scan": os.path.abspath(path) if path else None,
        "dpi_used": round(px_per_mm * 25.4, 3),
        "centre_px": [round(cx, 2), round(cy, 2)],
        "outer_edge_radius_mm": round(outer["rx"] / px_per_mm, 4),
        "y_over_x_scale": round(outer["ry"] / outer["rx"], 6),
        "radial_fit": {"r0_mm": round(math.sqrt(a), 4),
                       "pitch_x_bit_vs_nominal": round(c_edge / c0, 5)},
        **result,
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    _unrolled_png(f, radii, layout, a, c_edge, set(result["readable_bands"]), out_dir)

    log(f"Edges {result['edges_used']}/{result['edges_expected']}, mirrored {mirrored}, "
        f"readable bands {len(bands)}/{len(layout.bands)}")
    for b in bands:
        st = status.get(b["index"], "")
        log(f"  band {b['index']:>2} (group {b['group']}, s {b['s']:+.2%}) r {b['r_in_mm']:.2f}-{b['r_out_mm']:.2f} mm: "
            f"local rate error {b['s_local_needed']:+.4%}, line rms {b['rms_deg']:.2f} deg"
            + (f", fine fit {st[0]} {st[1]:.2f} deg, radius shift {st[2]:+.1f} um" if isinstance(st, tuple)
               else (f", {st}" if st else "")))
    if fit:
        log(f"u = r0/b = {fit['u']:.3f}, v = p/b = {fit['v']:.7f}")
        log(f"With bit length {layout.bit_nm} nm: r0 {fit['r0_mm_at_bit']:.5f} mm, pitch {fit['pitch_um_at_bit']:.6f} um")
        if fit.get("angle_sigma_deg") is not None:
            log(f"Angle uncertainty across {fit['angle_span_mm'][0]}-{fit['angle_span_mm'][1]} mm: "
                f"{fit['angle_sigma_deg']:.3f} deg (1 sigma); nominal geometry was off by "
                f"{fit['nominal_error_deg']:.0f} deg over the same span")
    summary["_bands"] = bands
    summary["_status"] = status
    summary["_geo"] = geo
    return summary


def _report(u, v, cov, coarse, layout: CalLayout, n_of_r) -> dict:
    b_nm = layout.bit_nm
    out = {"u": u, "v": v, "coarse_u": coarse[0], "coarse_v": coarse[1],
           "r0_mm_at_bit": u * b_nm * 1e-6, "pitch_um_at_bit": v * b_nm * 1e-3,
           "bit_nm_assumed": b_nm,
           "note": "angles depend only on u and v; any bit length with r0 = u*b and pitch = v*b gives the same image"}
    b_mm = b_nm * 1e-6
    out["dis_equivalent"] = {
        "bit_nm": b_nm, "inner_radius_mm": u * b_mm,
        "outer_radius_mm_for_total_sectors": {
            str(n): math.sqrt((u * b_mm) ** 2 + v * b_mm * b_mm * n * SECTOR_BITS / math.pi)
            for n in (2295104, 2298496)},
        "note": "DiscImageStudio builds its spiral from inner radius, outer radius and track length "
                "(total sectors x 38688 x bit); use the outer radius for your disc's sector count",
    }
    lo, hi = 24.0, 58.0
    n_lo = math.pi * ((lo / (b_nm * 1e-6)) ** 2 - u * u) / v
    n_hi = math.pi * ((hi / (b_nm * 1e-6)) ** 2 - u * u) / v
    n_lo = max(n_lo, 0.0)
    out["angle_span_mm"] = [lo, hi]
    nn = np.linspace(n_lo, n_hi, 400)
    diff = np.degrees(theta(nn, u, v) - theta(nn, layout.u0, layout.v0))
    out["nominal_error_deg"] = float(diff.max() - diff.min())
    if cov is not None:
        g_hi = np.array(_dtheta(n_hi, u, v))
        g_lo = np.array(_dtheta(n_lo, u, v))
        g = g_hi - g_lo
        out["angle_sigma_deg"] = math.degrees(math.sqrt(float(g @ cov[:2, :2] @ g)))
        out["u_sigma"] = math.sqrt(cov[0, 0])
        out["v_sigma"] = math.sqrt(cov[1, 1])
    return out


def _unrolled_png(f, radii, layout: CalLayout, a, c_edge, readable: set, out_dir: str) -> None:
    from PIL import Image, ImageDraw
    g = np.where(np.isnan(f), np.nanmedian(f), f)
    small = g.reshape(g.shape[0], N_THETA // 4, 4).mean(axis=2)
    lo, hi = np.percentile(small, (1, 99))
    grey = np.clip((small - lo) / (hi - lo + 1e-9) * 255, 0, 255).astype(np.uint8)
    pad = 70
    im = Image.new("RGB", (grey.shape[1] + pad, grey.shape[0]), (255, 255, 255))
    im.paste(Image.fromarray(grey).convert("RGB"), (pad, 0))
    d = ImageDraw.Draw(im)
    for band in layout.bands:
        r_mid = math.sqrt(a + c_edge * 0.5 * (band["lba_start"] + band["lba_end"]))
        y = int(round((r_mid - radii[0]) / DR_MM))
        colour = (0, 150, 0) if band["index"] in readable else (120, 120, 120)
        d.text((2, y - 6), f"{band['s']:+.1%}", fill=colour)
    im.save(os.path.join(out_dir, "unrolled.png"))
