"""Read a colour4 photo, black out everything but the disc, and draw what the reader found.
Filtered photos: geometry and IDs only, no colour is measured. Writes a JPEG with no EXIF."""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "D:/disc-probe")
from discprobe import beacondisc as bd, beaconread as br  # noqa: E402

name, full_px_mm, out_img, out_json = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4]
im = ImageOps.exif_transpose(Image.open(os.path.join(os.path.expanduser("~"), "Downloads", name + ".jpeg"))).convert("RGB")
full = np.asarray(im)


def highpass(rgb, sigma_px, norm):
    """Log colour minus a blurred copy, optionally divided by the local contrast. Only for reading."""
    lg = np.log(rgb.astype(np.float32) + 2.0)
    hp = lg - cv2.GaussianBlur(lg, (0, 0), sigma_px)
    if norm:
        rms = np.sqrt(cv2.GaussianBlur(hp * hp, (0, 0), sigma_px * 2) + 1e-3)
        hp = hp / rms * 0.35
    return np.clip(np.exp(hp) * 90, 0, 255).astype(np.uint8)


best = None
for target in (14.0, 18.0):
    if target > full_px_mm * 1.05:
        continue
    f = target / full_px_mm
    small = cv2.resize(full, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    for label, sig_mm, norm in (("plain", 0, False), ("hp3", 3.0, False), ("hp5", 5.0, False), ("hp3n", 3.0, True), ("hp6n", 6.0, True)):
        use = small if not sig_mm else highpass(small, sig_mm * target, norm)
        res = br.read_disc(use, target)
        res["scale"] = f
        res["target"] = target
        res["method"] = label
        n = sum(t["read"] for t in res["tiles"])
        print(f"{name} {target} px/mm {label}: seed {res['seed_tiles']}, {n}/27 read, "
              f"fit rms {res.get('fit_rms_mm', float('nan')):.3f} mm over {res.get('fit_points', 0)} pts", flush=True)
        if best is None or n > sum(t["read"] for t in best["tiles"]):
            best = res
print("best:", best["method"], best["target"])
if not best["H"]:
    from discprobe import tilephoto
    hub_preview = tuple(float(v) for v in sys.argv[5:7])
    target = min(14.0, full_px_mm)
    f = target / full_px_mm
    small = cv2.resize(full, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    grey = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    hub = (hub_preview[0] * small.shape[1] / 1100, hub_preview[1] * small.shape[1] / 1100)
    pts = tilephoto.rim_points(grey, hub)
    e, nin = tilephoto.ransac_ellipse(pts)
    print(f"rim: {len(pts)} points, {nin} on the ellipse, axes {e[2]:.0f} {e[3]:.0f} px")
    edges, lg = br.edge_map(small)
    scan = []
    for psi in np.radians(np.arange(0, 360, 0.5)):
        H0 = tilephoto.affine_h(e, psi, False)
        t = br.read_guided(lg, H0)
        scan.append((sum(x["read"] for x in t), -sum(x["errors"] for x in t if x["bits_read"] == 16), float(psi)))
    scan.sort(reverse=True)
    print("best rotations (read, -errors, deg):", [(a, b, round(math.degrees(c), 1)) for a, b, c in scan[:5]])
    print("reads at a wrong rotation, median and max:", int(np.median([x[0] for x in scan])), scan[len(scan) // 3][0])
    H = tilephoto.affine_h(e, scan[0][2], False)
    peaks = np.array([q[:2] for q in br.find_bullseyes(edges, target)]).reshape(-1, 2)
    tiles = br.read_guided(lg, H)
    for _ in range(4):
        src, dst = [], []
        for t in tiles:
            if not t["read"]:
                continue
            fc = bd.finder_centres(t["ring"], t["sector"])
            for k in "ABC":
                d = np.linalg.norm(peaks - np.array(t["finders_px"][k]), axis=1)
                if d.size and d.min() < 1.5 * target:
                    r, a = fc[k]
                    src.append((r * math.cos(a), r * math.sin(a)))
                    dst.append(peaks[int(d.argmin())])
        if len(src) >= 8:
            H = br.fit_homography(np.array(src), np.array(dst))
            tiles = br.read_guided(lg, H)
    print(f"after refit: {sum(t['read'] for t in tiles)}/27 read over {len(src)} points")
    best = {"seed_tiles": 0, "H": H.tolist(), "tiles": tiles, "scale": f, "target": target, "method": "rim+rotation"}
json.dump(best, open(out_json, "w", encoding="utf-8"), indent=1)
S = np.diag([1 / best["scale"], 1 / best["scale"], 1.0])
H = S @ np.array(best["H"])
W, Hh = im.size


def poly(r, n=720):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return [tuple(p) for p in br.project(H, r * np.cos(a), r * np.sin(a))]


m = Image.new("L", im.size, 0)
d = ImageDraw.Draw(m)
d.polygon(poly(60.2), fill=255)
d.polygon(poly(19.6), fill=0)
m = m.resize(im.size)
base = Image.composite(im, Image.new("RGB", im.size, (0, 0, 0)), m)
view_scale = 1300 / max(W, Hh)
draw_scale = 3
canvas = Image.new("RGBA", im.size, (0, 0, 0, 0))
dd = ImageDraw.Draw(canvas)
px_mm = full_px_mm
font = ImageFont.truetype(r"C:\Windows\Fonts\consolab.ttf", max(14, int(2.1 * px_mm)))
GREEN, GREY = (90, 255, 170, 255), (255, 255, 255, 110)
lw = max(2, int(0.13 * px_mm))
for t in best["tiles"]:
    ring, sector = t["ring"], t["sector"]
    col = GREEN if t["read"] else GREY
    r_in, dr, a0, dth = bd._tile_frame(ring, sector)
    arc = np.linspace(a0 + 0.5 / (r_in + dr), a0 + dth - 0.5 / (r_in + dr), 24)
    pts = np.r_[np.c_[r_in * np.cos(arc), r_in * np.sin(arc)], np.c_[(r_in + dr) * np.cos(arc[::-1]), (r_in + dr) * np.sin(arc[::-1])]]
    line = [tuple(p) for p in br.project(H, pts[:, 0], pts[:, 1])]
    dd.line(line + line[:1], fill=col, width=lw if t["read"] else max(1, lw // 2))
    if t["read"]:
        for k, (r, a) in bd.finder_centres(ring, sector).items():
            c = br.project(H, r * math.cos(a), r * math.sin(a))
            R = 1.7 * px_mm
            dd.ellipse((c[0] - R, c[1] - R, c[0] + R, c[1] + R), outline=GREEN, width=lw)
        mid_r, mid_a = r_in + dr / 2, a0 + dth * (bd.ID_FRAC / 2 + 0.02)
        c = br.project(H, mid_r * math.cos(mid_a), mid_r * math.sin(mid_a))
        label = f"#{t['id']}"
        bb = dd.textbbox((0, 0), label, font=font)
        pad = int(0.25 * px_mm)
        x, y = c[0] - (bb[2] - bb[0]) / 2, c[1] - (bb[3] - bb[1]) / 2
        dd.rounded_rectangle((x - pad, y - pad + bb[1], x + bb[2] - bb[0] + pad, y + bb[3] + pad), radius=pad, fill=(0, 0, 0, 200))
        dd.text((x - bb[0], y), label, font=font, fill=GREEN)
for a_deg in bd.MARK_ANGLES_DEG:
    a = math.radians(a_deg)
    c = br.project(H, bd.MARK_RADIUS_MM * math.cos(a), bd.MARK_RADIUS_MM * math.sin(a))
    R = 1.9 * px_mm
    dd.ellipse((c[0] - R, c[1] - R, c[0] + R, c[1] + R), outline=(255, 255, 255, 110), width=max(1, lw // 2))
out = Image.alpha_composite(base.convert("RGBA"), canvas).convert("RGB")
q = np.array(poly(60.2))
x0, y0, x1, y1 = q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()
pad = 20
box = (max(0, int(x0 - pad)), max(0, int(y0 - pad)), min(W, int(x1 + pad)), min(Hh, int(y1 + pad)))
out = out.crop(box)
out.thumbnail((1200, 1200), Image.LANCZOS)
out.save(out_img, quality=90, optimize=True, exif=b"")
print(out.size, os.path.getsize(out_img) // 1024, "KB", "read ids:", [t["id"] for t in best["tiles"] if t["read"]])
