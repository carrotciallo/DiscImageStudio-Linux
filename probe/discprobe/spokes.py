"""Radial-spoke calibration pattern.

Brightness at polar position (r, theta) of the *model* disc is

    b = 0.5 + 0.5 * sum_k w_k * cos(k*theta + phi_k)

for k = 3, 21, 63. DiscImageStudio places every byte by its model position, so on the
real disc the pattern shows up rotated by delta(r) = actual angle - model angle at
each radius; that bending curve is what the scan analysis measures.

Design choices:
- Only pure sinusoids, so each k sits in its own Fourier bin.
- k ratios are odd (21/3 = 7, 63/21 = 3). An inverted scan (dark/light swapped) then
  leaves the phase invariants unchanged, while a mirrored scan flips the sign of
  psi21 - 7*psi3, which is designed to be 90 degrees.
- k = 1 and 2 are avoided: lighting gradients and the scanner's diffraction rainbow
  live mostly there.
- Thin uniform-grey marker rings at known model radii make the spoke amplitude drop
  to zero; finding them in the scan gives actual radius versus model radius.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field

import numpy as np


@dataclass
class SpokeSpec:
    radius_mm: float = 58.0
    size_px: int = 4096
    ks: tuple = (3, 21, 63)
    phases_deg: tuple = (0.0, 90.0, 0.0)
    weights: tuple = (0.3, 0.3, 0.4)
    marker_radii_mm: tuple = (26.0, 32.0, 38.0, 44.0, 50.0, 56.0)
    marker_width_mm: float = 0.5
    version: int = 1
    notes: list = field(default_factory=lambda: [
        "image centre = disc centre; image half-width = radius_mm",
        "theta is counter-clockwise from +x with y pointing up in the image"])

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path: str) -> "SpokeSpec":
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        for key in ("ks", "phases_deg", "weights", "marker_radii_mm"):
            d[key] = tuple(d[key])
        return cls(**d)


def brightness(spec: SpokeSpec, r_mm: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """Pattern brightness in [0, 1] at model polar coordinates."""
    b = np.full(np.broadcast(r_mm, theta).shape, 0.5, dtype=np.float64)
    for k, phi, w in zip(spec.ks, spec.phases_deg, spec.weights):
        b += 0.5 * w * np.cos(k * theta + np.radians(phi))
    half = spec.marker_width_mm / 2
    for rm in spec.marker_radii_mm:
        b = np.where(np.abs(r_mm - rm) < half, 0.5, b)
    return np.clip(b, 0.0, 1.0)


def render(spec: SpokeSpec, rows_per_chunk: int = 256) -> np.ndarray:
    n = spec.size_px
    mm_per_px = 2 * spec.radius_mm / n
    xs = (np.arange(n) + 0.5 - n / 2) * mm_per_px
    out = np.empty((n, n), dtype=np.uint8)
    for i0 in range(0, n, rows_per_chunk):
        ys = (n / 2 - (np.arange(i0, min(n, i0 + rows_per_chunk)) + 0.5)) * mm_per_px
        x, y = np.meshgrid(xs, ys)
        r = np.hypot(x, y)
        b = brightness(spec, r, np.arctan2(y, x))
        b = np.where(r > spec.radius_mm, 1.0, b)
        out[i0:i0 + len(ys)] = np.round(b * 255).astype(np.uint8)
    return out


def generate(path: str, spec: SpokeSpec) -> str:
    from PIL import Image
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img = render(spec)
    dpi = spec.size_px / (2 * spec.radius_mm / 25.4)
    Image.fromarray(img).save(path, dpi=(dpi, dpi))
    spec_path = os.path.splitext(path)[0] + ".spokes.json"
    spec.save(spec_path)
    return spec_path
