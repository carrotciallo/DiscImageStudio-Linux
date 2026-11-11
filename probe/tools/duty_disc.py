"""Read-limit test disc: how much of the time can a block be biased before it stops reading (experimental, DVD±R).

On the mix1 disc, peak DSV didn't predict reading: A5 peaks at 325 and reads, 92D peaks at 373 and doesn't.
The share of time spent at a high local bias separates them better, so this disc varies that share directly.

Each block is 92 in its balanced form, with biased bursts: an active sync frame holds BE, then L bytes of 92,
then 9B, then more 92. An inactive frame holds 9B, then 92. N is how many data frames apart the bursts are.

- L64_N1 to L64_N96: same burst, less and less often. Peak DSV stays about the same at a given LBA.
- L8_N1, L16_N2, L32_N4 with L64_N8: the same number of biased bytes per block, in short or long bursts.
- 92, guarded92, 92D, A5, A5S, RND: references.

Every condition appears at 4 phases in 3 radius bands, 64 ECC blocks each, in shuffled order, with random data
between the bands. F512 and F1488 are the share of 512T and 1488T windows with |mean level| above 0.125 and 0.10.
These are model numbers, recomputed at each real LBA, and none of them is a drive's limit.

    python tools/duty_disc.py --describe
    python tools/duty_disc.py --output iso/duty1.iso
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsv_block as D  # noqa: E402
from discprobe import dvd, iso9660  # noqa: E402
from discprobe.rings import DVD_PLUS_R_SECTORS, RingLayout  # noqa: E402
from mix_disc import ENTRY, GUARD, SECTOR, frame_starts, recorded_block, to_payload  # noqa: E402

REFERENCES = ("92", "guarded92", "92D", "A5", "A5S", "RND")
# All N divide 384, the data frames in a block, so the pattern carries on across blocks.
BURSTS = ((64, 1), (64, 2), (64, 4), (64, 8), (64, 16), (64, 32), (64, 64), (64, 96), (8, 1), (16, 2), (32, 4))
FRAMES = np.r_[0, frame_starts()]    # the first frame of a sector begins at byte 0, after the header
BANDS_MM = (26.0, 40.0, 54.0)
PHASES = 4
BLOCKS = 64


def conditions():
    return [{"name": r} for r in REFERENCES] + [{"name": f"L{L}_N{N}", "L": L, "N": N} for L, N in BURSTS]


def burst_block(L, N, phase):
    rec = np.full((dvd.BLOCK_SECTORS, SECTOR), 0x92, np.uint8)
    rec[:, FRAMES] = GUARD
    active = (np.arange(dvd.BLOCK_SECTORS * FRAMES.size) - phase) % N == 0
    sector, frame = np.divmod(np.flatnonzero(active), FRAMES.size)
    rec[sector, FRAMES[frame]] = ENTRY
    rec[sector, FRAMES[frame] + 1 + L] = GUARD
    return rec


def block_for(cond, repeat, rng):
    if "L" in cond:
        return burst_block(cond["L"], cond["N"], (2 + repeat * cond["N"] // PHASES) % cond["N"])
    if cond["name"] == "guarded92":
        rec = np.full((dvd.BLOCK_SECTORS, SECTOR), 0x92, np.uint8)
        rec[:, FRAMES] = GUARD
        return rec
    return recorded_block(cond["name"], rng)


def metrics(payload, lba):
    peak, _, level = D.encode(D.recording_rows(payload, lba))
    x = 2.0 * level - 1
    out = {"peak": peak}
    for w, tau in ((512, 0.125), (1488, 0.10)):
        out[f"F{w}"] = round(100 * float(np.mean(np.abs(np.convolve(x, np.ones(w) / w, mode="valid")) > tau)), 4)
    return out


def build_layout(geo, seed):
    segments, sectors = [], BLOCKS * dvd.BLOCK_SECTORS
    for band, r in enumerate(BANDS_MM):
        items = [(c, k) for c in conditions() for k in range(PHASES)]
        order = np.random.default_rng([seed, band]).permutation(len(items))
        lba = geo.sector_at(r)
        for i in order:
            cond, repeat = items[i]
            segments.append({**cond, "repeat": repeat, "band": band, "lba_start": lba, "lba_end": lba + sectors,
                             "r_mm": round(geo.radius_at(lba), 3)})
            lba += sectors
    return segments


def write_image(path, segments, seed):
    fill, tex = np.random.default_rng([seed, 100]), np.random.default_rng([seed, 101])
    random_cond = {"name": "RND"}
    with open(path, "xb") as f:
        lba = 0
        for seg in segments + [None]:
            end = seg["lba_start"] if seg else lba
            for at in range(lba, end, dvd.BLOCK_SECTORS):
                f.write(to_payload(block_for(random_cond, 0, fill), at).tobytes())
            if seg is None:
                break
            h = hashlib.sha256()
            for at in range(seg["lba_start"], seg["lba_end"], dvd.BLOCK_SECTORS):
                data = to_payload(block_for(seg, seg["repeat"], tex), at).tobytes()
                f.write(data)
                h.update(data)
            seg["sha256"] = h.hexdigest()
            lba = seg["lba_end"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", default="iso/duty1.iso")
    ap.add_argument("--describe", action="store_true", help="print the model table at LBA 64000, write nothing")
    ap.add_argument("--r0-mm", type=float, default=24.063, help="default: measured on RITEKF1")
    ap.add_argument("--pitch-um", type=float, default=0.7453, help="default: measured on RITEKF1")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    geo = RingLayout(r0_mm=args.r0_mm, pitch_um=args.pitch_um)
    segments = build_layout(geo, args.seed)
    total = segments[-1]["lba_end"]
    print(f"{len(conditions())} conditions, {len(segments)} segments of {BLOCKS} ECC blocks, last LBA {total}, {total * SECTOR / 1e9:.2f} GB")
    for band in range(len(BANDS_MM)):
        part = [s for s in segments if s["band"] == band]
        print(f"band {band}: LBA {part[0]['lba_start']} to {part[-1]['lba_end']}, {part[0]['r_mm']} to {geo.radius_at(part[-1]['lba_end']):.3f} mm")
    if total > DVD_PLUS_R_SECTORS:
        sys.exit("layout does not fit on a single-layer disc")
    if args.describe:
        rng = np.random.default_rng(args.seed)
        print(f"\nmodel at LBA 64000\n{'condition':10} {'peak':>5} {'F512 %':>9} {'F1488 %':>9}")
        for c in conditions():
            m = metrics(to_payload(block_for(c, 0, rng), 64000), 64000)
            print(f"{c['name']:10} {m['peak']:5d} {m['F512']:9.4f} {m['F1488']:9.4f}", flush=True)
        return
    if os.path.exists(args.output):
        sys.exit(f"{args.output} exists; not overwriting")
    write_image(args.output, segments, args.seed)
    iso9660.add(args.output, total, "DISCPROBE_DUTY")
    print(f"wrote {os.path.abspath(args.output)}")
    problems = 0
    with open(args.output, "rb") as f:
        for seg in segments:
            lba = (seg["lba_start"] + seg["lba_end"]) // 2 // dvd.BLOCK_SECTORS * dvd.BLOCK_SECTORS
            f.seek(lba * SECTOR)
            payload = np.frombuffer(f.read(dvd.BLOCK_SECTORS * SECTOR), np.uint8)
            seg["model_mid_block"] = {"lba": lba, **metrics(payload, lba)}
            if "L" in seg:
                rec = np.vstack([dvd.recorded(payload[s * SECTOR:(s + 1) * SECTOR], lba + s) for s in range(dvd.BLOCK_SECTORS)])
                if not np.array_equal(rec, block_for(seg, seg["repeat"], None)):
                    print("VERIFY FAILED", seg["name"], seg["lba_start"])
                    problems += 1
    spec = os.path.splitext(args.output)[0] + ".layout.json"
    with open(spec, "w", encoding="utf-8") as f:
        json.dump({"kind": "dvd-duty-disc", "seed": args.seed, "r0_mm": args.r0_mm, "pitch_um": args.pitch_um, "total_sectors": total,
                   "blocks_per_segment": BLOCKS, "segments": segments}, f, indent=1)
    print(f"layout {os.path.abspath(spec)}")
    print("Verified: the middle block of every burst segment records its intended bytes" if not problems else f"{problems} segments failed")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
