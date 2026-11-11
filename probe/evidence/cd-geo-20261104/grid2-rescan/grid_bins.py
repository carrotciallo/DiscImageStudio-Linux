# Radial line angle per 0.25 mm radius bin for each scan of a CD grid disc (radial lines only, dark
# sectors only), saved for later averaging.
# usage: grid_bins.py OUT.npz PREFIX L_MM SCAN [SCAN ...]
import sys, numpy as np
sys.path.insert(0, r"D:\disc-probe")
from multiprocessing import Pool
from discprobe import scan
from scipy.ndimage import uniform_filter1d

px = 600 / 25.4; NT = 14400; res = 360 / NT
EDGES = np.arange(26, 56.001, 0.25)


def one(a):
    prefix, L, i = a
    R = np.arange(25.5, 56.5, 0.05); R = R[np.abs((R + 2.5) % 5 - 2.5) > 0.45]
    TH = np.arange(NT) * 2 * np.pi / NT
    ang = np.degrees(TH)[None, :]; d = np.abs(((ang + 15) % 30) - 15)
    D = np.where(np.radians(d) * R[:, None] < 0.3, -1.0, 0.0); D -= D.mean(1, keepdims=True)
    Fd = np.fft.rfft(D, axis=1); Fd[:, :24] = 0; k = np.arange(Fd.shape[1])
    img, _ = scan.load_gray(f"{prefix}{i}.png")
    o, _ = scan.locate_disc(img, px); cx, cy = o["cx"], o["cy"]; sy = o["ry"] / o["rx"]
    xx = cx + R[:, None] * px * np.cos(TH); yy = cy - R[:, None] * px * sy * np.sin(TH)
    pol = img[yy.astype(int), xx.astype(int)].astype(float)
    mean = uniform_filter1d(pol, size=321, axis=1, mode="wrap"); hp = (pol - mean) / np.maximum(mean, 1e-3)
    bri = mean[(R > 30) & (R < 50)].mean(0); w = uniform_filter1d((bri < np.percentile(bri, 22)).astype(float), size=81, mode="wrap")
    F = np.fft.rfft(hp * w, axis=1); F[:, :24] = 0
    C = F * np.conj(Fd) * np.exp(1j * 2 * np.pi * k[None, :] * (np.degrees(L / R)[:, None] / 360))
    c = np.fft.irfft(C.sum(0), n=NT); j0 = int(c.argmax()); peak = float(c.max() / c.std())
    phi = []
    for a_, b_ in zip(EDGES[:-1], EDGES[1:]):
        m = (R >= a_) & (R < b_)
        if not m.any():
            phi.append(np.nan); continue
        cc = np.fft.irfft(C[m].sum(0), n=NT)
        idx = (np.arange(-60, 61) + j0) % NT; jj = idx[int(np.argmax(cc[idx]))]
        y0, y1, y2 = cc[(jj - 1) % NT], cc[jj], cc[(jj + 1) % NT]
        phi.append((((jj - j0 + NT // 2) % NT - NT // 2) + 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2)) * res)
    return i, j0 * res, peak, phi


if __name__ == "__main__":
    out, prefix, L = sys.argv[1], sys.argv[2], float(sys.argv[3]); scans = [int(s) for s in sys.argv[4:]]
    with Pool(6) as p:
        r = p.map(one, [(prefix, L, i) for i in scans])
    for i, rot, peak, _ in r:
        print(f"scan {i}: rotation {rot:.2f}, peak/std {peak:.1f}", flush=True)
    np.savez(out, edges=EDGES, phi=np.array([x[3] for x in r]), rot=[x[1] for x in r], peak=[x[2] for x in r], scans=scans)
