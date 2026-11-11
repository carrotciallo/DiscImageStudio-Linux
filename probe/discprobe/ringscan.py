"""Brightness of each texture on a flatbed scan of the texture-ring disc.

Pipeline, per scan:
  1. Locate the disc (same edge fit as the spoke analysis) and resample polar rings.
  2. Take the median over angle at each radius, locate the ring edges as gradient
     peaks near their predicted radii, and fit r^2 = a + c * LBA through them. That
     gives the real ring radii, and as a by-product r0 and the product pitch x sector
     length (radial geometry only; it says nothing about angles).
  3. Average each ring inside its fitted edges in angle bins. The flatbed lamp and the
     disc's diffraction rainbow change brightness and contrast with angle and radius,
     so per angle bin the A5 and 92 rings of all groups are fitted linearly in radius
     and each ring is expressed as a level: 0 = A5, 1 = 92 at the same place.
  4. Pool every texture over groups (and over scans), estimate the repeat scatter, and
     suggest a palette whose neighbouring levels differ by at least 3x that scatter.

The level scale assumes the scanner output is linear in reflectance between the two
references; with gamma-encoded files the levels are still ordered correctly but the
spacing is distorted. Separations measured here say what the scanner can tell apart
under its own lighting, not what an eye will see.
"""

from __future__ import annotations

import csv
import json
import math
import os

import numpy as np

from . import scan
from .rings import RingLayout

N_THETA = 2048
N_BINS = 72
DR_MM = 0.02
EDGE_SCORE = 6.0
SEPARATION_SIGMAS = 3.0
CONTRAST_KEEP = 0.5  # angle bins whose A5-92 contrast is at least this share of the best


