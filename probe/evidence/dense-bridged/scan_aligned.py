"""Same part of the picture on both discs, point by point, using the angles the two wedges share.

Baseline: the same disc in scan 1 and scan 2, so old-vs-new can be read against repeatability.
"""
import json
import sys

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
D = sys.argv[1]
OUT = sys.argv[2]
MM = 600 / 25.4
DTH, DR = 0.1, 0.05
SCALE = 10.1
RS = np.arange(25.5, 57.5, DR)
CENTRES = {(0, "new"): (2293.6, 2351.7), (0, "old"): (2281.1, 5292.0), (1, "old"): (2456.4, 1820.8), (1, "new"): (2339.4, 5277.6)}
res = json.load(open(f"{D}/compare3.json"))
theta = {k: res[str(k)]["theta"] for k in CENTRES}
design = cv2.imread("D:/disc-probe/iso/dense.preview.png", cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
H = design.shape[0] / 2
INK, MUTED = "#1f2328", "#59636e"


def linear(rgb):
    x = rgb.astype(np.float32) / 255
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def polar(img, c, rs, ths):
    R, T = np.meshgrid(rs, np.deg2rad(ths), indexing="ij")
    return cv2.remap(img, (c[0] + R * MM * np.cos(T)).astype(np.float32), (c[1] + R * MM * np.sin(T)).astype(np.float32),
                     cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def highpass(y):
    ly = np.log(np.maximum(y, 1e-4))
    return ly - cv2.GaussianBlur(ly, (0, 0), sigmaX=3.0 / DTH, sigmaY=2.0 / DR, borderType=cv2.BORDER_REFLECT)


def ncc(a, b):
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-12))


# design angles shared by old and new: centre them so each disc sits off its wedge centre equally
th_old, th_new = np.mean([theta[(0, "old")], theta[(1, "old")]]), np.mean([theta[(0, "new")], theta[(1, "new")]])
mid = (th_old + th_new) / 2
half = 6.0
phis = {"A": np.arange(mid - half, mid + half, DTH), "B": np.arange(mid - half, mid + half, DTH) + 180}
print("theta old", round(th_old, 2), "new", round(th_new, 2), "shared design angles", round(mid - half, 2), "to", round(mid + half, 2))
Y = {}
for page in (0, 1):
    L = linear(cv2.imread(f"{D}/p{page}.png")[:, :, ::-1])
    Y[page] = (0.2126 * L[..., 0] + 0.7152 * L[..., 1] + 0.0722 * L[..., 2]).astype(np.float32)


def strip(k, phi):
    """Measure on a wide strip so the high-pass sees the same surroundings, then keep phi."""
    wide = np.arange(phi[0] - 8, phi[-1] + 8, DTH)
    hp = np.clip(highpass(polar(Y[k[0]], CENTRES[k], RS, wide - theta[k])), -0.35, 0.35)
    i = int(round(8 / DTH))
    return hp[:, i:i + len(phi)]


def dstrip(phi):
    R, T = np.meshgrid(RS, np.deg2rad(phi), indexing="ij")
    return cv2.remap(design, (H + R * SCALE * np.cos(T)).astype(np.float32), (H + R * SCALE * np.sin(T)).astype(np.float32), cv2.INTER_AREA)


def register(a, b):
    """Small leftover shift between two strips of the same picture (centres, theta)."""
    best = (-9, 0, 0)
    for dy in range(-8, 9):
        for dx in range(-8, 9):
            v = ncc(a[10:-10, 10:-10], np.roll(np.roll(b, dy, 0), dx, 1)[10:-10, 10:-10])
            if v > best[0]:
                best = (v, dy, dx)
    return best


strips, designs = {}, {}
for w, phi in phis.items():
    designs[w] = dstrip(phi)
    for k in CENTRES:
        strips[(w, k)] = strip(k, phi)

