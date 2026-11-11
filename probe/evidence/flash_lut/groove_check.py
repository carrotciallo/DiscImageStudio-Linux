"""Are the colours of 92 at small |delta| the groove's radial rainbow?

With the flash at the lens, the groove grating (pitch p = 0.745 um, grating vector radial)
sends wavelength lambda = 2 p |c . r_hat| / m back to the camera, where r_hat is the outward
radial unit vector at the tile. For m = 1 and 400-700 nm that needs |c . r_hat| in 0.27-0.47.
This script recomputes c for every verified tile observation and compares, for the 92
swatch (its colour relative to the tile's mean swatch colour, which removes the global
cast), the measured hue with the hue predicted by the groove (first order) or by the 16T
along-track grating (first order), in observations where only one of the two falls in the
visible range. A shuffle of the predictions gives the chance level.

    python evidence/flash_lut/groove_check.py
"""

import colorsys
import csv
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import flash_lut  # noqa: E402

PITCH_UM, P16_UM = 0.745, 16 * 0.1333
DL = os.path.join(os.path.expanduser("~"), "Downloads")
LAYOUT = json.load(open(os.path.join(ROOT, "iso", "lut2.tiles.json"), encoding="utf-8"))


def tile_centre(ring, sector):
    e, g = LAYOUT["ring_edges_mm"], LAYOUT["gap_mm"]
    n = LAYOUT["sectors_per_ring"][ring]
    r = (e[ring] + e[ring + 1]) / 2
    a = (sector + 0.5) * 2 * math.pi / n
    return r, a


def visible(lam_um):
    return 0.40 <= lam_um <= 0.70


def hue_of(rgb):
    rgb = np.asarray(rgb, float)
    return colorsys.rgb_to_hsv(*np.clip(rgb / max(rgb.max(), 1e-3), 0, 1))[0] * 360


def main():
    from lut_scatter import wavelength_rgb
    from PIL import Image, ImageOps
    rows = [r for r in csv.DictReader(open(os.path.join(HERE, "swatch_colours_vs_delta.csv"), encoding="utf-8"))
            if r["verified"] == "1"]
    cams = {}
    for name in sorted({r["photo"] for r in rows}):
        s = json.load(open(os.path.join(ROOT, "results", "flash_lut_tiles_v2", name, "summary.json"), encoding="utf-8"))
        path = os.path.join(DL, name + ".jpeg")
        w, h = ImageOps.exif_transpose(Image.open(path)).size
        cams[name] = flash_lut.pose(np.array(s["homography_disc_mm_to_px"]), flash_lut.focal_px(path, w, h), w / 2, h / 2)
    meta = ("photo", "ring", "sector", "verified", "delta", "view_tilt_deg")
    groups = {"groove only": [], "16T only": []}
    for r in rows:
        rad, a = tile_centre(int(r["ring"]), int(r["sector"]))
        pt = np.array([rad * math.cos(a), rad * math.sin(a), 0.0])
        c = cams[r["photo"]] - pt
        c /= np.linalg.norm(c)
        cr = abs(c @ np.array([math.cos(a), math.sin(a), 0.0]))
        ct = abs(c @ np.array([-math.sin(a), math.cos(a), 0.0]))
        swatches = np.array([[float(v) for v in r[k].split()] for k in r if k not in meta])
        measured = hue_of(np.array([float(v) for v in r["92"].split()]) / (swatches.mean(0) + 1e-3))  # cast removed
        lam_g, lam_t = PITCH_UM * 2 * cr, P16_UM * 2 * ct
        if visible(lam_g) and not visible(lam_t):
            groups["groove only"].append((measured, hue_of(wavelength_rgb(lam_g * 1000))))
        if visible(lam_t) and not visible(lam_g):
            groups["16T only"].append((measured, hue_of(wavelength_rgb(lam_t * 1000))))
    rng = np.random.default_rng(0)
    err = lambda m, p: np.median(np.abs((m - p + 180) % 360 - 180))
    for k, v in groups.items():
        v = np.array(v)
        e = err(v[:, 0], v[:, 1])
        null = np.array([err(v[:, 0], rng.permutation(v[:, 1])) for _ in range(2000)])
        print(f"{k:12s} n {len(v):3d}  median |hue error| {e:5.1f} deg  shuffled {np.median(null):5.1f}  "
              f"p = {np.mean(null <= e):.3f}")


if __name__ == "__main__":
    main()
