# Two scan sets of grid disc 2 (9 pages, then 16 pages from "cd v2.pdf"), and what the timing-only correction predicts for disc 3.
import sys, numpy as np
sys.path.insert(0, r"D:\disc-probe")
from discprobe import imagedisc
G = "evidence/cd-geo-20261104/"
c7 = imagedisc.load_correction(G + "full-2080rpm/correction_phi7.json"); q = imagedisc.load_correction(G + "full-2080rpm/correction_quadratic.json")
def stack(f, minpeak=0):
    z = np.load(f); phi = z["phi"]; good = z["peak"] >= minpeak
    phi = phi[good]; phi = phi - np.nanmedian(phi, axis=1, keepdims=True)
    return z["edges"], phi, z["peak"], z["rot"]
e, p3, pk3, rot3 = stack(G + "grid2-rescan/bins_disc2_rescan16.npz", 2.75)
_, p2, pk2, rot2 = stack(G + "grid2-rescan/bins_disc2.npz", 2.75)
print("scans used: disc 3", len(p3), "of", len(pk3), " disc 2", len(p2), "of", len(pk2))
def binned(p, w):
    m = e[:-1] + 0.125; out = []; cen = np.arange(26 + w / 2, 56, w)
    for c in cen:
        s = np.abs(m - c) < w / 2
        v = np.nanmedian(p[:, s], axis=1)              # one number per scan
        out.append((c, np.nanmedian(v), 1.4826 * np.nanmedian(np.abs(v - np.nanmedian(v))) / np.sqrt(np.isfinite(v).sum())))
    return np.array(out)
b3, b2 = binned(p3, 2.5), binned(p2, 2.5)
print("2.5 mm bins\n  r     disc2   disc3  (+/-)  predicted change  disc2+change")
pred = c7(b2[:, 0]) - q(b2[:, 0]); pred -= pred.mean()
for a, b, d in zip(b2, b3, pred):
    print(f"{a[0]:6.2f} {a[1]:+6.2f} {b[1]:+6.2f} {b[2]:5.2f}   {-d:+6.2f}   {a[1] - d:+6.2f}")
mid = lambda v: v - v.mean()
print("rms disc2 %.3f p-p %.3f | disc3 %.3f p-p %.3f" % (b2[:, 1].std(), np.ptp(b2[:, 1]), b3[:, 1].std(), np.ptp(b3[:, 1])))
print("disc3 vs disc2-pred corr %.2f; disc3 vs disc2 corr %.2f" % (np.corrcoef(b3[:, 1], b2[:, 1] - pred)[0, 1], np.corrcoef(b3[:, 1], b2[:, 1])[0, 1]))
print("\n0.5 mm bins, disc 2 and disc 3")
c2, c3 = binned(p2, 0.5), binned(p3, 0.5)
for a, b in zip(c2, c3):
    if 29 <= a[0] <= 38 or 46 <= a[0] <= 54:
        print(f"{a[0]:6.2f} {a[1]:+6.2f} ({a[2]:.2f})   {b[1]:+6.2f} ({b[2]:.2f})")
print("\n0.25 mm bins disc 3, 31.5-35")
d3 = binned(p3, 0.25)
for b in d3:
    if 31.5 <= b[0] <= 35:
        print(f"{b[0]:6.2f} {b[1]:+6.2f} ({b[2]:.2f})")
