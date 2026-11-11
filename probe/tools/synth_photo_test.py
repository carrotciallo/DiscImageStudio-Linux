"""End-to-end test of discprobe.tilephoto on synthetic photos of a tile target.

Renders the design through a known camera (homography from a pose and focal length),
gives every texture a grey level (A5 and 92 differ by the contrast k, the other swatches
lie in between), adds a white surround, a light hub, blur and noise, then runs the photo
analysis and reports IDs read and the reprojection error of the fitted homography.

Usage: python tools/synth_photo_test.py [LAYOUT.json]   (default iso/lut2.tiles.json)
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from discprobe import tiledisc as T, tilephoto  # noqa: E402
from discprobe.imagedisc import CELL_MM, HALF_MM, SIZE  # noqa: E402

W, H_PX, F = 2016, 1512, 1400.0          # image size and focal length in pixels (about 24 mm equivalent)


def camera_h(C, look_at=(0.0, 0.0, 0.0), roll_deg=0.0):
    C = np.asarray(C, float)
    z = np.asarray(look_at) - C
    z /= np.linalg.norm(z)
    x = np.cross([0.0, 1.0, 0.0], z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.vstack([x, y, z])
    rr = math.radians(roll_deg)
    R = np.array([[math.cos(rr), -math.sin(rr), 0], [math.sin(rr), math.cos(rr), 0], [0, 0, 1]]) @ R
    t = -R @ C
    K = np.array([[F, 0, W / 2], [0, F, H_PX / 2], [0, 0, 1.0]])
    Hm = K @ np.column_stack([R[:, 0], R[:, 1], t])
    return Hm / Hm[2, 2]


def render(labels, textures, Hm, k, seed=0):
    rng = np.random.default_rng(seed)
    level = 0.30 + k * rng.uniform(0, 1, len(textures))
    level[textures.index("A5")], level[textures.index("92")] = 0.30, 0.30 + k
    Hi = np.linalg.inv(Hm)
    yy, xx = np.mgrid[0:H_PX, 0:W]
    u, v = xx.ravel() + 0.5, yy.ravel() + 0.5
    s = Hi[2, 0] * u + Hi[2, 1] * v + Hi[2, 2]
    x = (Hi[0, 0] * u + Hi[0, 1] * v + Hi[0, 2]) / s
    y = (Hi[1, 0] * u + Hi[1, 1] * v + Hi[1, 2]) / s
    r = np.hypot(x, y)
    ix = np.clip(np.floor((x + HALF_MM) / CELL_MM).astype(int), 0, SIZE - 1)
    iy = np.clip(np.floor((HALF_MM - y) / CELL_MM).astype(int), 0, SIZE - 1)
    img = np.where(r > 60, 0.90, np.where(r < 22, 0.60, level[labels[iy, ix]]))
    img = np.where((r >= 22) & (r <= 60) & (labels[iy, ix] == 0) & (r < 24.8), 0.35, img)   # unwritten inner band
    img = gaussian_filter(img.reshape(H_PX, W), 1.0) + rng.normal(0, 0.02, (H_PX, W))
    return np.clip(np.stack([img] * 3, -1), 0, 1)


def reproj_error(H_fit, H_true):
    pts = [(r * math.cos(a), r * math.sin(a)) for r in (30, 45, 55) for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)]
    e = [np.hypot(*(np.array(tilephoto.project(H_fit, x, y)) - np.array(tilephoto.project(H_true, x, y)))) for x, y in pts]
    return float(np.max(e))


def main(layout_path="iso/lut2.tiles.json"):
    with open(layout_path, encoding="utf-8") as f:
        lay = json.load(f)
    labels, textures, _ = T.design(lay["palette"], **T.geometry(lay))
    cases = [("head-on, contrast 0.30", (0, 0, 220), 0.30), ("head-on, contrast 0.10", (0, 0, 220), 0.10),
             ("head-on, contrast 0.04", (0, 0, 220), 0.04), ("offset 60 mm, contrast 0.10", (60, 20, 180), 0.10),
             ("offset 60 mm, contrast 0.04", (60, 20, 180), 0.04),
             ("offset 100 mm, contrast 0.10", (90, -40, 150), 0.10)]
    tmp = tempfile.mkdtemp()
    for name, C, k in cases:
        Hm = camera_h(C, roll_deg=17.0)
        img = render(labels, textures, Hm, k)
        path = os.path.join(tmp, "synth.png")
        Image.fromarray((img * 255).astype(np.uint8)).save(path)
        s = tilephoto.analyse(path, layout_path, os.path.join(tmp, "out"), mirrors=(False,), log=lambda *_: None,
                              focal_px=F)
        err = reproj_error(np.array(s["homography_disc_mm_to_px"]), Hm)
        print(f"{name:30s} IDs {s['ids_ok']:2d}/{s['tiles']}  max reprojection error {err:6.1f} px", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