def load_channels(path: str):
    """{'L': luminance, 'R', 'G', 'B' when the file has colour}, values in 0..1, plus DPI."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(path) as im:
        dpi = im.info.get("dpi")
        if im.mode in ("I;16", "I;16B", "I;16L", "I"):
            ch = {"L": np.asarray(im, dtype=np.float32) / 65535.0}
        elif im.mode in ("L", "1"):
            ch = {"L": np.asarray(im.convert("L"), dtype=np.float32) / 255.0}
        else:
            rgb = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
            ch = _split(rgb)
    return ch, (float(dpi[0]) if dpi else None)


def _split(a: np.ndarray) -> dict:
    if a.ndim == 2:
        return {"L": a.astype(np.float32)}
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return {"L": (0.2126 * r + 0.7152 * g + 0.0722 * b).astype(np.float32), "R": r, "G": g, "B": b}


# ---------------------------------------------------------------- edges and radial fit

def _edge_peak(radii, grad, guess, window):
    sel = np.nonzero(np.abs(radii - guess) <= window)[0]
    if len(sel) < 5:
        return None
    j = sel[int(np.argmax(grad[sel]))]
    if j in (sel[0], sel[-1]) or j == 0 or j == len(grad) - 1:
        return None
    den = grad[j - 1] - 2 * grad[j] + grad[j + 1]
    off = 0.5 * (grad[j - 1] - grad[j + 1]) / den if den != 0 else 0.0
    return radii[j] + off * (radii[1] - radii[0]), float(grad[j])


def fit_edges(radii, profile, lbas, a: float, c: float, signs=None, windows=(0.6, 0.25)):
    """Edges at the given LBAs as (LBA, radius, score, used, residual) and the fit
    r^2 = a + c * LBA, starting from the nominal a and c.

    signs, if given, holds +1 (brightness rises outward), -1 (falls) or 0 (either) per
    edge, so two close edges of opposite direction are not confused."""
    smooth = np.convolve(np.nan_to_num(profile, nan=float(np.nanmedian(profile))), np.ones(3) / 3, mode="same")
    signed = np.gradient(smooth, radii)
    signed[:3] = signed[-3:] = 0
    grad = np.abs(signed)
    noise = float(np.median(np.abs(grad - np.median(grad))) * 1.4826) or 1e-9
    per_edge = [grad if not signs or not signs[i] else np.maximum(signs[i] * signed, 0) for i in range(len(lbas))]
    fitted, kept = False, []
    for window in windows:
        found = []
        for n, g in zip(lbas, per_edge):
            hit = _edge_peak(radii, g, math.sqrt(a + c * n), window)
            if hit and hit[1] / noise > EDGE_SCORE:
                found.append((n, hit[0], hit[1] / noise))
        if len(found) < 4:
            break
        e = np.array(found)
        keep = np.ones(len(e), bool)
        for _ in range(3):
            A = np.column_stack([np.ones(keep.sum()), e[keep, 0]])
            (a_new, c_new), *_ = np.linalg.lstsq(A, e[keep, 1] ** 2, rcond=None)
            res = np.sqrt(np.maximum(a_new + c_new * e[:, 0], 0)) - e[:, 1]
            mad = np.median(np.abs(res[keep])) * 1.4826
            keep = np.abs(res) < max(4 * mad, 0.02)
        a, c, fitted = float(a_new), float(c_new), True
        kept = [(n, r, s, bool(k), float(rs)) for (n, r, s), k, rs in zip(found, keep, res)]
    return {"a": a, "c": c, "fitted": fitted, "edges": kept, "grad_noise": noise}


# ---------------------------------------------------------------- per-scan analysis

def _ring_rows(polar, radii, layout: RingLayout, a, c, margin, bins, name):
    rows = []
    for ring in layout.rings:
        r_in = math.sqrt(a + c * ring["lba_start"])
        r_out = math.sqrt(a + c * ring["lba_end"])
        sel = (radii >= r_in + margin) & (radii <= r_out - margin)
        if sel.sum() < 3:
            raise RuntimeError(f"{name}: ring {ring['index']} is narrower than its margins")
        vals = {}
        for k, p in polar.items():
            band = np.nanmean(p[sel], axis=0)
            vals[k] = np.bincount(bins, weights=band, minlength=N_BINS) / np.bincount(bins, minlength=N_BINS)
        rows.append({**ring, "r_in_mm": r_in, "r_out_mm": r_out, "r_mid_mm": 0.5 * (r_in + r_out), "bins": vals})
    return rows


def _ref_span(rows, k, ring, with_dark=False, refs=("A5", "92")):
    """The dark and bright references fitted linearly in radius over the groups, per
    angle bin, evaluated at this ring: returns bright - dark (and the dark value)."""
    x = ring["r_mid_mm"] - 40.0
    vals = {}
    for t in refs:
        rr = np.array([r["r_mid_mm"] for r in rows if r["texture"] == t]) - 40.0
        vv = np.array([r["bins"][k] for r in rows if r["texture"] == t])
        coef, *_ = np.linalg.lstsq(np.column_stack([np.ones_like(rr), rr]), vv, rcond=None)
        vals[t] = coef[0] + coef[1] * x
    span = vals[refs[1]] - vals[refs[0]]
    return (vals[refs[0]], span) if with_dark else span

def analyse_scan(ch: dict, layout: RingLayout, px_per_mm: float, centre=None, log=print, name="scan",
                 refs=("A5", "92")):
    outer, hole = scan.locate_disc(ch["L"], px_per_mm, centre)
    cx, cy = outer["cx"], outer["cy"]
    sx = px_per_mm
    sy = px_per_mm * outer["ry"] / outer["rx"]
    r_lo = max(layout.rings[0]["r_start_mm"] - 1.2, 20.0)
    r_hi = min(layout.rings[-1]["r_end_mm"] + 1.2, 59.0)
    radii = np.arange(r_lo, r_hi, DR_MM)
    polar = {k: scan.polar_rings(v, cx, cy, sx, sy, radii, n_theta=N_THETA, sub=2)[0] for k, v in ch.items()}
    if np.isnan(polar["L"]).mean() > 0.01:
        raise RuntimeError(f"{name}: part of the disc is outside the scan")
    lbas = [r["lba_start"] for r in layout.rings] + [layout.rings[-1]["lba_end"]]
    a0 = layout.r0_mm ** 2
    c0 = (layout.radius_at(1e6) ** 2 - a0) / 1e6
    bins = (np.arange(N_THETA) * N_BINS) // N_THETA

    # A flatbed lamp shows texture contrast only in some directions; elsewhere glare
    # swamps it. A first pass at the nominal radii finds the angle bins where A5 and
    # 92 differ most, and both the edge fit and the levels use only those.
    rows0 = _ring_rows(polar, radii, layout, a0, c0, 0.45, bins, name)
    span0 = np.abs(np.median(np.array([_ref_span(rows0, "L", r, refs=refs) for r in rows0]), axis=0))
    use = span0 >= CONTRAST_KEEP * span0.max()
    profile = np.nanmean(polar["L"][:, use[bins]], axis=1)
    geo = fit_edges(radii, profile, lbas, a0, c0)
    a, c = geo["a"], geo["c"]
    margin = 0.25 if geo["fitted"] else 0.45
    if not geo["fitted"]:
        log(f"{name}: fewer than 4 ring edges found; using the nominal radii with wider margins")
    rows = _ring_rows(polar, radii, layout, a, c, margin, bins, name)

    for k in polar:
        for r in rows:
            dark, span = _ref_span(rows, k, r, with_dark=True, refs=refs)
            v = r["bins"][k]
            level = float(np.sum(((v - dark) * span)[use]) / np.sum((span * span)[use]))
            per_bin = ((v - dark) / span)[use]
            r.setdefault("level", {})[k] = level
            r.setdefault("level_bin_spread", {})[k] = float(np.median(np.abs(per_bin - np.median(per_bin))) * 1.4826)
            r.setdefault("raw", {})[k] = float(v[use].mean())
            r.setdefault("contrast_raw", {})[k] = float(np.median(span[use]))
            r.setdefault("angle_variation", {})[k] = float(v.std())
    info = {
        "name": name,
        "dpi_used": round(px_per_mm * 25.4, 3),
        "centre_px": [round(cx, 2), round(cy, 2)],
        "outer_edge_radius_mm": round(outer["rx"] / px_per_mm, 4),
        "y_over_x_scale": round(outer["ry"] / outer["rx"], 6),
        "edges_found": len(geo["edges"]),
        "edges_used": sum(1 for e in geo["edges"] if e[3]),
        "edges_expected": len(layout.rings) + 1,
        "angle_fraction_used": round(float(use.mean()), 3),
        "radial_fit": None,
    }
    if geo["fitted"]:
        res = [e[4] for e in geo["edges"] if e[3]]
        nominal_c = (layout.radius_at(1e6) ** 2 - layout.r0_mm ** 2) / 1e6
        info["radial_fit"] = {
            "r0_mm": round(math.sqrt(a), 4),
            "pitch_x_sector_length_vs_nominal": round(c / nominal_c, 5),
            "edge_residual_rms_mm": round(float(np.sqrt(np.mean(np.square(res)))), 4),
            "note": "radius scale comes from the scanner DPI; compare outer_edge_radius_mm with 60.0",
        }
    return {"info": info, "rows": rows, "polar": polar["L"], "radii": radii, "geo": geo}


# ---------------------------------------------------------------- pooling

def pool(results: list[dict], layout: RingLayout, channel: str = "L", refs=("A5", "92")) -> dict:
    by_tex = {t: [] for t in layout.textures}
    for res in results:
        for r in res["rows"]:
            by_tex[r["texture"]].append(r["level"][channel])
    stats = {}
    ss, dof = 0.0, 0
    for t, v in by_tex.items():
        v = np.array(v)
        stats[t] = {"n": len(v), "level": float(v.mean()), "std": float(v.std(ddof=1)) if len(v) > 1 else float("nan")}
        if t not in refs and len(v) > 1:
            ss += float(np.sum((v - v.mean()) ** 2))
            dof += len(v) - 1
    s_pool = math.sqrt(ss / dof) if dof else float("nan")
    order = sorted(stats, key=lambda t: stats[t]["level"])
    palette = [order[0]]
    for t in order[1:]:
        if stats[t]["level"] - stats[palette[-1]]["level"] >= SEPARATION_SIGMAS * s_pool:
            palette.append(t)
    sep = {a: {b: (abs(stats[a]["level"] - stats[b]["level"]) / s_pool if s_pool > 0 else float("inf"))
               for b in order} for a in order}
    return {"channel": channel, "textures": stats, "pooled_std": s_pool, "pooled_dof": dof,
            "order_dark_to_bright": order, "palette": palette, "separation_sigmas": sep}


# ---------------------------------------------------------------- top level

def analyse(paths: list[str] | None, layout: RingLayout, out_dir: str, dpi: float | None = None,
            centre=None, images=None, log=print, refs=("A5", "92")) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    results = []
    sources = images if images is not None else [(p, None) for p in paths]
    for i, (path, arr) in enumerate(sources):
        if arr is None:
            ch, meta_dpi = load_channels(path)
            name = os.path.splitext(os.path.basename(path))[0]
        else:
            ch, meta_dpi, name = _split(arr), None, f"image{i}"
        d = dpi or meta_dpi
        if not d:
            d = 600.0
            log(f"{name}: no DPI in file and none given; assuming 600 dpi")
        res = analyse_scan(ch, layout, d / 25.4, centre, log, name, refs=refs)
        results.append(res)
        inf = res["info"]
        fit = inf["radial_fit"]
        log(f"{name}: edges {inf['edges_used']}/{inf['edges_expected']}"
            + (f", r0 {fit['r0_mm']} mm, pitch x length {fit['pitch_x_sector_length_vs_nominal']} x nominal, "
               f"edge rms {fit['edge_residual_rms_mm']} mm" if fit else ", no radial fit"))
        _unrolled_png(res, layout, os.path.join(out_dir, f"unrolled_{name}.png"))

    channels = list(results[0]["rows"][0]["level"])
    pooled = {k: pool(results, layout, k, refs) for k in channels if all(k in r["rows"][0]["level"] for r in results)}

    with open(os.path.join(out_dir, "rings.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scan", "channel", "ring", "group", "texture", "r_in_mm", "r_out_mm",
                    "level", "level_bin_spread", "raw_mean", "contrast_raw", "angle_variation"])
        for res in results:
            for r in res["rows"]:
                for k in r["level"]:
                    w.writerow([res["info"]["name"], k, r["index"], r["group"], r["texture"],
                                f"{r['r_in_mm']:.4f}", f"{r['r_out_mm']:.4f}", f"{r['level'][k]:.4f}",
                                f"{r['level_bin_spread'][k]:.4f}", f"{r['raw'][k]:.5f}",
                                f"{r['contrast_raw'][k]:.5f}", f"{r['angle_variation'][k]:.5f}"])
    with open(os.path.join(out_dir, "textures.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["channel", "texture", "n", "level", "std"])
        for k, p in pooled.items():
            for t in p["order_dark_to_bright"]:
                s = p["textures"][t]
                w.writerow([k, t, s["n"], f"{s['level']:.4f}", f"{s['std']:.4f}"])

    lum = pooled["L"]
    warnings = []
    if not lum["pooled_std"] < 0.2:
        warnings.append("levels scatter by more than 0.2 of the reference span: the references barely differ "
                        "under this lighting, so the levels are unreliable")
    for res in results:
        if not res["info"]["radial_fit"]:
            warnings.append(f"{res['info']['name']}: ring edges not fitted, nominal radii used")
    summary = {
        "warnings": warnings,
        "scans": [r["info"] for r in results],
        "levels": {k: {t: round(v["level"], 4) for t, v in p["textures"].items()} for k, p in pooled.items()},
        "pooled_std_L": round(lum["pooled_std"], 5),
        "order_dark_to_bright_L": lum["order_dark_to_bright"],
        "palette_L": lum["palette"],
        "palette_rule": f"neighbouring levels differ by >= {SEPARATION_SIGMAS} x the pooled repeat std "
                        "(scanner separability only; confirm by eye)",
        "separation_sigmas_L": {a: {b: round(v, 1) for b, v in row.items()} for a, row in lum["separation_sigmas"].items()},
        "level_scale": f"0 = {refs[0]}, 1 = {refs[1]} at the same radius and angle",
    }
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    log(f"\nLevels (L, 0 = {refs[0]}, 1 = {refs[1]}), pooled repeat std {lum['pooled_std']:.4f}:")
    for t in lum["order_dark_to_bright"]:
        s = lum["textures"][t]
        log(f"  {t:>4}  {s['level']:7.3f}  +- {s['std']:.3f}  (n {s['n']})")
    log(f"Suggested palette (dark to bright): {' '.join(lum['palette'])}")
    for wmsg in warnings:
        log(f"warning: {wmsg}")
    summary["_results"] = results
    summary["_pooled"] = pooled
    return summary


def _unrolled_png(res, layout: RingLayout, path: str) -> None:
    """Polar view: radius down, angle across, fitted ring edges in red, texture names at the left."""
    from PIL import Image, ImageDraw
    p = res["polar"]
    g = np.where(np.isnan(p), np.nanmedian(p), p)
    small = g.reshape(g.shape[0], N_THETA // 2, 2).mean(axis=2)
    lo, hi = np.percentile(small, (1, 99))
    grey = np.clip((small - lo) / (hi - lo + 1e-9) * 255, 0, 255).astype(np.uint8)
    pad = 60
    im = Image.new("RGB", (grey.shape[1] + pad, grey.shape[0]), (255, 255, 255))
    im.paste(Image.fromarray(grey).convert("RGB"), (pad, 0))
    d = ImageDraw.Draw(im)
    radii = res["radii"]
    to_row = lambda r: int(round((r - radii[0]) / (radii[1] - radii[0])))
    for r in res["rows"]:
        for edge in (r["r_in_mm"], r["r_out_mm"]):
            y = to_row(edge)
            d.line([(pad, y), (pad + 12, y)], fill=(220, 0, 0))
            d.line([(im.width - 12, y), (im.width, y)], fill=(220, 0, 0))
        d.text((4, to_row(r["r_mid_mm"]) - 6), f"{r['texture']}", fill=(0, 0, 0))
    im.save(path)
