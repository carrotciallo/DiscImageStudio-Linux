"""Picture contrast against scanner angle, per disc and scan. Separates a disc difference from wedge position."""
import json
import sys

import cv2
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
D = sys.argv[1]
MM = 600 / 25.4
DTH, DR = 0.1, 0.05
SCALE = 10.1
RS = np.arange(25.5, 57.5, DR)
CENTRES = {(0, "new"): (2293.6, 2351.7), (0, "old"): (2281.1, 5292.0), (1, "old"): (2456.4, 1820.8), (1, "new"): (2339.4, 5277.6),
           (2, "old"): (2465.6, 1723.8), (2, "new"): (2437.0, 5209.5)}
res = json.load(open(f"{D}/compare3.json"))
design = cv2.imread("D:/disc-probe/iso/dense.preview.png", cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
H = design.shape[0] / 2
AL = np.arange(-20, 20, DTH)
EDGES = [-14, -10, -6, -2, 2, 6, 10, 14]


def linear(rgb):
    x = rgb.astype(np.float32) / 255
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def polar(img, c, ths):
    R, T = np.meshgrid(RS, np.deg2rad(ths), indexing="ij")
    return cv2.remap(img, (c[0] + R * MM * np.cos(T)).astype(np.float32), (c[1] + R * MM * np.sin(T)).astype(np.float32), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def highpass(y):
    ly = np.log(np.maximum(y, 1e-4))
    return ly - cv2.GaussianBlur(ly, (0, 0), sigmaX=3.0 / DTH, sigmaY=2.0 / DR, borderType=cv2.BORDER_REFLECT)


table = {}
for page in (0, 1, 2):
    L = linear(cv2.imread(f"{D}/p{page}.png")[:, :, ::-1])
    Y = (0.2126 * L[..., 0] + 0.7152 * L[..., 1] + 0.0722 * L[..., 2]).astype(np.float32)
    for k, c in CENTRES.items():
        if k[0] != page:
            continue
        th = res[str(k)]["theta"]
        rows = []
        for lo, hi in zip(EDGES[:-1], EDGES[1:]):
            vals = []
            for off in (0, 180):
                hp = np.clip(highpass(polar(Y, c, AL + off)), -0.35, 0.35)
                R, T = np.meshgrid(RS, np.deg2rad(AL + off + th), indexing="ij")
                d = cv2.remap(design, (H + R * SCALE * np.cos(T)).astype(np.float32), (H + R * SCALE * np.sin(T)).astype(np.float32), cv2.INTER_AREA)
                sel = (AL >= lo) & (AL < hi)
                dd, ss = d[:, sel], hp[:, sel]
                for i in range(0, dd.shape[0], 80):
                    for j in range(0, dd.shape[1], 40):
                        x, s = dd[i:i + 80, j:j + 40], ss[i:i + 80, j:j + 40]
                        a, b = x > 0.75, x < 0.25
                        if a.sum() > 40 and b.sum() > 40:
                            vals.append(np.median(s[a]) - np.median(s[b]))
            rows.append((float(np.mean(vals)) if vals else None, float(np.std(vals) / np.sqrt(len(vals))) if vals else None, len(vals)))
        table[str(k)] = rows
        print(k, " ".join(f"{m:.3f}±{e:.3f}({n})" if m is not None else "-" for m, e, n in rows), flush=True)
print("bins", EDGES)
print("\nmean over scans, per bin")
for role in ("old", "new"):
    out = []
    for b in range(len(EDGES) - 1):
        v = [table[str((p, role))][b][0] for p in range(3) if table[str((p, role))][b][0] is not None]
        out.append(np.mean(v))
    print(role, " ".join(f"{x:.3f}" for x in out))
json.dump(table, open(f"{D}/profile.json", "w"), indent=0)
