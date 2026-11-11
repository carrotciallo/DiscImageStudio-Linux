"""Colour lookup table from flash photos of the rosette colour test.

With the phone's flash as the only light, source and lens sit at (almost) the same point,
so the along-track diffraction condition at a disc point p is

    m * lambda / period = 2 * (c . t)

with c the unit vector from p to the camera and t the local track tangent. delta = 2 c.t
is fixed by the camera pose alone, which follows from the fitted homography and the
focal length (EXIF 35 mm equivalent): H = K [r1 r2 t].

For every complete rosette in every photo this records delta at the rosette centre and
the mean colour of each texture, then draws one colour strip per texture against delta.

Usage: python tools/flash_lut.py IMG_a.jpeg IMG_b.jpeg ...   -> results/flash_lut/
"""

from __future__ import annotations

import csv
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from discprobe import tilephoto  # noqa: E402
from discprobe.imagedisc import CELL_MM, HALF_MM, SIZE  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from compose_rosettes import PITCH_MM, RINGS_MM, TEXTURES  # noqa: E402
from rosette_colours import LABELS, NAMES, rosette_of  # noqa: E402

OUT = os.path.join("results", "flash_lut")


def focal_px(path, width, height):
    with Image.open(path) as im:
        f35 = im.getexif().get_ifd(0x8769).get(0xA405)
    return f35 / 36.0 * max(width, height)          # 35 mm frame is 36 mm on its long side


def pose(H, f, cx, cy, with_rotation=False):
    """Camera centre in disc millimetres (z > 0 on the viewed side) from H (disc mm -> px);
    with_rotation also returns R (disc -> camera axes: x right, y down, z forward)."""
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1.0]])
    B = np.linalg.solve(K, H)
    lam = 2.0 / (np.linalg.norm(B[:, 0]) + np.linalg.norm(B[:, 1]))
    if B[2, 2] * lam < 0:
        lam = -lam
    r1, r2, t = lam * B[:, 0], lam * B[:, 1], lam * B[:, 2]
    R = np.column_stack([r1, r2, np.cross(r1, r2)])
    C = -R.T @ t
    if C[2] < 0:                                   # mirror solution: flip to the viewed side
        C[2], R = -C[2], R @ np.diag([1.0, 1.0, -1.0])
    return (C, R) if with_rotation else C


def photo_samples(path):
    rgb = tilephoto.load_photo(path)
    small, fs = tilephoto._reduce(rgb, tilephoto.FIT_WIDTH)
    H, info = tilephoto.fit(small, LABELS, TEXTURES, (small.shape[1] / 2, small.shape[0] / 2), auto_hub=True,
                             mirrors=(False,))
    h, w = small.shape[:2]
    f = focal_px(path, rgb.shape[1], rgb.shape[0]) * fs
    C = pose(H, f, w / 2, h / 2)
    Hi = np.linalg.inv(H)
    yy, xx = np.mgrid[0:h, 0:w]
    u, v = xx.ravel() + 0.5, yy.ravel() + 0.5
    s = Hi[2, 0] * u + Hi[2, 1] * v + Hi[2, 2]
    x = (Hi[0, 0] * u + Hi[0, 1] * v + Hi[0, 2]) / s
    y = (Hi[1, 0] * u + Hi[1, 1] * v + Hi[1, 2]) / s
    ix = np.floor((x + HALF_MM) / CELL_MM).astype(int)
    iy = np.floor((HALF_MM - y) / CELL_MM).astype(int)
    col = small.reshape(-1, 3)
    ok = ((ix >= 0) & (ix < SIZE) & (iy >= 0) & (iy < SIZE) & (np.hypot(x, y) > 24.5) & (np.hypot(x, y) < 54.8)
          & (col.max(1) < 0.97))                                  # skip the flash highlight
    lab = np.full(ix.shape, -1)
    lab[ok] = LABELS[iy[ok], ix[ok]]
    k, j = rosette_of(x, y)
    groups = {}
    for key, idx in zip(zip(k[ok], j[ok], lab[ok]), np.flatnonzero(ok)):
        groups.setdefault(key, []).append(idx)
    rows = []
    for kk, jj in sorted({(a, b) for a, b, _ in groups}):
        if not all(len(groups.get((kk, jj, t), [])) >= 8 for t in range(len(TEXTURES))):
            continue
        n = int(2 * math.pi * RINGS_MM[kk] // PITCH_MM)
        a = 2 * math.pi * (jj + 0.5 * (kk % 2)) / n
        p = np.array([RINGS_MM[kk] * math.cos(a), RINGS_MM[kk] * math.sin(a), 0.0])
        c = (C - p) / np.linalg.norm(C - p)
        tangent = np.array([-math.sin(a), math.cos(a), 0.0])
        row = {"photo": os.path.basename(path), "ring": int(kk), "rosette": int(jj),
               "angle_deg": round(math.degrees(a) % 360, 1), "delta": round(float(2 * c @ tangent), 4),
               "view_tilt_deg": round(math.degrees(math.acos(c[2])), 1)}
        for t in range(len(TEXTURES)):
            row[NAMES[t]] = " ".join(f"{q:.3f}" for q in col[groups[(kk, jj, t)]].mean(0))
        rows.append(row)
    print(f"{os.path.basename(path)}: camera at ({C[0]:.0f}, {C[1]:.0f}, {C[2]:.0f}) mm, "
          f"{len(rows)} rosettes, fit {info}", flush=True)
    return rows, C


def chart(rows, path, lo=-0.8, hi=0.8, step=0.02):
    bins = np.arange(lo, hi + 1e-9, step)
    cw, ch = 6, 34
    im = Image.new("RGB", (110 + cw * (len(bins) - 1), 40 + ch * len(NAMES)), (20, 20, 20))
    d = ImageDraw.Draw(im)
    deltas = np.array([r["delta"] for r in rows])
    for t, name in enumerate(NAMES):
        d.text((4, 40 + t * ch + 10), name, fill=(230, 230, 230))
        cols = np.array([[float(q) for q in r[name].split()] for r in rows])
        for b in range(len(bins) - 1):
            m = (deltas >= bins[b]) & (deltas < bins[b + 1])
            if m.sum():
                c = np.clip(cols[m].mean(0) * 1.4, 0, 1)
                d.rectangle((110 + b * cw, 40 + t * ch, 110 + (b + 1) * cw - 1, 40 + (t + 1) * ch - 3),
                            fill=tuple(int(q * 255) for q in c))
    for tick in np.arange(-0.8, 0.81, 0.2):
        x = 110 + int((tick - lo) / step * cw)
        d.line((x, 30, x, 38), fill=(200, 200, 200))
        d.text((x - 10, 14), f"{tick:+.1f}", fill=(200, 200, 200))
    im.save(path)


def main(paths):
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for p in paths:
        r, _ = photo_samples(p)
        rows += r
    with open(os.path.join(OUT, "rosette_colours_vs_delta.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    chart(rows, os.path.join(OUT, "lut_chart.png"))
    print(f"{len(rows)} rosette observations; delta range {min(r['delta'] for r in rows):.2f} .. "
          f"{max(r['delta'] for r in rows):.2f}")


if __name__ == "__main__":
    main(sys.argv[1:])
