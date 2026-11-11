"""Can any byte choice push pit/land coverage away from 50 % on a DSV-controlled burner?

  python evidence/coverage/greedy_coverage.py   (~40 min; output in greedy_coverage_output.txt)

Pure textures and random data, then a greedy search that, at every free byte, tries all
256 values through the exact encoder (discprobe/efmplus.py, incl. the drive's SYNC and
table choices) and keeps the one with the most land so far.  PI parity and PO rows are
stand-in random bytes.
"""
import os, sys, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from discprobe.efmplus import encode_rows, encode_frame, Boundary, ROW_SYNC, main
rng = np.random.default_rng(1)

def stats(levels, label):
    f = levels.reshape(-1, 1488).mean(1)
    w5 = levels[: len(levels)//(1488*5)*1488*5].reshape(-1, 1488*5).mean(1)
    print(f"{label:28s} land {levels.mean():.3f}  per-frame min/max {f.min():.2f}/{f.max():.2f}  5-frame windows {w5.min():.3f}-{w5.max():.3f}")

def rows_of(byte, n=26):
    r = np.full((n, 182), byte, np.uint8)
    r[:, 172:] = rng.integers(0, 256, (n, 10))      # PI parity ~ random
    r[12::13] = rng.integers(0, 256, (len(r[12::13]), 182))  # PO row ~ random
    return r

for q in (0xA5, 0x92, 0xB9, 0x66):
    lv, _ = encode_rows(rows_of(q)); stats(lv, f"pure Q={q:02X}")
lv, _ = encode_rows(rng.integers(0, 256, (26, 182))); stats(lv, "random bytes")

# Greedy: at every free byte, pick the candidate that maximises land in the frame prefix
# as actually encoded (incl. the drive's DSV choices).  Target: as much land as possible.
def greedy_frame(prefix_fixed, cat, b, target_land=True, cands=range(256)):
    data = list(prefix_fixed)
    chosen = []
    for pos in range(91):
        if pos >= len(data) or data[pos] is None:
            best, bv = None, -1
            for c in cands:
                trial = chosen + [c] + [0x92] * (90 - pos)   # filler for the remainder
                lv, _ = encode_frame(bytes(trial), cat, b)
                v = lv[: 32 + 16 * (pos + 1)].sum() if target_land else -lv[: 32 + 16 * (pos + 1)].sum()
                if v > bv: best, bv = c, v
            chosen.append(best)
        else:
            chosen.append(data[pos])
    return chosen

# candidate pool: bytes whose state-1..4 main words are most land-heavy or pit-heavy for either polarity
cands = list(range(256))
b = Boundary(); out = []
free_frames = 0
for row in range(26):
    for half in range(2):
        cat = ROW_SYNC[row % 13][half]
        if row % 13 == 12:   # PO row: random
            data = list(rng.integers(0, 256, 91))
        else:
            fixed = [None] * 91
            if half == 1:
                for k in range(81, 91): fixed[k] = int(rng.integers(0, 256))  # PI
            data = greedy_frame(fixed, cat, b, True, cands)
        lv, b = encode_frame(bytes(data), cat, b)
        out.append(lv)
        print(f"row {row:2d}/{half}: land {lv.mean():.3f}  dsv after {b.dsv:6d}", flush=True)
stats(np.concatenate(out), "greedy max-land (2 sectors)")
