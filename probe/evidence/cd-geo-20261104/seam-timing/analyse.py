# Is there a step near LBA 62000 or 66000? Sweeps 2 and 3 use the same reference, in opposite order.
import re, numpy as np
D = "evidence/cd-geo-20261104/seam-timing/"
def load(f):
    t = open(D + f, encoding="utf-8", errors="ignore").read()
    return {int(a): float(x) for a, r, x, s in re.findall(r"lba\s+(\d+)\s+r\s+([\d.]+) mm\s+residual\s+([+-][\d.]+) deg\s+\+/-\s+([\d.]+)", t)}
s2, s3 = load("sweep2.log"), load("sweep3.log")
common = sorted(set(s2) & set(s3))
a = np.array([s2[k] for k in common]); b = np.array([s3[k] for k in common]); off = np.mean(a - b)
print("points", len(common), "offset sweep2-sweep3 %+.3f, rms difference %.3f, so one sweep about %.3f" % (off, (a - b - off).std(), (a - b - off).std() / np.sqrt(2)))
for k, x, y in zip(common, a, b):
    print(f"{k:6d} {x:+5.2f} {y + off:+5.2f}  mean {(x + y + off) / 2:+5.2f}")
for name, y in (("sweep 2", a), ("sweep 3", b), ("mean", (a + b + off) / 2)):
    lba = np.array(common, float); H = np.c_[np.ones_like(lba), (lba - lba.mean()) / 1e4]
    c, *_ = np.linalg.lstsq(H, y, rcond=None); e = y - H @ c
    out = []
    for k in range(3, len(lba) - 3):
        H2 = np.c_[H, (lba >= lba[k]).astype(float)]; c2, *_ = np.linalg.lstsq(H2, y, rcond=None); e2 = y - H2 @ c2
        out.append((float(e2 @ e2), int(lba[k]), float(c2[2])))
    out.sort()
    print(name, "line rms %.3f;" % e.std(), "best steps:", [(l, round(g, 2), round(np.sqrt(s / len(y)), 3)) for s, l, g in out[:3]])
