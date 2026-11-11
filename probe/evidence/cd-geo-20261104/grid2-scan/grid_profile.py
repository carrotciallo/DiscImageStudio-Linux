# Radial line angle against radius on a grid disc scan, in narrow bins, relative to the design.
# usage: grid_profile.py PREFIX L_MM R_MIN R_MAX BIN_MM SCAN [SCAN ...]
import sys, json, math, numpy as np
sys.path.insert(0, r"D:\disc-probe")
from discprobe import scan
from scipy.ndimage import uniform_filter1d
prefix, L, rmin, rmax, binw = sys.argv[1], *map(float, sys.argv[2:6]); scans = [int(s) for s in sys.argv[6:]]
px = 600 / 25.4; NT = 14400; res = 360 / NT
R = np.arange(rmin - 0.5, rmax + 0.5, 0.05); R = R[np.abs((R + 2.5) % 5 - 2.5) > 0.45]
TH = np.arange(NT) * 2 * np.pi / NT
ang = np.degrees(TH)[None, :]; d = np.abs(((ang + 15) % 30) - 15)
D = np.where(np.radians(d) * R[:, None] < 0.3, -1.0, 0.0); D -= D.mean(1, keepdims=True)
Fd = np.fft.rfft(D, axis=1); Fd[:, :24] = 0; k = np.arange(Fd.shape[1])
edges = np.arange(rmin, rmax + 1e-6, binw); mid = (edges[1:] + edges[:-1]) / 2
f = json.load(open("evidence/cd-geo-20261104/full-2080rpm/summary.json"))["fit"]; b = f["bit_nm_assumed"] * 1e-6
from discprobe import cd
SECTOR = 98 * cd.FRAME_BITS
lba = lambda r: math.pi * ((r / b) ** 2 - f["u"] ** 2) / f["v"] / SECTOR
out = []
for i in scans:
    img, _ = scan.load_gray(f"{prefix}{i}.png")
    o, _ = scan.locate_disc(img, px); cx, cy = o["cx"], o["cy"]; sy = o["ry"] / o["rx"]
    xx = cx + R[:, None] * px * np.cos(TH); yy = cy - R[:, None] * px * sy * np.sin(TH)
    pol = img[yy.astype(int), xx.astype(int)].astype(float)
    mean = uniform_filter1d(pol, size=321, axis=1, mode="wrap"); hp = (pol - mean) / np.maximum(mean, 1e-3)
    bri = mean.mean(0); w = uniform_filter1d((bri < np.percentile(bri, 22)).astype(float), size=81, mode="wrap")
    F = np.fft.rfft(hp * w, axis=1); F[:, :24] = 0
    C = F * np.conj(Fd) * np.exp(1j * 2 * np.pi * k[None, :] * (np.degrees(L / R)[:, None] / 360))
    j0 = int(np.fft.irfft(C.sum(0), n=NT).argmax())
    phi = []
    for a, e in zip(edges[:-1], edges[1:]):
        m = (R >= a) & (R < e)
        if not m.any():
            phi.append(np.nan); continue
        cc = np.fft.irfft(C[m].sum(0), n=NT)
        idx = (np.arange(-60, 61) + j0) % NT; jj = idx[int(np.argmax(cc[idx]))]
        y0, y1, y2 = cc[(jj - 1) % NT], cc[jj], cc[(jj + 1) % NT]
        phi.append((((jj - j0 + NT // 2) % NT - NT // 2) + 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2)) * res)
    out.append(phi)
M = np.array(out); med = np.nanmedian(M, axis=0); mad = np.nanmedian(np.abs(M - med), axis=0)
print("  r mm    LBA     median   mad   per scan")
for r, v, s, row in zip(mid, med, mad, M.T):
    if np.isfinite(v):
        print(f"{r:7.2f} {lba(r):8.0f}  {v:+6.2f} {s:5.2f}  " + " ".join(f"{x:+5.2f}" for x in row))
