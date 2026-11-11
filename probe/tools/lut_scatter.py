"""Per-texture colour vs |delta| from flash_lut_tiles output (verified tiles only).

One row per texture: x = |delta| = 2|c.t|, y = brightness (sum of RGB relative to the tile's
median swatch), dot colour = measured colour. The 92 row carries the predicted first-order
band of a 16T grating (P = 2.133 um): lambda = |delta| * P for 400-700 nm.

Usage: python tools/lut_scatter.py CSV [OUT.png]   (OUT defaults to lut_scatter.png next to CSV)
"""

import csv
import os
import sys

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def wavelength_rgb(nm):
    """Rough visible-spectrum colour."""
    if nm < 440:
        r, g, b = -(nm - 440) / 40, 0.0, 1.0
    elif nm < 490:
        r, g, b = 0.0, (nm - 440) / 50, 1.0
    elif nm < 510:
        r, g, b = 0.0, 1.0, -(nm - 510) / 20
    elif nm < 580:
        r, g, b = (nm - 510) / 70, 1.0, 0.0
    elif nm < 645:
        r, g, b = 1.0, -(nm - 645) / 65, 0.0
    else:
        r, g, b = 1.0, 0.0, 0.0
    return (r, g, b)


def main(path, out=None):
    out = out or os.path.join(os.path.dirname(path), "lut_scatter.png")
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["verified"] == "1"]
    names = [k for k in rows[0] if k not in ("photo", "ring", "sector", "verified", "delta", "view_tilt_deg")]
    d = np.abs(np.array([float(r["delta"]) for r in rows]))
    cols = np.array([[[float(v) for v in r[n].split()] for n in names] for r in rows])     # obs x tex x rgb
    bright = cols.sum(-1)
    rel = bright / np.median(bright, axis=1, keepdims=True)
    fig, axes = plt.subplots(len(names), 1, figsize=(9, 1.05 * len(names)), sharex=True)
    for i, (ax, n) in enumerate(zip(axes, names)):
        c = np.clip(cols[:, i] / np.maximum(cols[:, i].max(-1, keepdims=True), 1e-3), 0, 1)
        ax.set_facecolor("#202020")
        ax.scatter(d, rel[:, i], c=c, s=9, edgecolors="none")
        if n == "92":
            for nm in range(400, 701, 10):
                x = nm / 1000 / 2.133
                ax.axvspan(x - 0.0024, x + 0.0024, ymin=0.9, ymax=1.0, color=wavelength_rgb(nm), lw=0)
        ax.set_ylim(0, max(2.5, np.percentile(rel[:, i], 99) * 1.1))
        ax.set_ylabel(n if len(n) < 10 else n[:9] + "…", rotation=0, ha="right", va="center", fontsize=8)
        ax.tick_params(labelsize=7)
    axes[-1].set_xlabel("|delta| = 2 |c . t|   (verified tiles; top strip on the 92 row: predicted 16T first order)")
    fig.tight_layout()
    fig.savefig(out, dpi=110, facecolor="white")
    print(out, len(rows), "observations")


if __name__ == "__main__":
    main(*sys.argv[1:])
