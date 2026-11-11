"""Predicted first-order colour of each single-period texture over the disc, for a flash at the lens.

For a camera (with its flash) at position C (mm, disc centre at the origin, disc in z = 0),
every point p of the data area returns wavelength lambda = |delta| * P / m in order m, with
delta = 2 c . t (c the unit vector from p to C, t the track tangent). One panel per texture
shows the colour of the first order (dark grey where it is outside 400-700 nm; higher orders
are much weaker since about 75 % of the power is in the fundamental), so a design can pick,
region by region, the texture that gives the wanted colour from that viewpoint. Periods are
from evidence/flash_lut/grating_check.py.

Usage: python tools/colour_map.py X Y Z [OUT.png]      e.g. 0 80 150 (camera 8 cm off axis, 15 cm up)
"""

import os
import sys

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lut_scatter import wavelength_rgb  # noqa: E402

PERIODS_UM = {"A5": 0.85, "66": 1.06, "B9": 1.42, "92": 2.13}
R_IN, R_OUT, N = 23.0, 58.0, 500


def delta_map(C):
    s = np.linspace(-R_OUT, R_OUT, N)
    x, y = np.meshgrid(s, -s)
    r = np.hypot(x, y)
    c = np.stack([C[0] - x, C[1] - y, np.full_like(x, C[2])], -1)
    c /= np.linalg.norm(c, axis=-1, keepdims=True)
    t = np.stack([-y, x, np.zeros_like(x)], -1) / np.maximum(r, 1e-9)[..., None]
    return np.abs(2 * (c * t).sum(-1)), (r >= R_IN) & (r <= R_OUT)


def colour(d, P):
    img = np.full(d.shape + (3,), 0.15)
    lam = d * P * 1000
    ok = (lam >= 400) & (lam <= 700)
    img[ok] = [wavelength_rgb(v) for v in lam[ok]]
    return img


def main(x, y, z, out=None):
    C = (float(x), float(y), float(z))
    out = out or f"results/colour_map_{int(C[0])}_{int(C[1])}_{int(C[2])}.png"
    d, inside = delta_map(C)
    fig, axes = plt.subplots(1, len(PERIODS_UM), figsize=(4 * len(PERIODS_UM), 4.3))
    for ax, (name, P) in zip(axes, PERIODS_UM.items()):
        img = colour(d, P)
        img[~inside] = 1.0
        ax.imshow(img, extent=(-R_OUT, R_OUT, -R_OUT, R_OUT))
        ax.set_title(f"{name}  (P {P} um)", fontsize=10)
        ax.set_xticks([]), ax.set_yticks([])
    fig.suptitle(f"flash camera at ({C[0]:.0f}, {C[1]:.0f}, {C[2]:.0f}) mm; |delta| {d[inside].min():.2f}-"
                 f"{d[inside].max():.2f}; dark = first order not visible (prediction)", fontsize=9)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    fig.savefig(out, dpi=100, facecolor="white")
    print(out)


if __name__ == "__main__":
    main(*sys.argv[1:])
