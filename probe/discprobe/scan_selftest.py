"""Synthetic end-to-end test for the spoke scan analysis.

Renders what a scan of a burned spoke disc could look like: a known bending curve
delta(r) and radial distortion applied to the model pattern, binary dithering,
an unknown rotation, scanner x/y scale mismatch, an off-centre disc, a lighting
gradient, a k = 2 diffraction rainbow stronger than the pattern itself, noise, and
optionally a mirrored or dark/light-inverted image. The analysis must recover the
bending curve and the marker radii.
"""

from __future__ import annotations

import math
import tempfile

import numpy as np

from . import scan
from .spokes import SpokeSpec, brightness

DPI = 600.0
BEND_TOL_DEG = 0.3
MARKER_TOL_MM = 0.03


def bend_true(r):
    x = (r - 24.0) / 34.0
    return 260.0 * x * x - 45.0 * x


def model_radius(r_actual):
    return r_actual * 0.998 + 0.03


def actual_radius(r_model):
    return (r_model - 0.03) / 0.998


def synth_scan(spec: SpokeSpec, mirrored=False, inverted=False, seed=0,
               canvas_mm=(140.0, 135.0), centre_mm=(71.3, 66.1), y_scale=1.003, rot_deg=37.0):
    rng = np.random.default_rng(seed)
    px = DPI / 25.4
    w = int(canvas_mm[0] * px)
    h = int(canvas_mm[1] * px * y_scale)
    out = np.empty((h, w), dtype=np.float32)
    xs = (np.arange(w) + 0.5) / px - centre_mm[0]
    for i0 in range(0, h, 256):
        ys = centre_mm[1] - (np.arange(i0, min(h, i0 + 256)) + 0.5) / (px * y_scale)
        x, y = np.meshgrid(xs, ys)
        r = np.hypot(x, y)
        th_view = np.arctan2(y, x)
        th = -th_view if mirrored else th_view
        th_model = th - np.radians(bend_true(r)) - math.radians(rot_deg)
        b = brightness(spec, model_radius(r), th_model)
        bit = b > rng.random(b.shape)
        if inverted:
            bit = ~bit
        data = np.where(bit, 0.60, 0.40) + 0.15 * np.cos(2 * th_view + 0.4) + 0.06 * x / 60
        v = np.select(
            [r < 7.5, r < 22.0, r < 23.6, r <= 58.4, r < 59.9, r < 60.05],
            [0.93, 0.78, 0.55, data, 0.70, 0.30],
            default=0.95)
        out[i0:i0 + len(ys)] = v + rng.normal(0, 0.05, v.shape)
    return out


def _case(c, spec, mirrored, inverted):
    label = f"mirrored={mirrored}, inverted={inverted}"
    print(f"synthetic scan: {label}")
    img = synth_scan(spec, mirrored=mirrored, inverted=inverted, seed=11 + 2 * mirrored + inverted)
    with tempfile.TemporaryDirectory() as tmp:
        s = scan.analyse(None, spec, tmp, dpi=DPI, img=img, log=lambda *_: None)
    c.check(s["mirrored"] == mirrored, f"mirror detected as {s['mirrored']}")
    radii, rel, ok = s["_radii"], s["_delta_rel"], s["_ok"]
    truth = bend_true(radii) - bend_true(radii[ok][0])
    err = np.abs(rel[ok] - truth[ok])
    c.check(ok.sum() > 500, f"rings used {ok.sum()} of {len(radii)} "
                            f"({s['radius_range_used_mm'][0]}-{s['radius_range_used_mm'][1]} mm)")
    c.check(err.max() < BEND_TOL_DEG,
            f"bending over {truth[ok].min():.0f}..{truth[ok].max():.0f} deg: max error {err.max():.3f} deg, "
            f"rms {np.sqrt(np.mean(err ** 2)):.3f} deg, noise/ring {s['noise_per_ring_deg']}")
    c.check(abs(s["y_over_x_scale"] - 1.003) < 2e-4, f"scanner y/x scale {s['y_over_x_scale']}")
    marker_err = [abs(m["actual_mm"] - actual_radius(m["model_mm"])) for m in s["markers"]]
    c.check(len(marker_err) == len(spec.marker_radii_mm) - 0 and max(marker_err) < MARKER_TOL_MM,
            f"{len(marker_err)} markers, max radius error {max(marker_err, default=float('nan')):.4f} mm")


def run(c) -> None:
    spec = SpokeSpec()
    _case(c, spec, mirrored=False, inverted=False)
    _case(c, spec, mirrored=True, inverted=True)