out = {"pairs": {}, "paired_contrast": {}}
for w in phis:
    for name, a, b in (("old s1 vs old s2", (0, "old"), (1, "old")), ("new s1 vs new s2", (0, "new"), (1, "new")), ("old s1 vs new s1", (0, "old"), (0, "new")),
                       ("old s2 vs new s2", (1, "old"), (1, "new")), ("old s1 vs new s2", (0, "old"), (1, "new")), ("old s2 vs new s1", (1, "old"), (0, "new"))):
        v, dy, dx = register(strips[(w, a)], strips[(w, b)])
        out["pairs"][f"{w} {name}"] = {"ncc": round(v, 3), "shift_px": [dy, dx]}
        print(w, name, round(v, 3), "shift", dy, dx)

# paired contrast: same patches of the same picture on both discs
diffs, olds, news = [], [], []
for w in phis:
    d = designs[w]
    old = (strips[(w, (0, "old"))] + strips[(w, (1, "old"))]) / 2
    new = (strips[(w, (0, "new"))] + strips[(w, (1, "new"))]) / 2
    for j in range(0, d.shape[1], 30):
        for i in range(0, d.shape[0], 80):
            dd = d[i:i + 80, j:j + 30]
            a, b = dd > 0.75, dd < 0.25
            if a.sum() > 40 and b.sum() > 40:
                co = np.median(old[i:i + 80, j:j + 30][a]) - np.median(old[i:i + 80, j:j + 30][b])
                cn = np.median(new[i:i + 80, j:j + 30][a]) - np.median(new[i:i + 80, j:j + 30][b])
                olds.append(co)
                news.append(cn)
                diffs.append(cn - co)
diffs, olds, news = map(np.array, (diffs, olds, news))
out["paired_contrast"] = {"n": len(diffs), "old": float(olds.mean()), "new": float(news.mean()), "new_minus_old": float(diffs.mean()), "sem": float(diffs.std() / np.sqrt(len(diffs)))}
print(out["paired_contrast"])
json.dump(out, open(f"{OUT}/aligned.json", "w"), indent=1)

fig, axes = plt.subplots(2, 4, figsize=(10, 9.6), dpi=150, facecolor="white", gridspec_kw={"wspace": 0.06, "hspace": 0.16, "left": 0.07, "right": 0.985, "top": 0.88, "bottom": 0.06})
fig.text(0.07, 0.945, "Same part of the picture on both discs", fontsize=13, fontweight="bold", color=INK)
fig.text(0.07, 0.915, "Average of scans 1 and 2. Left edge: original near the centre of the dark region, bridged near its edge. Right edge: the reverse. Difference = bridged minus original.", fontsize=8.6, color=MUTED)
for r, w in enumerate(phis):
    phi = phis[w]
    old = (strips[(w, (0, "old"))] + strips[(w, (1, "old"))]) / 2
    new = (strips[(w, (0, "new"))] + strips[(w, (1, "new"))]) / 2
    v, dy, dx = register(old, new)
    new = np.roll(np.roll(new, dy, 0), dx, 1)
    ext = [0, phi[-1] - phi[0], RS[-1], RS[0]]
    for c, (title, im, lo, hi) in enumerate((("Design", designs[w], 0, 1), ("Original", old, -0.35, 0.35), ("Bridged", new, -0.35, 0.35), ("Difference", new - old, -0.35, 0.35))):
        ax = axes[r, c]
        ax.imshow(im, cmap="gray", vmin=lo, vmax=hi, extent=ext, aspect="auto")
        ax.tick_params(length=2, labelsize=8, colors=MUTED)
        for sp in ax.spines.values():
            sp.set_color("#d8dee4")
        if r == 0:
            ax.set_title(title, fontsize=10, color=INK)
        if c == 0:
            ax.set_ylabel("radius (mm)", fontsize=9, color=INK)
        else:
            ax.set_yticklabels([])
        ax.set_xlabel("angle (deg)", fontsize=8.5, color=INK)
fig.savefig(f"{OUT}/aligned.png", facecolor="white")
