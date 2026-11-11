"""Read back a burned duty_disc.py disc, recording every read. Sends read commands only.

Segments are visited in random order, so a run stopped early is still a fair sample. In each segment it reads
the first, middle and last block; the first and middle are each followed by their neighbour, which separates a
read right after a seek from a read in sequence. Reads use FUA so a block comes from the disc and not the cache.

    python tools/duty_readback.py --drive H: --iso iso/duty1.iso --layout iso/duty1.layout.json --out evidence/duty1/readback.json

Every read is saved with its time, status, sense and whether the data matched the ISO. Repeat passes are
kept apart from the first, because a later read of the same block can succeed where the first one failed.
"""
import argparse
import collections
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from discprobe import mmc  # noqa: E402

BLOCK_SECTORS = 16
BLOCK_BYTES = BLOCK_SECTORS * 2048


def open_drive(args):
    if args.sim:
        from discprobe.sim import SimDrive
        return SimDrive(mode="cav", seed=args.seed)
    from discprobe.__main__ import _open
    return _open(argparse.Namespace(sim=None, drive=args.drive, transport=args.transport))


def plan_reads(seg):
    """(lba, access) in reading order."""
    start, end = seg["lba_start"], seg["lba_end"]
    middle = (start + end) // 2 // BLOCK_SECTORS * BLOCK_SECTORS
    return [(start, "seek"), (start + BLOCK_SECTORS, "sequential"), (middle, "seek"), (middle + BLOCK_SECTORS, "sequential"),
            (end - BLOCK_SECTORS, "seek")]


def read_block(dev, iso, lba):
    iso.seek(lba * 2048)
    want = iso.read(BLOCK_BYTES)
    res = dev.execute(mmc.read12(lba, BLOCK_SECTORS, fua=True), BLOCK_BYTES, timeout_s=60)
    out = {"lba": lba, "ms": round(res.duration_us / 1000, 2), "status": res.status}
    if res.ok:
        out["match"] = bytes(res.data[:BLOCK_BYTES]) == want
    else:
        out["sense"] = str(res.sense) if res.sense else None
    return out


def summarize(records, layout):
    model = collections.defaultdict(list)
    for s in layout["segments"]:
        model[s["name"]].append(s["model_mid_block"]["F512"])
    rows = collections.defaultdict(list)
    for r in records:
        if r["pass"] == 0:
            rows[r["name"]].append(r)
    print(f"\nfirst pass, least to most biased\n{'condition':10} {'F512 %':>7} {'reads':>5} {'failed':>6} {'wrong':>5} {'median ms':>9} {'seek ms':>8} {'max ms':>9}")
    for name in sorted(rows, key=lambda n: float(np.median(model[n]))):
        a = rows[name]
        ms = [x["ms"] for x in a]
        seek = [x["ms"] for x in a if x["access"] == "seek"]
        failed = sum(x["status"] != 0 for x in a)
        wrong = sum(x.get("match") is False for x in a)
        print(f"{name:10} {float(np.median(model[name])):7.2f} {len(a):5d} {failed:6d} {wrong:5d} {np.median(ms):9.1f} {np.median(seek):8.1f} {max(ms):9.1f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drive")
    ap.add_argument("--sim", action="store_true", help="use the simulated drive, to test this script")
    ap.add_argument("--transport", choices=["auto", "spti", "imapi"], default="auto")
    ap.add_argument("--iso", required=True)
    ap.add_argument("--layout", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--passes", type=int, default=2, help="the first pass is the result; later ones show whether a failure repeats")
    ap.add_argument("--max-minutes", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if os.path.exists(args.out):
        sys.exit(f"{args.out} exists; not overwriting")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.layout, encoding="utf-8") as f:
        layout = json.load(f)
    rng = np.random.default_rng(args.seed)
    dev = open_drive(args)
    began, records, stopped = time.monotonic(), [], False
    with open(args.iso, "rb") as iso:
        for pass_no in range(args.passes):
            for i in rng.permutation(len(layout["segments"])):
                seg = layout["segments"][int(i)]
                for lba, access in plan_reads(seg):
                    records.append({**read_block(dev, iso, lba), "pass": pass_no, "access": access, "name": seg["name"], "band": seg["band"]})
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump({"iso": os.path.basename(args.iso), "drive": args.drive or "sim", "stopped_early": stopped, "reads": records}, f)
                if time.monotonic() - began > args.max_minutes * 60:
                    stopped = True
                    break
            print(f"pass {pass_no}: {len(records)} reads so far, {(time.monotonic() - began) / 60:.1f} min", flush=True)
            if stopped:
                print("time limit reached")
                break
    if hasattr(dev, "close"):
        dev.close()
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"iso": os.path.basename(args.iso), "drive": args.drive or "sim", "stopped_early": stopped, "reads": records}, f)
    summarize(records, layout)


if __name__ == "__main__":
    main()
