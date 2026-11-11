# Look for a seam near 33.8 mm: the angle of the radial lines in narrow radius bins, on scans of
# the grid discs, with a straight line in r removed either side of a candidate step.
# usage: grid_seam.py PREFIX L_MM SCAN [SCAN ...]   (L_MM = along-track offset left on that disc)
import sys, numpy as np
sys.path.insert(0, r"D:\disc-probe")
from discprobe import scan
from scipy.ndimage import uniform_filter1d
prefix, L = sys.argv[1], float(sys.argv[2]); scans = [int(s) for s in sys.argv[3:]]
px = 600 / 25.4; NT = 14400; res = 360 / NT
R = np.arange(28, 41, 0.05); R = R[np.abs((R + 2.5) % 5 - 2.5) > 0.45]
TH = np.arange(NT) * 2 * np.pi / NT
ang = np.degrees(TH)[None, :]; d = np.abs(((ang + 15) % 30) - 15)
D = np.where(np.radians(d) * R[:, None] < 0.3, -1.0, 0.0); D -= D.mean(1, keepdims=True)
Fd = np.fft.rfft(D, axis=1); Fd[:, :24] = 0; k = np.arange(Fd.shape[1])
edges = np.arange(29, 39.01, 0.5); mid = (edges[1:] + edges[:-1]) / 2
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
    c = np.fft.irfft(C.sum(0), n=NT); j0 = int(c.argmax())
    phi = []
    for a, b in zip(edges[:-1], edges[1:]):
        m = (R >= a) & (R < b)
        if not m.any():
            phi.append(np.nan); continue
        cc = np.fft.irfft(C[m].sum(0), n=NT)
        idx = (np.arange(-60, 61) + j0) % NT; p = int(np.argmax(cc[idx])); jj = idx[p]
        y0, y1, y2 = cc[(jj - 1) % NT], cc[jj], cc[(jj + 1) % NT]
        phi.append((((jj - j0 + NT // 2) % NT - NT // 2) + 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2)) * res)
    out.append(phi); print(f"scan {i}: rotation {j0 * res:.2f}  " + " ".join(f"{p:+.2f}" for p in phi), flush=True)
M = np.array(out); med = np.nanmedian(M, axis=0)
print("radius    " + " ".join(f"{m:5.2f}" for m in mid))
print("median    " + " ".join(f"{v:+5.2f}" for v in med))
print("scan std  " + " ".join(f"{v:5.2f}" for v in np.nanstd(M, axis=0)))
ok = np.isfinite(med); x = mid[ok]; y = med[ok]
def fit(rs):
    A = [np.ones_like(x), x - 34, (x - 34) ** 2]
    if rs is not None:
        A.append((x >= rs).astype(float))
    A = np.array(A).T; c, *_ = np.linalg.lstsq(A, y, rcond=None); e = y - A @ c
    return c, float(e @ e)
c0, s0 = fit(None)
print(f"no step: rms {np.sqrt(s0 / len(x)):.3f} deg")
for rs in np.arange(31.25, 37, 0.5):
    c, s = fit(rs)
    print(f"  step at {rs:5.2f} mm: {c[-1]:+.3f} deg ({np.radians(c[-1]) * rs:+.3f} mm), rms {np.sqrt(s / len(x)):.3f}")
