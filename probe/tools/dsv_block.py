"""DSV of a DVD ECC block under the EFMPlus model, using full recording frames.

Builds ID, IED, CPR_MAI, EDC, scrambling, PO and PI per ECMA-267, then encodes the 26 sync frames of
each sector. The sector header matters: all-92 frames with no header stay near |DSV| 19, and adding
12 header bytes takes them to about 319, so a check on repeated bytes alone gives the wrong answer.

The sector information byte of the ID is assumed to be 0. This is a model: it shows which data has a
large DC offset, not the point at which a given drive stops reading it.

    python tools/dsv_block.py block.gz --positions 2000 4000 8000 100 500

The input is one 32768-byte ECC block, plain or gzip. Positions are ECC block numbers (LBA / 16).
With no block, only the repeated-byte table is printed.

max bias is the largest |2 f_land - 1| over any 1488-bit sliding window. ends>100 counts sync frames
that end with |DSV| above 100, so a frame that only passes 100 inside is not counted. Each block is
encoded from state 1, DSV 0; a real recording carries the state of the block before it.
"""
import argparse
import collections
import gzip
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from discprobe import dvd, efmplus as E  # noqa: E402

EXP, LOG = [0] * 512, [0] * 256
_x = 1
for _i in range(255):
    EXP[_i], LOG[_x] = _x, _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def rs_generator(n):
    g = [1]
    for k in range(n):
        out = [0] * (len(g) + 1)
        for i, c in enumerate(g):
            out[i] ^= c
            if c:
                out[i + 1] ^= EXP[LOG[c] + k]
        g = out
    return g


def rs_parity(data, g):
    n = len(g) - 1
    reg = [0] * n
    for d in data:
        fb = int(d) ^ reg[0]
        reg = reg[1:] + [0]
        if fb:
            for i in range(n):
                if g[i + 1]:
                    reg[i] ^= EXP[LOG[g[i + 1]] + LOG[fb]]
    return reg


G_PI, G_PO, G_IED = rs_generator(10), rs_generator(16), rs_generator(2)


def edc(data):
    reg = 0
    for byte in data:
        for k in range(7, -1, -1):
            top = (reg >> 31) & 1
            reg = ((reg << 1) & 0xFFFFFFFF) | ((int(byte) >> k) & 1)
            if top:
                reg ^= 0x80000011
    for _ in range(32):
        top = (reg >> 31) & 1
        reg = (reg << 1) & 0xFFFFFFFF
        if top:
            reg ^= 0x80000011
    return reg


def recording_rows(payload, lba):
    """208 x 182 bytes in recording order: 12 data rows then one PO row, per sector."""
    data = np.zeros((192, 172), np.uint8)
    for s in range(16):
        psn = lba + s + dvd.DATA_START_PSN
        ident = [0x00, (psn >> 16) & 255, (psn >> 8) & 255, psn & 255]
        head = ident + rs_parity(ident, G_IED) + [0] * 6
        main = payload[s * 2048:(s + 1) * 2048]
        crc = edc(head + [int(b) for b in main])
        frame = np.array(head + list(dvd.recorded(main, lba + s)) + [(crc >> k) & 255 for k in (24, 16, 8, 0)], np.uint8)
        data[12 * s:12 * (s + 1)] = frame.reshape(12, 172)
    po = np.array([rs_parity(data[:, c], G_PO) for c in range(172)], np.uint8).T
    full = np.vstack([data, po])
    rows = np.zeros((208, 182), np.uint8)
    for r in range(208):
        rows[r, :172] = full[r]
        rows[r, 172:] = rs_parity(full[r], G_PI)
    order = []
    for s in range(16):
        order += list(range(12 * s, 12 * (s + 1))) + [192 + s]
    return rows[order]


def encode(rows):
    """Peak |DSV| inside frames, frame-end DSV, and channel levels."""
    b, ends, peak, levels = E.Boundary(), [], 0, []
    for i, row in enumerate(rows):
        for half in range(2):
            lv, nb = E.encode_frame(row[91 * half:91 * (half + 1)], E.ROW_SYNC[i % 13][half], b)
            peak = max(peak, int(np.abs(b.dsv + np.cumsum(2 * lv.astype(int) - 1)).max()))
            ends.append(nb.dsv)
            levels.append(lv)
            b = nb
    return peak, np.array(ends), np.concatenate(levels).astype(int)


def report(payload, lba):
    peak, ends, level = encode(recording_rows(payload, lba))
    mean = np.convolve(2 * level - 1, np.ones(E.BITS_PER_FRAME) / E.BITS_PER_FRAME, mode="valid")
    main = np.vstack([dvd.recorded(payload[s * 2048:(s + 1) * 2048], lba + s) for s in range(16)]).ravel()
    return peak, ends, float(np.abs(mean).max()), collections.Counter(main.tolist()).most_common(2)


def repeated(q, lba=64000):
    return np.concatenate([dvd.payload_for(q, lba + k) for k in range(16)])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("block", nargs="?")
    ap.add_argument("--positions", type=int, nargs="*", default=[])
    ap.add_argument("--sector-frames", type=int, default=0, help="also print frame-end DSV of this many sectors at the first position")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if args.block:
        with open(args.block, "rb") as f:
            raw = f.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        raw = np.frombuffer(raw, np.uint8)
        if raw.size != 32768:
            sys.exit(f"expected one 32768-byte ECC block, got {raw.size} bytes")
        print(f"{'block':>6} {'LBA':>7} {'seed':>4} {'max|DSV|':>9} {'max bias':>10} {'ends>100':>10}  most common bytes on disc")
        for pos in args.positions:
            peak, ends, dc, top = report(raw, pos * 16)
            print(f"{pos:6d} {pos * 16:7d} {dvd.preset_index(pos * 16):4d} {peak:9d} {dc:10.3f} {int(np.sum(np.abs(ends) > 100)):10d}  " +
                  " ".join(f"{k:02X}x{v}" for k, v in top))
        if args.positions and args.sector_frames:
            _, ends, _, _ = report(raw, args.positions[0] * 16)
            for s in range(args.sector_frames):
                print(f"sector {s}: {ends[s * 26:(s + 1) * 26].tolist()}")
        print()
    rng = np.random.default_rng(3)
    peak, _, dc, _ = report(rng.integers(0, 256, 32768).astype(np.uint8), 64000)
    print(f"{'random':>8}: max|DSV| {peak:4d}, max bias {dc:.3f}")
    for q in (0x00, 0x66, 0xB9, 0xF9, 0x92, 0xA5, 0xFF, 0xED, 0x8E):
        peak, _, dc, _ = report(repeated(q), 64000)
        print(f"{'all ' + format(q, '02X'):>8}: max|DSV| {peak:4d}, max bias {dc:.3f}")
    bare = encode(np.full((208, 182), 0x92, np.uint8))[0]
    rows = np.full((208, 182), 0x92, np.uint8)
    rows[np.arange(16) * 13, :12] = rng.integers(0, 256, (16, 12))
    print(f"all 92 with no sector header: max|DSV| {bare}; with 12 random header bytes per sector: {encode(rows)[0]}")


if __name__ == "__main__":
    main()
