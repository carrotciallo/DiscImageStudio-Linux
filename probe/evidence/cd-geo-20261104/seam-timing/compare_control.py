# Are the ripples near LBA 60000-70000 special? Same method on LBA 100000-110000.
import re, numpy as np
D = "evidence/cd-geo-20261104/seam-timing/"
def load(f):
    t = open(D + f, encoding="utf-8", errors="ignore").read()
    return {int(a): float(x) for a, r, x, s in re.findall(r"lba\s+(\d+)\s+r\s+([\d.]+) mm\s+residual\s+([+-][\d.]+) deg\s+\+/-\s+([\d.]+)", t)}
def seg(a, b, name, show=True):
    A, B = load(a), load(b); k = sorted(set(A) & set(B))
    x = np.array(k, float); p = np.array([A[i] for i in k]); q = np.array([B[i] for i in k]); off = np.mean(p - q); q = q + off; m = (p + q) / 2
    noise = (p - q).std() / 2                      # noise of the two-sweep mean
    H = np.c_[np.ones_like(x), (x - x.mean()) / 1e4]; c, *_ = np.linalg.lstsq(H, m, rcond=None); e = m - H @ c
    H2 = np.c_[H, ((x - x.mean()) / 1e4) ** 2]; c2, *_ = np.linalg.lstsq(H2, m, rcond=None); e2 = m - H2 @ c2
    print(f"{name}: {len(k)} points, sweeps differ {(p - q).std():.3f} rms, noise of mean {noise:.3f}; slope {c[1]:+.3f} deg/10k; after line {e.std():.3f}, after parabola {e2.std():.3f}; corr of the two sweeps after line {np.corrcoef(p - H @ np.linalg.lstsq(H, p, rcond=None)[0], q - H @ np.linalg.lstsq(H, q, rcond=None)[0])[0, 1]:.2f}; max point-to-point {np.abs(np.diff(m)).max():.2f}")
    if show:
        print(" ".join(f"{int(i / 100)}:{v:+.2f}" for i, v in zip(k, m)))
seg("sweep2.log", "sweep3.log", "seam 60000-70000")
seg("control_fwd.log", "control_rev.log", "control 100000-110000")
