"""Texture comparison disc for the data-and-picture question (experimental, DVD±R).

Concentric rings, each filled with one texture, repeated in groups so radius effects can be removed.
Rings need no angle calibration. Questions it answers:

- Does a random mix of long-run bytes still look bright, and short-run bytes dark? If so, a picture
  can carry data: the choice among the bytes in a set is free.
- Does a guard byte before each run of 92 (bridge_iso.py) change how a pattern looks?
- Does 92 look different in its 6T/10T code word (92D) and its 8T/8T one (92)?

Textures: A5, 92, RND as references; 92D forced into 6T/10T; M32 and M32B (92 and A5 chosen per 32
bytes, without and with guards); M8 and M1 (per 8 bytes, per byte); LONG and SHORT (random choice
from long-run and short-run bytes); A5S (A5 with 78 random bytes per block to break up its PO rows).

    python tools/mix_disc.py --describe
    python tools/mix_disc.py --output iso/mix1.iso

The layout file works with ringscan: python -m discprobe ringscan scan.png --layout iso/mix1.rings.json
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsv_block as D  # noqa: E402
from bridge_iso import bridge_sector  # noqa: E402
from discprobe import dvd, efmplus as E, iso9660  # noqa: E402
from discprobe.rings import RingLayout  # noqa: E402

TEXTURES = ("A5", "92", "RND", "92D", "M32", "M32B", "M8", "M1", "LONG", "SHORT", "A5S")
GUARD = 0x9B
ENTRY = 0xBE    # after this byte, a following 92 sits in the 6T/10T code word
SECTOR = dvd.SECTOR_BYTES
_trans = np.array([[bin(E.main(q, s)[0]).count("1") for s in (1, 2, 3, 4)] for q in range(256)])
LONG = np.flatnonzero((_trans.max(axis=1) <= 3) & (np.arange(256) > 87)).astype(np.uint8)
SHORT = np.flatnonzero((_trans.mean(axis=1) >= 4.5) & (np.arange(256) > 87)).astype(np.uint8)


def frame_starts():
    """Offsets in the 2048 main bytes that begin a sync frame, past the 12 header bytes of a sector."""
    out = [c * 172 + half - 12 for c in range(12) for half in (0, 91)]
    return np.array([x for x in out if 0 <= x < SECTOR])


def recorded_block(tex, rng):
    """16 x 2048 bytes as recorded, before scrambling is undone."""
    shape = (dvd.BLOCK_SECTORS, SECTOR)
    if tex == "A5" or tex == "92":
        return np.full(shape, int(tex, 16), np.uint8)
    if tex == "RND":
        return rng.integers(0, 256, shape, dtype=np.uint8)
    if tex == "92D":
        rec = np.full(shape, 0x92, np.uint8)
        rec[:, frame_starts()] = ENTRY
        rec[:, 0] = ENTRY
        return rec
    if tex in ("M32", "M32B", "M8", "M1"):
        n = {"M32": 32, "M32B": 32, "M8": 8, "M1": 1}[tex]
        cells = rng.choice([0x92, 0xA5], (dvd.BLOCK_SECTORS, SECTOR // n + 1)).astype(np.uint8)
        rec = np.repeat(cells, n, axis=1)[:, :SECTOR]
        if tex == "M32B":
            rec = np.vstack([bridge_sector(rec[s], GUARD)[0] for s in range(dvd.BLOCK_SECTORS)])
        return rec
    if tex == "LONG":
        return rng.choice(LONG, shape)
    if tex == "SHORT":
        return rng.choice(SHORT, shape)
    if tex == "A5S":
        rec = np.full(shape, 0xA5, np.uint8)
        rec[0, 172:328:2] = rng.integers(0, 256, 78, dtype=np.uint8)
        return rec
    raise ValueError(tex)


def to_payload(rec, lba):
    return np.concatenate([dvd.recorded(rec[s], lba + s) for s in range(dvd.BLOCK_SECTORS)])


def model_table(seed=1):
    rng = np.random.default_rng(seed)
    print(f"{'texture':8} {'peak |DSV|':>10} {'mean run':>9} {'>=7T':>6} {'<=3T':>6} {'8T':>6} {'6+10T':>6}  land share over 0.4 mm  (model only, LBA 64000)")
    for tex in TEXTURES:
        pay = to_payload(recorded_block(tex, rng), 64000)
        peak, _, level = D.encode(D.recording_rows(pay, 64000))
        r = np.diff(np.flatnonzero(np.diff(level) != 0))
        w = np.convolve(level, np.ones(3008) / 3008, mode="valid")
        print(f"{tex:8} {peak:10d} {r.mean():9.2f} {np.mean(r >= 7):6.3f} {np.mean(r <= 3):6.3f} {np.mean(r == 8):6.3f} "
              f"{np.mean((r == 6) | (r == 10)):6.3f}  {w.min():.3f} to {w.max():.3f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", default="iso/mix1.iso")
    ap.add_argument("--describe", action="store_true", help="print the layout and the model table, write nothing")
    ap.add_argument("--groups", type=int, default=3)
    ap.add_argument("--ring-width-mm", type=float, default=1.0)
    ap.add_argument("--start-mm", type=float, default=25.0)
    ap.add_argument("--r0-mm", type=float, default=24.063, help="default: measured on RITEKF1")
    ap.add_argument("--pitch-um", type=float, default=0.7453, help="default: measured on RITEKF1")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    lay = RingLayout(textures=TEXTURES, groups=args.groups, ring_width_mm=args.ring_width_mm, start_mm=args.start_mm,
                     r0_mm=args.r0_mm, pitch_um=args.pitch_um, filler="RND", seed=args.seed).build()
    for r in lay.rings:
        print(f"ring {r['index']:2d} group {r['group']} {r['texture']:6} {r['r_start_mm']:6.2f} to {r['r_end_mm']:6.2f} mm  LBA {r['lba_start']}-{r['lba_end']}")
    print(f"{lay.total_sectors} sectors, {lay.total_sectors * SECTOR / 1e9:.2f} GB\n")
    print(f"LONG: {len(LONG)} bytes, {np.log2(len(LONG)):.1f} bit/byte; SHORT: {len(SHORT)} bytes, {np.log2(len(SHORT)):.1f} bit/byte\n")
    model_table(args.seed)
    if args.describe:
        return
    if lay.total_sectors > 2295104:
        sys.exit("layout does not fit on a single-layer disc")
    if os.path.exists(args.output):
        sys.exit(f"{args.output} exists; not overwriting")
    rng = np.random.default_rng(args.seed)
    with open(args.output, "xb") as f:
        for start, end, tex in lay.segments():
            for lba in range(start, end, dvd.BLOCK_SECTORS):
                f.write(to_payload(recorded_block(tex, rng), lba).tobytes())
    iso9660.add(args.output, lay.total_sectors, "DISCPROBE_MIX")
    spec = os.path.splitext(args.output)[0] + ".rings.json"
    lay.save(spec)
    print(f"\nwrote {os.path.abspath(args.output)}\nlayout {os.path.abspath(spec)}")
    problems = 0
    with open(args.output, "rb") as f:
        for r in lay.rings:
            lba = (r["lba_start"] + r["lba_end"]) // 2 // dvd.BLOCK_SECTORS * dvd.BLOCK_SECTORS
            f.seek(lba * SECTOR)
            rec = np.vstack([dvd.recorded(np.frombuffer(f.read(SECTOR), np.uint8), lba + s) for s in range(dvd.BLOCK_SECTORS)])
            allowed = {"A5": {0xA5}, "92": {0x92}, "92D": {0x92, ENTRY}, "M32": {0x92, 0xA5}, "M8": {0x92, 0xA5}, "M1": {0x92, 0xA5},
                       "M32B": {0x92, 0xA5, GUARD}, "LONG": set(LONG.tolist()), "SHORT": set(SHORT.tolist())}.get(r["texture"])
            if allowed is not None and not set(np.unique(rec).tolist()) <= allowed:
                print("VERIFY FAILED", r["index"], r["texture"])
                problems += 1
    print("Verified: the middle block of every ring records its intended bytes" if not problems else f"{problems} rings failed")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
