"""Export a measured angle map as a DiscImageStudio DVD or CD preset (cubic track pitch).

DiscImageStudio models a disc by its inner and outer radius, the sector count, a fixed
channel bit length (CD: a fixed 1200 mm/s, the same thing), and a pitch
p(x) = p0 (1 + c1 x + c2 x^2 + c3 x^3), x = (r - ri) / (ro - ri), with p0 set by the
total track length. That is a different family from our
constant-pitch u, v model plus an angle correction phi(r), so the conversion is a fit:
ri, ro, c1, c2, c3 are chosen to reproduce our angle as a function of track position
over the measured radius range (an overall rotation is free), and the remaining angle
difference is reported so the export can be judged before use.

Thin-track approximation for arc length (ds = 2 pi r / p dr); against the exact arc
length this changes angles by well under 0.001 degree over a whole DVD.
"""

from __future__ import annotations

import json
import math

import numpy as np
from scipy.optimize import least_squares

from . import cd
from .calib import SECTOR_BITS, theta

GRID = 40001
MAX_EXPORT_DIFF_DEG = 5.0   # far beyond any real pitch shape: the fit failed, so no preset is written
CD_VELOCITY_MM_S = 1200     # fixed in DiscImageStudio; 57624 bits of cd.BIT_NM are 16 mm, 1/75 s at this speed


def dis_angle_map(ri, ro, c1, c2, c3, total_sectors, bit_nm, sector_bits=SECTOR_BITS):
    """Track position n (channel bits) and accumulated angle (rad) on a radius grid."""
    b = bit_nm * 1e-6
    r = np.linspace(ri, ro, GRID)
    x = (r - ri) / (ro - ri)
    shape = 1 + c1 * x + c2 * x * x + c3 * x ** 3
    if np.any(shape <= 0):
        return None
    cum = lambda y: np.concatenate([[0.0], np.cumsum((y[1:] + y[:-1]) * 0.5 * np.diff(r))])
    length = total_sectors * sector_bits * b
    s_unit = cum(2 * np.pi * r / shape)          # arc length times p0
    p0 = s_unit[-1] / length
    n = s_unit / p0 / b
    th = cum(2 * np.pi / shape) / p0
    return n, th, p0


def target_angle(n, u, v, bit_nm, correction=None):
    """Our angle along the track: constant-pitch model, minus phi(r) when a correction is given
    (phi is counter-clockwise in data-side view, while the track angle runs clockwise)."""
    th = theta(n, u, v)
    if correction is not None:
        r = bit_nm * 1e-6 * np.sqrt(u * u + v * n / math.pi)
        th = th - np.radians(correction(r))
    return th


def fit_preset(u, v, bit_nm, total_sectors, r_lo, r_hi, correction=None, sector_bits=SECTOR_BITS):
    b = bit_nm * 1e-6
    n_lo = math.pi * ((r_lo / b) ** 2 - u * u) / v
    n_hi = math.pi * ((r_hi / b) ** 2 - u * u) / v
    n_eval = np.linspace(n_lo, n_hi, 600)
    want = target_angle(n_eval, u, v, bit_nm, correction)
    ri0 = u * b
    ro0 = b * math.sqrt(u * u + v * total_sectors * sector_bits / math.pi)
    scale = np.array([1e-3, 1e-3, 1e-4, 1e-4, 1e-4])   # mm, mm, relative

    def resid(z):
        ri, ro, c1, c2, c3 = np.array([ri0, ro0, 0, 0, 0]) + z * scale
        m = dis_angle_map(ri, ro, c1, c2, c3, total_sectors, bit_nm, sector_bits)
        if m is None:
            return np.full(len(n_eval), 1e3)
        n, th, _ = m
        d = np.interp(n_eval, n, th) - want
        return np.degrees(d - d.mean())

    def jac(z):
        # A step of 1 is 1 um of radius or 1e-4 of pitch. The default step (1e-8) is lost in the noise of
        # interpolating on the radius grid, and the solver then stops at the start with no warning.
        return np.stack([(resid(z + e) - resid(z - e)) / 2 for e in np.eye(5)], axis=1)

    sol = least_squares(resid, np.zeros(5), jac=jac, x_scale=1.0, xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=400)
    ri, ro, c1, c2, c3 = np.array([ri0, ro0, 0, 0, 0]) + sol.x * scale
    d = resid(sol.x)
    _, _, p0 = dis_angle_map(ri, ro, c1, c2, c3, total_sectors, bit_nm, sector_bits)
    return {"innerRadiusMm": float(ri), "outerRadiusMm": float(ro), "pitchLinear": float(c1),
            "pitchQuadratic": float(c2), "pitchCubic": float(c3), "p0_um": float(p0 * 1e3),
            "fit_range_mm": [r_lo, r_hi], "max_angle_diff_deg": float(np.max(np.abs(d))),
            "rms_angle_diff_deg": float(np.sqrt(np.mean(d * d))),
            "peak_to_peak_angle_diff_deg": float(d.max() - d.min())}


