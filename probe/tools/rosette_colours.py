"""Measure petal colours per texture on photos of the rosette colour test.

Fits the photo with discprobe.tilephoto (the rosette design's A5 and 92 petals drive the
fit), then averages the photo colour over every petal and flower centre, grouped by
rosette, and draws a chart: one row per rosette (sorted by angle), one column per texture.

Usage: python tools/rosette_colours.py IMG_xxxx.jpeg [...]
"""

from __future__ import annotations

import csv
import json
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

LABELS = np.load(os.path.join(os.path.dirname(__file__), "..", "iso", "rosettes_design.npy"))
NAMES = ["bg 8T mix", "A5", "92 16T", "66", "ED00 64T", "48T centre"]


def rosette_of(x, y):
    r, th = np.hypot(x, y), np.arctan2(y, x)
    k = np.argmin(np.abs(r[..., None] - np.array(RINGS_MM)), axis=-1)
    n = np.array([int(2 * math.pi * rc // PITCH_MM) for rc in RINGS_MM])[k]
    step = 2 * math.pi / n
    j = np.round((th - step * 0.5 * (k % 2)) / step).astype(int) % n
    return k, j


def measure(path, out_dir):
    rgb = tilephoto.load_photo(path)
    small, fs = tilephoto._reduce(rgb, tilephoto.FIT_WIDTH)
    H, info = tilephoto.fit(small, LABELS, TEXTURES, (small.shape[1] / 2, small.shape[0] / 2), auto_hub=True,
                             mirrors=(False,))
    Hi = np.linalg.inv(H)
    h, w = small.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    u, v = xx.ravel() + 0.5, yy.ravel() + 0.5
    s = Hi[2, 0] * u + Hi[2, 1] * v + Hi[2, 2]
    x = (Hi[0, 0] * u + Hi[0, 1] * v + Hi[0, 2]) / s
    y = (Hi[1, 0] * u + Hi[1, 1] * v + Hi[1, 2]) / s
    ix = np.floor((x + HALF_MM) / CELL_MM).astype(int)
    iy = np.floor((HALF_MM - y) / CELL_MM).astype(int)
    ok = (ix >= 0) & (ix < SIZE) & (iy >= 0) & (iy < SIZE) & (np.hypot(x, y) < 54.8) & (np.hypot(x, y) > 24.5)
    lab = np.full(ix.shape, -1)
    lab[ok] = LABELS[iy[ok], ix[ok]]
    k, j = rosette_of(x, y)
    col = small.reshape(-1, 3)
    acc = {}
    for key in zip(k[ok], j[ok], lab[ok], np.arange(len(u))[ok]):
        acc.setdefault(key[:3], []).append(key[3])
    rows = []
    for (kk, jj) in sorted({(a, b) for a, b, _ in acc}):
        row = {"ring": int(kk), "rosette": int(jj)}
        n = int(2 * math.pi * RINGS_MM[kk] // PITCH_MM)
        row["angle_deg"] = round((360.0 * (jj + 0.5 * (kk % 2)) / n) % 360, 1)
        complete = True
        for t in range(len(TEXTURES)):
            idx = acc.get((kk, jj, t))
            if not idx or len(idx) < 8:
                complete = False
                continue
            row[NAMES[t]] = " ".join(f"{c:.3f}" for c in col[idx].mean(0))
        if complete:
            rows.append(row)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "rosettes.csv"), "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=["ring", "rosette", "angle_deg"] + NAMES)
        wr.writeheader()
        wr.writerows(rows)
    with open(os.path.join(out_dir, "fit.json"), "w", encoding="utf-8") as f:
        json.dump({"photo": os.path.basename(path), **info, "rosettes": len(rows)}, f, indent=2)
    rows.sort(key=lambda r: r["angle_deg"])
    cw, ch = 70, 9
    im = Image.new("RGB", (cw * len(NAMES) + 70, ch * len(rows) + 24), (25, 25, 25))
    d = ImageDraw.Draw(im)
    for t, name in enumerate(NAMES):
        d.text((70 + t * cw + 3, 6), name, fill=(230, 230, 230))
    for i, r in enumerate(rows):
        if i % 6 == 0:
            d.text((4, 24 + i * ch - 2), f"{r['angle_deg']:.0f}", fill=(200, 200, 200))
        for t, name in enumerate(NAMES):
            c = np.array([float(q) for q in r[name].split()])
            d.rectangle((70 + t * cw, 24 + i * ch, 70 + (t + 1) * cw - 2, 24 + (i + 1) * ch - 1),
                        fill=tuple(int(q) for q in np.clip(c * 1.3, 0, 1) * 255))
    im.save(os.path.join(out_dir, "chart.png"))
    print(f"{os.path.basename(path)}: {len(rows)} complete rosettes, fit {info}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        measure(p, os.path.join("results", "rosettes", os.path.splitext(os.path.basename(p))[0]))
