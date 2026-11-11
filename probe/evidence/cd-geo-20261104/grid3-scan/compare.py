# Grid disc 3 (degree 7 timing-only correction) against grid disc 2 (quadratic), radial lines only.
import sys, numpy as np
sys.path.insert(0, r"D:\disc-probe")
from discprobe import imagedisc
G = "evidence/cd-geo-20261104/"
c7 = imagedisc.load_correction(G + "full-2080rpm/correction_phi7.json"); q = imagedisc.load_correction(G + "full-2080rpm/correction_quadratic.json")
MINPEAK = 2.75
def stack(f):
    z = np.load(f); good = z["peak"] >= MINPEAK; print(f.split("/")[-1], "scans used", list(z["scans"][good]))
    phi = z["phi"][good]; return z["edges"], phi - np.nanmedian(phi, axis=1, keepdims=True)
e, p3 = stack(G + "grid3-scan/bins_disc3.npz")
_, a = stack(G + "grid2-rescan/bins_disc2.npz"); _, b = stack(G + "grid2-rescan/bins_disc2_rescan16.npz"); p2 = np.vstack([a, b])
m = e[:-1] + 0.125
def binned(p, w):
    out = []
    for c in np.arange(26 + w / 2, 56, w):
        v = np.nanmedian(p[:, np.abs(m - c) < w / 2], axis=1)
        out.append((c, np.nanmedian(v), 1.4826 * np.nanmedian(np.abs(v - np.nanmedian(v))) / np.sqrt(np.isfinite(v).sum())))
    return np.array(out)
b2, b3 = binned(p2, 2.5), binned(p3, 2.5)
pred = c7(b2[:, 0]) - q(b2[:, 0]); pred -= pred.mean()
print("  r     disc2  disc3 (+/-)   disc3-disc2  predicted change")
for x, y, d in zip(b2, b3, pred):
    print(f"{x[0]:6.2f} {x[1]:+6.2f} {y[1]:+6.2f} {y[2]:5.2f}   {y[1] - x[1]:+6.2f}     {-d:+6.2f}")
ok = np.isfinite(b3[:, 1]) & np.isfinite(b2[:, 1]); ch = (b3[:, 1] - b2[:, 1])[ok]
print("disc2 rms %.3f p-p %.3f | disc3 rms %.3f p-p %.3f" % (np.nanstd(b2[:, 1]), np.ptp(b2[ok, 1]), np.nanstd(b3[:, 1]), np.ptp(b3[ok, 1])))
print("measured change vs predicted: corr %.2f, slope %.2f; rms of (change - predicted) %.3f" % (np.corrcoef(ch, -pred[ok])[0, 1], np.polyfit(-pred[ok], ch, 1)[0], np.std(ch + pred[ok])))
print("\n0.5 mm bins: r, disc2, disc3")
c2, c3 = binned(p2, 0.5), binned(p3, 0.5)
for x, y in zip(c2, c3):
    print(f"{x[0]:6.2f} {x[1]:+6.2f} {y[1]:+6.2f} ({y[2]:.2f})")
print("\ndisc 3 0.25 mm, 31.5-35")
for y in binned(p3, 0.25):
    if 31.5 <= y[0] <= 35: print(f"{y[0]:6.2f} {y[1]:+6.2f} ({y[2]:.2f})")