def preset_json(fit, total_sectors, bit_nm, preset_id, name, description, media="dvd"):
    if media == "cd":
        size = {"sectors": total_sectors, "innerRadiusMm": fit["innerRadiusMm"],
                "outerRadiusMm": fit["outerRadiusMm"], "linearVelocityMmPerSecond": CD_VELOCITY_MM_S}
    else:
        size = {"totalSectors": total_sectors, "innerRadiusMm": fit["innerRadiusMm"],
                "outerRadiusMm": fit["outerRadiusMm"], "channelBitLengthNm": bit_nm}
    return {"id": preset_id, "displayName": name, "description": description, **size,
            "pitchLinear": fit["pitchLinear"], "pitchQuadratic": fit["pitchQuadratic"],
            "pitchCubic": fit["pitchCubic"]}


def export(geo_summary: str, total_sectors: int, correction_path: str | None, out_path: str,
           r_lo: float, r_hi: float, preset_id: str, name: str, along_track_frames: float = 0) -> dict:
    with open(geo_summary, encoding="utf-8") as f:
        geo = json.load(f)["fit"]
    media = "cd" if geo.get("media") == "cd" else "dvd"
    u, v, bit = geo["u"], geo["v"], geo["bit_nm_assumed"]
    if media == "cd":
        cd.check_capacity(total_sectors)
        if abs(bit - cd.BIT_NM) > 1e-6:
            raise ValueError(f"DiscImageStudio fixes the CD speed at 1200 mm/s ({cd.BIT_NM:.4f} nm per bit), "
                             f"this geo run assumed {bit} nm")
        # Same convention as image --along-track-frames: theta(n - d) is the spiral with u^2 - v d / pi.
        u = math.sqrt(u * u - v * along_track_frames * cd.FRAME_BITS / math.pi)
    elif along_track_frames:
        raise ValueError("--along-track-frames is for CD")
    corr = None
    if correction_path:
        from .imagedisc import load_correction
        corr = load_correction(correction_path)
    fit = fit_preset(u, v, bit, total_sectors, r_lo, r_hi, corr, cd.SECTOR_BITS if media == "cd" else SECTOR_BITS)
    if fit["max_angle_diff_deg"] > MAX_EXPORT_DIFF_DEG:
        raise ValueError(f"the preset misses the measured map by {fit['max_angle_diff_deg']:.1f} deg over "
                         f"{r_lo}-{r_hi} mm (outer radius came out {fit['outerRadiusMm']:.3f} mm); "
                         f"check --sectors and the fit range. No preset written.")
    desc = (f"Drive-timing calibration (discprobe){' + grid-scan angle correction' if corr else ''}; "
            f"fitted over {r_lo}-{r_hi} mm, max angle difference to the measured map "
            f"{fit['max_angle_diff_deg']:.3f} deg")
    if media == "cd":
        desc += f"; along-track constant {along_track_frames:g} frames"
    out = {"preset": preset_json(fit, total_sectors, bit, preset_id, name, desc, media), "fit": fit,
           "source": {"geo": geo_summary.replace("\\", "/").split("/")[-1],
                      "correction": correction_path.replace("\\", "/").split("/")[-1] if correction_path else None}}
    if media == "cd":
        out["source"]["along_track_frames"] = along_track_frames
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    return out
