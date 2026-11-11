"""Check the beacon target reader on synthetic photos, against where each tile really is.

Each texture gets a colour that drifts slowly over the disc and is dark over part of it, under a
perspective view. This tests the reader's logic only: it says nothing about how bright or how
different the textures will be on a real disc.

Usage: python tools/beacon_synth.py [--trials N] [--px-per-mm P]
"""

from __future__ import annotations

import argparse
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from discprobe import beacondisc as bd, beaconread as br  # noqa: E402
from discprobe.imagedisc import CELL_MM, HALF_MM, SIZE  # noqa: E402


def check(got, project, px_per_mm):
    """Numbers of strong and weak reads whose bullseye B really is that tile's, and of the others."""
    out = {"strong_right": 0, "strong_wrong": 0, "weak_right": 0, "weak_wrong": 0}
    for t in got:
        r, a = bd.finder_centres(t["ring"], t["sector"])["B"]
        d = np.linalg.norm(project(r * math.cos(a), r * math.sin(a)) - np.array(t["finders_px"]["B"])) / px_per_mm
        out[("strong_" if t["strong"] else "weak_") + ("right" if d < 1.0 else "wrong")] += 1
    return out


def render(labels, textures, rng, px_per_mm, dead_pair=None, tilt_deg=20.0, noise=3.0, size=(2400, 1800)):
    """A photo: colour per texture and per coarse region, seen under a tilted perspective camera."""
    base = np.zeros((len(textures), 32, 32, 3), np.float32)
    for t in range(len(textures)):
        coarse = rng.uniform(4, 150, (5, 5, 3)).astype(np.float32)
        base[t] = cv2.resize(coarse, (32, 32), interpolation=cv2.INTER_CUBIC).clip(2, 220)
    if dead_pair is not None:      # one texture of a pair copies the other: that pair has no contrast at all
        a, b = (textures.index(n) for n in bd.PAIRS[dead_pair])
        kill = b if dead_pair == 0 else a
        base[kill] = base[textures.index("92")]
    step = max(1, int(1 / (px_per_mm * CELL_MM) / 2))
    lab = labels[::step, ::step]
    yy, xx = np.mgrid[0:lab.shape[0], 0:lab.shape[1]]
    u = (xx * 32 // lab.shape[1]).astype(int)
    v = (yy * 32 // lab.shape[0]).astype(int)
    tex = base[lab, v, u]
    th, rot = math.radians(tilt_deg), rng.uniform(0, 2 * math.pi)
    n = lab.shape[0]
    mm = step * CELL_MM
    src = np.float32([[0, 0], [n, 0], [n, n], [0, n]])
    corners = []
    cz = 240.0
    for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
        x, y = sx * n * mm / 2, sy * n * mm / 2
        xr, yr = x * math.cos(rot) - y * math.sin(rot), x * math.sin(rot) + y * math.cos(rot)
        z = cz + yr * math.sin(th)
        s = (px_per_mm * cz) / z
        corners.append((size[0] / 2 + xr * s, size[1] / 2 - yr * math.cos(th) * s))
    H = cv2.getPerspectiveTransform(src, np.float32(corners))
    img = cv2.warpPerspective(tex, H, size, flags=cv2.INTER_AREA, borderValue=(30, 30, 30))
    img = img + rng.normal(0, noise, img.shape)

    def project(x_mm, y_mm):
        q = H @ np.array([(x_mm + HALF_MM) / mm, (HALF_MM - y_mm) / mm, 1.0])
        return q[:2] / q[2]
    return np.clip(img, 0, 255).astype(np.uint8), project


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=4)
    ap.add_argument("--px-per-mm", type=float, default=14.0)
    args = ap.parse_args()
    labels, textures, layout = bd.design()
    n = sum(bd.sectors_per_ring())
    print(f"{n} tiles; code distance {bd.bank_distances()} (all bits, 92/66 alone, A5/92 alone)")
    rng = np.random.default_rng(7)
    for name, dead in (("all textures differ", None), ("66 copies 92", 0), ("A5 copies 92", 1)):
        for _ in range(args.trials):
            img, project = render(labels, textures, rng, args.px_per_mm, dead_pair=dead)
            got = br.read_tiles(img, args.px_per_mm)
            print(f"{name}: of {n} tiles {check(got, project, args.px_per_mm)}", flush=True)
    noise = rng.integers(0, 255, (1800, 2400, 3), dtype=np.uint8)
    noise = cv2.GaussianBlur(noise, (0, 0), 6)
    noise = np.clip((noise.astype(np.float32) - noise.mean()) * 8 + 90, 0, 255).astype(np.uint8)
    print("false tiles on a textured random image:", len(br.read_tiles(noise, args.px_per_mm)))


if __name__ == "__main__":
    main()
