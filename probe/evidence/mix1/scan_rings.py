"""Per-ring brightness of the mix1 scan. Rings are full circles, so only scanner angle matters."""
import json
import sys

import cv2
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
D = sys.argv[1]
RINGS = json.load(open("D:/disc-probe/iso/mix1.rings.json", encoding="utf-8"))
TEX = RINGS["textures"]
DPI = 600
MM = DPI / 25.4


def circle(img):
    small = img[40:-40, 40:-40]
    paper = np.median(small.reshape(-1, 3)[::97], axis=0)
    d = np.abs(small.astype(float) - paper).sum(axis=2)
    m = (d > 60).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((41, 41), np.uint8))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)[:, 0, :].astype(float) + 40
    for _ in range(4):
        A = np.c_[2 * c, np.ones(len(c))]
        s = np.linalg.lstsq(A, (c ** 2).sum(axis=1), rcond=None)[0]
        r = np.sqrt(s[2] + s[0] ** 2 + s[1] ** 2)
        res = np.hypot(c[:, 0] - s[0], c[:, 1] - s[1]) - r
        c = c[np.abs(res) < max(3, 2.5 * res.std())]
    return s[0], s[1], r, res.std()


def unwrap(img, cx, cy, scale, dr=0.05, dth=0.5, rmin=20.0, rmax=60.0):
    rs = np.arange(rmin, rmax, dr)
    ths = np.deg2rad(np.arange(0, 360, dth))
    R, T = np.meshgrid(rs, ths, indexing="ij")
    mapx = (cx + R * scale * np.cos(T)).astype(np.float32)
    mapy = (cy + R * scale * np.sin(T)).astype(np.float32)
    return rs, np.rad2deg(ths), cv2.remap(img, mapx, mapy, cv2.INTER_AREA)


def linear(rgb):
    x = rgb.astype(float) / 255
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


out = {}
for page in (0, 1):
    img = cv2.cvtColor(cv2.imread(f"{D}/p{page}.png"), cv2.COLOR_BGR2RGB)
    cx, cy, rp, sd = circle(img)
    scale = MM
    print(f"page {page}: centre ({cx:.1f},{cy:.1f}) r {rp:.1f} px = {rp/MM:.2f} mm at {DPI} dpi, edge sd {sd:.1f} px, {scale:.2f} px/mm")
    rs, ths, pol = unwrap(img, cx, cy, scale)
    lin = linear(pol)
    Y = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
    cv2.imwrite(f"{D}/polar_{page}.jpg", cv2.cvtColor(pol, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
    # angle bins: distance from the dark wedge axis (scanner x axis)
    dist = np.abs(((ths + 90) % 180) - 90)
    bins = [(0, 5), (5, 10), (10, 15), (15, 25), (25, 45), (45, 90)]
    table = {}
    for rr in RINGS["rings"]:
        sel = (rs >= rr["r_start_mm"] + 0.2) & (rs < rr["r_end_mm"] - 0.2)
        row = {}
        for lo, hi in bins:
            a = (dist >= lo) & (dist < hi)
            row[f"{lo}-{hi}"] = float(Y[sel][:, a].mean())
        table[rr["index"]] = {"texture": rr["texture"], "group": rr["group"], "r": rr["r_start_mm"], **row}
    out[page] = table
    print(f"{'tex':6} " + " ".join(f"{lo}-{hi:<5}" for lo, hi in bins) + "   (mean ratio to the same group's RND ring, 3 groups)")
    for t in TEX:
        cells = []
        for lo, hi in bins:
            k = f"{lo}-{hi}"
            vals = []
            for g in range(RINGS["groups"]):
                ring = [v for v in table.values() if v["texture"] == t and v["group"] == g]
                ref = [v for v in table.values() if v["texture"] == "RND" and v["group"] == g]
                if ring and ref:
                    vals.append(ring[0][k] / ref[0][k])
            cells.append(f"{np.mean(vals):.2f}±{np.std(vals):.2f}" if vals else "  -  ")
        print(f"{t:6} " + " ".join(f"{c:9}" for c in cells))
json.dump(out, open(f"{D}/rings.json", "w"), indent=0)
