"""Second pass: fixed mapping (no mirror, fixed scale), list every registration peak, then measure
contrast old vs new only at a registration that is checked across scans."""
import json
import sys

import cv2
import numpy as np
from scipy.signal import find_peaks

sys.stdout.reconfigure(encoding="utf-8")
D = sys.argv[1]
MM = 600 / 25.4
RS = np.arange(25.5, 57.5, 0.05)
WEDGE, DTH = 9.0, 0.1
SCALE = 10.1
CENTRES = {(0, "new"): (2293.6, 2351.7), (0, "old"): (2281.1, 5292.0), (1, "old"): (2456.4, 1820.8), (1, "new"): (2339.4, 5277.6),
           (2, "old"): (2465.6, 1723.8), (2, "new"): (2437.0, 5209.5)}
ths_a = np.arange(-WEDGE, WEDGE, DTH)
wedges = {"R": ths_a, "L": ths_a + 180}
design = cv2.imread("D:/disc-probe/iso/dense.preview.png", cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
H = design.shape[0] / 2


def linear(rgb):
    x = rgb.astype(np.float32) / 255
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def polar(img, c, rs, ths):
    R, T = np.meshgrid(rs, np.deg2rad(ths), indexing="ij")
    return cv2.remap(img, (c[0] + R * MM * np.cos(T)).astype(np.float32), (c[1] + R * MM * np.sin(T)).astype(np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def highpass(y):
    ly = np.log(np.maximum(y, 1e-4))
    return ly - cv2.GaussianBlur(ly, (0, 0), sigmaX=3.0 / DTH, sigmaY=2.0 / 0.05, borderType=cv2.BORDER_REFLECT)


def dpolar(rs, ths, theta):
    R, T = np.meshgrid(rs, np.deg2rad(ths + theta), indexing="ij")
    return cv2.remap(design, (H + R * SCALE * np.cos(T)).astype(np.float32), (H + R * SCALE * np.sin(T)).astype(np.float32), cv2.INTER_AREA)


def ncc(a, b):
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-12))



CLIP = 0.35
hp = {}
for page in (0, 1, 2):
    img = cv2.imread(f"{D}/p{page}.png")[:, :, ::-1]
    L = linear(img)
    Y = (0.2126 * L[..., 0] + 0.7152 * L[..., 1] + 0.0722 * L[..., 2]).astype(np.float32)
    for k, c in CENTRES.items():
        if k[0] == page:
            hp[k] = {w: np.clip(highpass(polar(Y, c, RS, t)), -CLIP, CLIP) for w, t in wedges.items()}


def dhp(rs, ths, theta):
    d = dpolar(rs, ths, theta)
    step_r = (rs[1] - rs[0]) if len(rs) > 1 else 0.05
    step_t = (ths[1] - ths[0]) if len(ths) > 1 else DTH
    return d - cv2.GaussianBlur(d, (0, 0), sigmaX=3.0 / step_t, sigmaY=2.0 / step_r, borderType=cv2.BORDER_REFLECT)


grid = np.arange(0, 360, 0.5)
curves = {}
for k in sorted(hp):
    v = np.zeros(len(grid))
    for i, th in enumerate(grid):
        v[i] = sum(ncc(dhp(RS[::4], t[::4], th), hp[k][w][::4, ::4]) for w, t in wedges.items()) / 2
    curves[k] = v
    pk, _ = find_peaks(np.r_[v, v[:40]], distance=8)
    pk = pk[pk < len(v)]
    top = pk[np.argsort(-v[pk])[:5]]
    print(k, "peaks", [(float(grid[i]), round(float(v[i]), 3)) for i in top], "median", round(float(np.median(v)), 3), flush=True)


def measure(k, theta):
    ds, ss = [], []
    for w, t in wedges.items():
        ds.append(dpolar(RS, t, theta))
        ss.append(hp[k][w])
    d, s = np.hstack(ds), np.hstack(ss)
    tiles = []
    for j in range(0, d.shape[1], 30):
        for i in range(0, d.shape[0], 80):
            dd, sss = d[i:i + 80, j:j + 30], s[i:i + 80, j:j + 30]
            a, b = dd > 0.75, dd < 0.25
            if a.sum() > 40 and b.sum() > 40:
                tiles.append(np.median(sss[a]) - np.median(sss[b]))
    tiles = np.array(tiles)
    return {"contrast_median": float(np.median(s[d > 0.75]) - np.median(s[d < 0.25])), "tile_mean": float(tiles.mean()),
            "tile_sem": float(tiles.std() / np.sqrt(len(tiles))), "n": len(tiles), "ncc_full": ncc(d, s)}


print("best theta, refined")
res = {}
for k in sorted(hp):
    th0 = float(grid[np.argmax(curves[k])])
    fine = [(sum(ncc(dhp(RS[::2], t[::2], th), hp[k][w][::2, ::2]) for w, t in wedges.items()) / 2, th) for th in np.arange(th0 - 1, th0 + 1, 0.05)]
    v, th = max(fine)
    res[str(k)] = {"theta": float(th), "ncc": float(v), **measure(k, th)}
    print(k, {a: (round(b, 4) if isinstance(b, float) else b) for a, b in res[str(k)].items()}, flush=True)
json.dump(res, open(f"{D}/compare3.json", "w"), indent=1)
