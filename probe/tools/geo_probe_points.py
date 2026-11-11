"""Measure extra points against an existing `geo` fit and print their residuals.

Uses the same reference sector and reference/target interleaving as the ladder, then compares
each phase with the fitted model (mod 360). Good for mapping a local feature the ladder only
sampled sparsely, e.g. the 4-degree step near 49.9 mm on the first full CD ladder.

    python tools/geo_probe_points.py --drive H: --media cd --geo results/geo-H-.../summary.json ^
        --lbas 232000:252000:1000 219845 256153
"""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from discprobe.geo import Ladder  # noqa: E402
from discprobe.device import Device, raise_priority  # noqa: E402


def parse_lbas(items):
    out = []
    for it in items:
        if ":" in it:
            a, b, s = (int(x) for x in it.split(":"))
            out += list(range(a, b + 1, s))
        else:
            out.append(int(it))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--drive", required=True)
    ap.add_argument("--media", choices=("dvd", "cd"), default="dvd")
    ap.add_argument("--geo", required=True, help="summary.json of the geo run to compare against")
    ap.add_argument("--speed", type=int, help="read speed kB/s (default: the ladder's default for the media)")
    ap.add_argument("--lbas", nargs="+", required=True, help="LBAs, or start:stop:step ranges")
    ap.add_argument("--host-delay-ms", type=float, default=25.0,
                    help="random pause before each timed read; should exceed one revolution")
    ap.add_argument("--reps", type=int, help="reference/target read pairs per point (default: the ladder's)")
    ap.add_argument("--ref-lba", type=int, help="reference sector (default: the fit's); a near one cuts seek noise, "
                                                "and only shifts every residual by a constant")
    a = ap.parse_args()
    f = json.load(open(a.geo))["fit"]
    speed = a.speed or (1411 if a.media == "cd" else 5540)
    raise_priority()
    with Device(a.drive) as dev:
        ref = a.ref_lba if a.ref_lba is not None else f["reference_lba"]
        L = Ladder(dev, media=a.media, ref_lba=ref, speed_kbs=speed, log=print,
                   host_delay_ms=a.host_delay_ms, reps=a.reps)
        L.u, L.v, L.c = f["u"], f["v"], math.radians(f["c_deg"])
        tp = L.tp
        tp.setup()
        tp.cache_test()
        L.ranges = [(0, tp.last_lba + 1)]
        L.ref = ref
        L.n_ref = L._n_end(L.ref)
        t0 = time.time()
        while time.time() - t0 < 10:  # spin up before settling
            tp._measure(L.ref, "warm")
        L.settle()
        b = f["bit_nm_assumed"] * 1e-6
        for lba in parse_lbas(a.lbas):
            try:
                m = L._measure_retry(lba)
            except RuntimeError as e:
                print(lba, e)
                L.settle()
                continue
            if m is None:
                print(lba, "failed")
                continue
            res = (m["phase_deg"] - math.degrees(L._predict(m["n"])) + 180) % 360 - 180
            r = b * math.sqrt(f["u"] ** 2 + f["v"] * m["n"] / math.pi)
            print(f"lba {lba:7d}  r {r:6.3f} mm  residual {res:+7.2f} deg  +/- {m['sigma_deg']:.2f}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
