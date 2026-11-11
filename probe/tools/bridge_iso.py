"""Make a DVD picture ISO readable: put a guard byte before each run of 92 (experimental).

On the disc, a run of 92 can lock into the code word 0100000000010000, whose DC adds up to about
316 in one sync frame, and some drives then report 3/11/05 (DiscImageStudio #90). After 75 or 9B a
following 92 can only use the zero-DC code word. This rewrites the first 92 of each run, in the
scrambled domain, and leaves the rest alone.

A sector can be part picture and part file data, so the test is local. A run is only touched where
at least --min-pattern of the surrounding --window bytes are 92 or A5, which random-looking data
never reaches. Runs of one byte are left alone. The image must start at LBA 0.

    python tools/bridge_iso.py target.iso target_bridged.iso --check 20

This does not fix everything. A block with no 92 runs can still be high because of its PO rows (all
A5 reaches 325), and --check shows those. On a real drive so far (bczhc, #90): one block read after
this change, an earlier version that skipped mixed sectors moved a whole disc's first read error
from about 390 MiB to about 2.14 GiB, and the current rule read a whole disc with no errors. That is
one drive and one disc. On another disc the picture showed no clear change near the centre of a
scanner's dark region and a possible small loss toward its edges (evidence/dense-bridged).
"""
import argparse
import hashlib
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsv_block as D  # noqa: E402
from discprobe import dvd  # noqa: E402

BLOCK = dvd.BLOCK_SECTORS * dvd.SECTOR_BYTES
GUARDS = (0x75, 0x9B)


def bridge_sector(rec, guard, window=64, min_pattern=0.9, min_run=2):
    """Guard the first 92 of each run of at least min_run bytes where the area around it is picture."""
    is92 = rec == 0x92
    starts = np.flatnonzero(is92 & ~np.r_[False, is92[:-1]])
    if starts.size == 0:
        return rec.copy(), 0
    ends = np.flatnonzero(is92 & ~np.r_[is92[1:], False]) + 1
    pattern = np.r_[0, np.cumsum(is92 | (rec == 0xA5))]
    # A run at the edge of a picture has picture on one side only, so look each way and take the better.
    # Only full windows count: a few bytes at a sector edge could look like picture by chance.
    ahead = np.zeros(starts.size)
    fits = starts + window <= rec.size
    ahead[fits] = (pattern[starts[fits] + window] - pattern[starts[fits]]) / window
    behind = np.zeros(starts.size)
    fits = starts + 1 >= window
    behind[fits] = (pattern[starts[fits] + 1] - pattern[starts[fits] + 1 - window]) / window
    keep = ((ends - starts) >= min_run) & (np.maximum(ahead, behind) >= min_pattern)
    # A run right after a guard is already safe. Without this, a second pass would move every guard along.
    guarded = np.isin(rec, GUARDS)
    keep &= (starts == 0) | ~guarded[np.maximum(starts - 1, 0)]
    out = rec.copy()
    out[starts[keep]] = guard
    return out, int(keep.sum())


def bridge_block(payload, lba, guard, window, min_pattern):
    out, changed, touched = payload.copy(), 0, 0
    for s in range(dvd.BLOCK_SECTORS):
        a = s * dvd.SECTOR_BYTES
        rec = dvd.recorded(payload[a:a + dvd.SECTOR_BYTES], lba + s)
        new, n = bridge_sector(rec, guard, window, min_pattern)
        if n:
            out[a:a + dvd.SECTOR_BYTES] = dvd.recorded(new, lba + s)
            changed += n
            touched += 1
    return out, changed, touched


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--guard", default="9B", choices=("9B", "75"), help="byte placed before each run of 92")
    ap.add_argument("--window", type=int, default=64, help="bytes around a run used to decide it is picture")
    ap.add_argument("--min-pattern", type=float, default=0.9, help="share of 92 and A5 in that window")
    ap.add_argument("--check", type=int, default=0, help="compare peak |DSV| before and after on this many changed blocks")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if os.path.exists(args.output):
        sys.exit(f"{args.output} exists; not overwriting")
    if os.path.getsize(args.input) % dvd.SECTOR_BYTES:
        sys.exit("input is not a whole number of 2048-byte sectors")
    guard = int(args.guard, 16)
    total = changed = touched = blocks = 0
    picked = []
    rng = np.random.default_rng(args.seed)
    h_in, h_out = hashlib.sha256(), hashlib.sha256()
    with open(args.input, "rb") as fi, open(args.output, "xb") as fo:
        lba = 0
        while True:
            raw = fi.read(BLOCK)
            if not raw:
                break
            h_in.update(raw)
            data = np.frombuffer(raw, np.uint8)
            if len(raw) == BLOCK and lba % dvd.BLOCK_SECTORS == 0:
                out, c, t = bridge_block(data, lba, guard, args.window, args.min_pattern)
            else:
                out, c, t = data, 0, 0   # a short block at the end of the image
            fo.write(out.tobytes())
            h_out.update(out.tobytes())
            total += len(raw) // dvd.SECTOR_BYTES
            changed += c
            touched += t
            if c:
                blocks += 1
                # reservoir sample, so the check is spread over the disc
                if len(picked) < args.check:
                    picked.append((lba, raw, out.tobytes()))
                elif args.check and rng.integers(blocks) < args.check:
                    picked[rng.integers(args.check)] = (lba, raw, out.tobytes())
            lba += len(raw) // dvd.SECTOR_BYTES
    print(f"{total} sectors; {touched} changed, {changed} bytes changed "
          f"({100 * changed / max(1, total * dvd.SECTOR_BYTES):.2f} % of the image), guard {args.guard}")
    print(f"sha256 in  {h_in.hexdigest()}\nsha256 out {h_out.hexdigest()}")
    if picked:
        print("peak |DSV| on sampled blocks, before and after (model only; random data is about 29):")
        worst = 0
        for lba, a, b in sorted(picked, key=lambda x: x[0]):
            before = D.report(np.frombuffer(a, np.uint8), lba)[0]
            after = D.report(np.frombuffer(b, np.uint8), lba)[0]
            worst = max(worst, after)
            print(f"  LBA {lba:8d}: {before:4d} -> {after:4d}")
        print(f"worst after: {worst}" + ("  (high: probably PO rows, see the note at the top of this file)" if worst > 100 else ""))


if __name__ == "__main__":
    main()
