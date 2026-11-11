"""Search byte sequences whose recorded channel pattern has one strong along-track period.

For each target period P (channel bits) a sequence of k bytes is chosen so that its length
16k is a multiple of P (several periods per repeat lets P fall between multiples of 16T).
Hill climbing on single-byte changes maximises the fraction of AC power at 1/P, measured
through the exact EFMPlus encoder (discprobe/efmplus.py) on realistic rows: 12 header
bytes, 172 data bytes and 10 random PI bytes per row, several start states. The final
score is the minimum over four start states.

    python evidence/coverage/period_search_v2.py > evidence/coverage/period_search_v2.txt
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import discprobe.efmplus as E  # noqa: E402
from discprobe.imagedisc import texture_bytes  # noqa: E402

TARGETS = {20: 5, 24: 3, 28: 7, 40: 5, 56: 7, 80: 5, 96: 6, 112: 7, 128: 8}   # period -> bytes
STARTS = [(0, True), (60, False), (-60, True), (30, False)]


def rows_for(spec, nrows, seed):
    q = texture_bytes(spec, np.array([1000 + seed]))[0]
    rng = np.random.default_rng(seed)
    frame = np.concatenate([rng.integers(0, 256, 12).astype(np.uint8), q[:172 * nrows - 12]])
    return np.hstack([frame.reshape(nrows, 172), rng.integers(0, 256, (nrows, 10)).astype(np.uint8)])


def frac(spec, P, starts, nrows=4):
    vals = []
    for seed, (dsv, land) in enumerate(starts):
        b, tot, fund = E.Boundary(1, dsv, land), 0.0, 0.0
        for i, row in enumerate(rows_for(spec, nrows, seed)):
            for h in range(2):
                lv, b = E.encode_frame(row[91 * h:91 * (h + 1)], E.ROW_SYNC[i % 13][h], b)
                x = 2.0 * lv[32:] - 1
                x -= x.mean()
                n = np.arange(x.size)
                fund += abs(np.sum(x * np.exp(-2j * np.pi * n / P))) ** 2 / x.size
                tot += np.sum(x * x)
        vals.append(2 * fund / tot)
    return min(vals)


def climb(P, k, rng, iters=500):
    seq = list(rng.integers(0, 256, k))
    hexs = lambda s: "".join(f"{int(v):02X}" for v in s)
    try:
        best = frac(hexs(seq), P, STARTS[:2])
    except ValueError:
        best = -1
    for _ in range(iters):
        cand = list(seq)
        cand[int(rng.integers(0, k))] = int(rng.integers(0, 256))
        try:
            s = frac(hexs(cand), P, STARTS[:2])
        except ValueError:
            continue
        if s >= best:
            seq, best = cand, s
    return hexs(seq), best


def main():
    rng = np.random.default_rng(7)
    for P, k in TARGETS.items():
        found = sorted((climb(P, k, rng) for _ in range(4)), key=lambda t: -t[1])
        spec, _ = found[0]
        print(f"P {P:3d}T ({P * 0.1333:.2f} um)  {spec:16s}  fraction at 1/P: robust {frac(spec, P, STARTS, 6):.2f}",
              flush=True)


if __name__ == "__main__":
    main()
