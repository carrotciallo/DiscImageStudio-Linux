import sys, time, itertools, numpy as np
import os; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import discprobe.efmplus as E

def levels_for(seq, frames=2):
    data = np.array([seq[i % len(seq)] for i in range(91 * frames)], np.uint8)
    b, out = E.Boundary(), []
    for f in range(frames):
        lv, b = E.encode_frame(data[91 * f:91 * (f + 1)], 1 + f % 4, b)
        out.append(lv[32:])            # drop the sync code
    return out

def score(seq, P):
    tot = 0.0; fund = 0.0
    for lv in levels_for(seq):
        x = 2.0 * lv - 1; x = x - x.mean()
        n = np.arange(x.size)
        fund += abs(np.sum(x * np.exp(-2j * np.pi * n / P))) ** 2 / x.size
        tot += np.sum(x * x)
    return 2 * fund / tot   # fraction of AC power in the +-1/P lines

def runs(seq):
    lv = np.concatenate(levels_for(seq))
    r = np.diff(np.flatnonzero(np.diff(lv.astype(int)) != 0))
    return r.mean(), r.min(), r.max()

t = time.time()
print("single bytes, fraction of power at 1/16 and 1/32:")
res = []
for q in range(256):
    try: res.append((score([q], 16), score([q], 32), q))
    except ValueError: pass
for s16, s32, q in sorted(res, reverse=True)[:4]: print(f"  {q:02X}  P16 {s16:.2f}  P32 {s32:.2f}  runs {runs([q])}")
for s16, s32, q in sorted(res, key=lambda r: -r[1])[:6]: print(f"  {q:02X}  P16 {s16:.2f}  P32 {s32:.2f}  runs {runs([q])}")
print("time", round(time.time() - t, 1))

def multi(seq, Ps):
    lvs = levels_for(seq)
    out = []
    for P in Ps:
        tot = fund = 0.0
        for lv in lvs:
            x = 2.0 * lv - 1; x = x - x.mean(); n = np.arange(x.size)
            fund += abs(np.sum(x * np.exp(-2j * np.pi * n / P))) ** 2 / x.size; tot += np.sum(x * x)
        out.append(2 * fund / tot)
    return out

t = time.time(); best = {32: [], 64: []}
for a in range(256):
    for b in range(256):
        try: s32, s64 = multi([a, b], (32, 64))
        except ValueError: continue
        best[32].append((s32, a, b)); best[64].append((s64, a, b))
for P in (32, 64):
    best[P].sort(reverse=True)
    print(f"pairs, P{P}:", [(f"{a:02X}{b:02X}", round(s, 3)) for s, a, b in best[P][:8]], flush=True)
print("pairs time", round(time.time() - t))
rng = np.random.default_rng(0); t = time.time(); b48 = []; b96 = []
for _ in range(150000):
    s = [int(x) for x in rng.integers(0, 256, 3)]
    try: s48, s96 = multi(s, (48, 96))
    except ValueError: continue
    b48.append((s48, *s)); b96.append((s96, *s))
b48.sort(reverse=True); b96.sort(reverse=True)
print("triples, P48:", [(f"{a:02X}{b:02X}{c:02X}", round(s, 3)) for s, a, b, c in b48[:8]])
print("triples, P96:", [(f"{a:02X}{b:02X}{c:02X}", round(s, 3)) for s, a, b, c in b96[:8]])
print("triples time", round(time.time() - t))
