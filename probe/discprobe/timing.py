"""`timing`: cache/FUA test, CAV/CLV check, and sector phase measurement.

Experiments, in order:
  1. cache  - repeated reads of one sector: plain, with FUA, and after a zero-length
              READ(12)+FUA at the same LBA (redumper's cache flush). A median command
              time under CACHE_HIT_US means the drive answered from its buffer.
  2. period - repeated reads of one sector at inner, middle and outer zones give the
              revolution period there. Equal periods mean CAV; periods growing with
              radius mean CLV, and then the phase method below is not valid.
  3. phase  - alternate a reference sector R and a target X. Under CAV the spindle
              phase advances at a fixed rate whatever the head does, so the phase of
              X's completion relative to R's is the angle between the two sectors on
              the disc (plus a constant decode latency), independent of seek times.
"""

from __future__ import annotations

import gc
import math
import random
import statistics
import time
from dataclasses import asdict, dataclass

from . import analysis, mmc
from .geometry import NOMINAL
from .scsi import DATA_IN, DATA_NONE

# Re-reading one sector from the media waits for most of a revolution (over 4 ms even
# at 10000 rpm); the GH70N answers cache hits in about 1.1 ms over SATA, so 1 ms was
# too tight.
CACHE_HIT_US = 3000.0
CACHE_RATIO = 3.0
EVICT_REGION_SECTORS = 32768
ZONES = (0.05, 0.5, 0.95)
DEFAULT_TARGETS = (0.15, 0.35, 0.55, 0.75, 0.95)


@dataclass
class Event:
    experiment: str
    label: str
    lba: int
    command: str
    fua: bool
    t_start_ns: int
    t_end_ns: int
    duration_us: float
    status: int
    sense: str


# Medium errors in a row before giving up. A failing read can take the drive several seconds
# of retries (7.5 s each on a GP65NB60), so running every experiment anyway takes over an hour.
MAX_MEDIUM_ERRORS = 8
# "Becoming ready" in a row before giving up, seconds of it. Once or twice could pass by itself, but a disc going
# back in takes many seconds, and whatever comes after may not be the disc that was being measured.
MAX_LOADING_READS = 100
UNREADABLE_DISC = ("reads keep failing with medium errors ({sense}): the drive cannot read this disc reliably. "
                   "Picture, calibration and texture discs often behave like this. Timing needs plain data: "
                   "burn a random-data disc from the same batch (python -m discprobe random) and measure that.")


class NoReadableDisc(RuntimeError):
    pass


def duration_stats(results) -> dict:
    d = sorted(r.duration_us for r in results)
    if not d:
        return {"n": 0}

    def pct(p):
        return round(d[min(len(d) - 1, int(p * (len(d) - 1) + 0.5))], 1)
    return {"n": len(d), "p50_us": pct(0.5), "p95_us": pct(0.95), "p99_us": pct(0.99),
            "min_us": round(d[0], 1), "max_us": round(d[-1], 1),
            "failed": sum(1 for r in results if not r.ok)}


class TimingProbe:
    def __init__(self, dev, log=print, read_method: str = "auto", reps: int = 40,
                 period_reads: int = 60, targets=DEFAULT_TARGETS, ref_fraction: float = 0.05,
                 speed_kbs: int | None = None, pure_cav: bool = False, evict_sectors: int = 1024,
                 sectors: int = 1, host_delay_ms: float = 25.0, seed: int = 1, media="dvd",
                 stop_if_not_cav: bool = False, time_limit_s: float | None = None):
        self.media = media
        self.stop_if_not_cav = stop_if_not_cav
        self._deadline = time.monotonic() + time_limit_s if time_limit_s else None
        self._time_limit_s = time_limit_s
        self._medium_errors = 0
        self._loading_reads = 0
        self.dev = dev
        self.host_delay_s = host_delay_ms / 1e3
        self._rng = random.Random(seed)
        self.sectors = sectors
        self.log = log
        self.read_method = read_method
        self.reps = reps
        self.period_reads = period_reads
        self.targets = tuple(targets)
        self.ref_fraction = ref_fraction
        self.speed_kbs = speed_kbs
        self.pure_cav = pure_cav
        self.evict_sectors = evict_sectors
        self.events: list[Event] = []
        self.summary: dict = {}
        self._experiment = ""
        self._evict_cursor = 0
        # Reads faster than this are taken as cache hits when the cache is defeated indirectly.
        # Raised by the cache test when a slow link makes cache hits slower (see cache_test).
        self.cache_hit_us = CACHE_HIT_US

    # ------------------------------------------------------------ plumbing

    def _cmd(self, cdb: bytes, alloc: int):
        return self.dev.execute(cdb, alloc, DATA_IN if alloc else DATA_NONE)

    def _read(self, lba: int, count: int = 1, fua: bool = False, label: str = ""):
        if self.method == "readcd":
            cdb, size = mmc.read_cd(lba, count), 2352 * count
        elif self.method == "read10":
            cdb, size = mmc.read10(lba, count, fua), 2048 * count
        else:
            cdb, size = mmc.read12(lba, count, fua), 2048 * count
        res = self._cmd(cdb, size)
        self._record(label, lba, self.method, fua, res)
        self._watch(res)
        return res

    def _watch(self, res):
        """Stop early when the disc has gone, reads keep failing or the run overstays its time limit.

        Without the first of these, every read left fails in a few ms and the run ends looking like a noisy drive.
        """
        if res.ok:
            self._medium_errors = self._loading_reads = 0
        else:
            gone = mmc.disc_gone(res.sense)
            if gone:
                raise NoReadableDisc(gone)
            if mmc.not_ready(res.sense):
                self._loading_reads += 1
                if self._loading_reads >= MAX_LOADING_READS:
                    raise NoReadableDisc(mmc.LOADING)
            elif res.sense is not None and res.sense.key == 3:
                self._medium_errors += 1
                if self._medium_errors >= MAX_MEDIUM_ERRORS:
                    raise NoReadableDisc(UNREADABLE_DISC.format(sense=res.sense))
        if self._deadline is not None and time.monotonic() > self._deadline:
            raise NoReadableDisc(f"stopped after the {self._time_limit_s / 60:.0f} minute time limit "
                                 "(--max-minutes); reads are far slower than expected")

    def _record(self, label, lba, command, fua, res):
        self.events.append(Event(self._experiment, label, lba, command, fua, res.t_start_ns,
                                 res.t_end_ns, round(res.duration_us, 2), res.status, str(res.sense or "")))

    def _flush(self, lba: int):
        # Zero-length READ(12) with FUA, as redumper does before re-reading a sector;
        # whether a given firmware drops its cached copy is what the cache test checks.
        res = self._cmd(mmc.read12(lba, 0, fua=True), 0)
        self._record("flush", lba, "read12-0-fua", True, res)
        return res

    def _align(self, fraction: float) -> int:
        lba = int(self.last_lba * fraction)
        lba -= lba % self.block
        return max(0, min(lba, self.last_lba - self.block + 1))

    def _evict(self):
        chunk = 32 if self.method != "readcd" else 27
        start = self._align(0.6)
        done = 0
        while done < self.evict_sectors:
            lba = start + self._evict_cursor
            self._read(lba, chunk, label="evict")
            self._evict_cursor = (self._evict_cursor + chunk) % EVICT_REGION_SECTORS
            done += chunk

    def _pause(self):
        # A random idle time before each timed read. Without it, back-to-back re-reads of
        # one sector all take the same whole number of revolutions, and the completion
        # times only reveal that multiple, never the revolution itself (seen on the GH70N:
        # every FUA re-read took exactly 42.37 ms).
        d = self._rng.uniform(0.0, self.host_delay_s)
        if hasattr(self.dev, "idle"):
            self.dev.idle(d)
        elif d > 0:
            time.sleep(d)

    def _measure(self, lba: int, label: str):
        self._pause()
        if self.strategy == "evict":
            self._evict()
        elif self.strategy == "flush":
            self._flush(lba)
        return self._read(lba, self.sectors, fua=self.strategy == "fua", label=label)

    def _usable(self, res) -> bool:
        # Dropping samples never biases the phase (it comes from the completion time,
        # not the wait), so when the cache is defeated indirectly anything that may be
        # a cache hit is dropped.
        if not res.ok:
            return False
        return self.strategy not in ("evict", "flush") or res.duration_us >= self.cache_hit_us

    # ------------------------------------------------------------ steps

    def setup(self):
        self._experiment = "setup"
        ready = self._cmd(mmc.test_unit_ready(), 0)
        reason = mmc.not_ready(ready.sense)
        if reason:      # the checks below would blame the disc, or the --media setting
            raise NoReadableDisc(reason)
        cfg = self._cmd(mmc.get_configuration(), 4096)
        profile = mmc.parse_configuration(cfg.data).get("current_profile") if cfg.ok else None
        self.family = mmc.media_family(profile)
        self.block = mmc.block_sectors(self.family)

        cap = self._cmd(mmc.read_capacity(), 8)
        self.last_lba = mmc.parse_capacity(cap.data)["last_lba"] if cap.ok else None
        toc = self._cmd(mmc.read_toc(0), 2048)
        tracks = mmc.parse_toc(toc.data)["tracks"] if toc.ok else []
        audio = bool(tracks) and not tracks[0]["data"]
        if self.media == "cd" and (self.family != "cd" or audio or self.read_method == "readcd"):
            raise NoReadableDisc("--media cd requires a CD-ROM Mode 1 data track and READ(12)/READ(10), not READ CD")
        if self.last_lba is None and tracks and tracks[-1]["track"] == 0xAA:
            self.last_lba = tracks[-1]["start_lba"] - 1
        if not self.last_lba or self.last_lba < 1000:
            raise NoReadableDisc("no readable recorded area; burn a test disc first (blank media has nothing to read)")

        self.method = self.read_method
        if self.method == "auto":
            self.method = "readcd" if audio else "read12"
        if self.method == "read12":
            res = self._read(self._align(0.5), label="probe")
            # Only a refused command means "try READ(10)"; a medium error says nothing about the opcode.
            if not res.ok and res.sense is not None and res.sense.key == 5:
                self.method = "read10"
        probes = [self._read(self._align(f), label="probe") for f in (0.5, 0.25, 0.75)]
        if not any(r.ok for r in probes):
            sense = next((r.sense for r in probes if r.sense is not None), None)
            if sense is not None and sense.key == 3:
                raise NoReadableDisc(UNREADABLE_DISC.format(sense=sense))
            raise NoReadableDisc(f"{self.method} fails on this disc ({sense})")

        if self.speed_kbs is not None or self.pure_cav:
            res = self._cmd(mmc.set_cd_speed(self.speed_kbs or 0xFFFF, 0xFFFF, self.pure_cav), 0)
            self.summary["set_cd_speed"] = {"requested_kBps": self.speed_kbs, "pure_cav": self.pure_cav,
                                            "status": res.status, "sense": str(res.sense or "")}
        self.summary["setup"] = {"profile": f"0x{profile:04X}" if profile is not None else None,
                                 "profile_name": mmc.PROFILES.get(profile), "family": self.family,
                                 "block_sectors": self.block, "sectors_per_read": self.sectors, "last_lba": self.last_lba,
                                 "first_track_audio": audio, "read_method": self.method}
        self.log(f"Disc: {self.summary['setup']['profile_name']}, last LBA {self.last_lba}, "
                 f"reading with {self.method}")

        self._experiment = "warmup"
        warm = [self._read(self._align(f), label="warmup") for f in (0.0, 0.25, 0.5, 0.75, 1.0, 0.05)]
        bad = [r for r in warm if not r.ok and r.sense is not None and r.sense.key == 3]
        if len(bad) >= 3:
            raise NoReadableDisc(UNREADABLE_DISC.format(sense=bad[0].sense))

    def cache_test(self, reads: int = 40):
        self._experiment = "cache"
        lba = self._align(0.5)
        n = self.sectors
        plain = [self._read(lba, n, label="plain") for _ in range(reads)]
        out = {"lba": lba, "sectors": n, "plain": duration_stats(plain)}
        plain_cached = out["plain"]["p50_us"] < CACHE_HIT_US
        fua_media = flush_media = False
        if self.method != "readcd":
            fua = [self._read(lba, n, fua=True, label="fua") for _ in range(reads)]
            out["fua"] = duration_stats(fua)
            fua_media = out["fua"]["p50_us"] >= CACHE_HIT_US and all(r.ok for r in fua)
            # A cache hit over a slow link is not under CACHE_HIT_US (8 ms on an SDRW-08D2S-U over
            # USB, against 39 ms with FUA). Far slower with FUA also means plain reads are cached.
            if fua_media and out["fua"]["p50_us"] >= CACHE_RATIO * out["plain"]["p50_us"]:
                plain_cached = True
        elif not plain_cached:
            # READ CD has no FUA bit, so compare with reads that follow an eviction instead. Over
            # USB an HP BU20N returned cached CD-DA sectors in about 10 ms, above CACHE_HIT_US,
            # while reads from the disc took several times longer.
            evicted = []
            for _ in range(max(8, reads // 4)):
                self._evict()
                evicted.append(self._read(lba, n, label="after-evict"))
            out["after_evict"] = duration_stats(evicted)
            slow = out["after_evict"]["p50_us"] >= CACHE_RATIO * out["plain"]["p50_us"]
            if slow and all(r.ok for r in evicted):
                plain_cached = True
                # Halfway (geometrically) between the cache hits and the reads from the disc.
                self.cache_hit_us = max(CACHE_HIT_US, math.sqrt(out["plain"]["p50_us"] *
                                                                 out["after_evict"]["p50_us"]))
                out["cache_hit_us"] = round(self.cache_hit_us, 1)
        if plain_cached and not fua_media:
            flushed = []
            for _ in range(reads):
                self._flush(lba)
                flushed.append(self._read(lba, n, label="after-flush"))
            out["after_flush"] = duration_stats(flushed)
            flush_media = out["after_flush"]["p50_us"] >= self.cache_hit_us and all(r.ok for r in flushed)
        if not plain_cached:
            self.strategy = "plain"
        elif fua_media:
            self.strategy = "fua"
        elif flush_media:
            self.strategy = "flush"
        else:
            self.strategy = "evict"
        out.update(plain_served_from_cache=plain_cached, fua_reads_media=fua_media,
                   flush_then_read_media=flush_media, strategy=self.strategy)
        self.summary["cache"] = out
        self.log("Cache: " + ", ".join(f"{k} p50 {v['p50_us']} us" for k, v in out.items()
                                       if isinstance(v, dict)) + f" -> strategy {self.strategy}")

    def cover_one_turn(self, period_s: float):
        """The random pause before a timed read has to span a revolution to spread the phases."""
        self.host_delay_s = max(self.host_delay_s, 1.25 * period_s)

    def settle_spindle(self, rounds: int = 15, reads: int = 16):
        """Wait for a steady speed: a stopped or slowed drive spins up for a while after the first
        reads, and the first run then looks mixed or noisy while a second run looks fine."""
        self._experiment = "settle"
        lba, prev = self._align(0.5), None
        for _ in range(rounds):
            res = [self._measure(lba, "settle") for _ in range(reads)]
            times = [r.t_end_ns for r in res if self._usable(r)]
            fit = analysis.estimate_period(times) if len(times) >= 8 else None
            period = fit.period_s if fit and fit.coherence > 0.9 else None
            if period and prev and abs(period / prev - 1) < 2e-3:
                self.log(f"Spindle steady: T = {period * 1e3:.3f} ms ({60 / period:.1f} rpm)")
                self.summary["settle"] = {"steady": True, "period_ms": period * 1e3}
                if self.strategy == "fua":  # without the random pause, which would hide the whole turns
                    self.summary["settle"]["read"] = duration_stats(
                        [self._read(lba, self.sectors, fua=True, label="settled") for _ in range(8)])
                self.cover_one_turn(period)
                return
            prev = period
        self.log("Spindle did not reach a steady speed; expect noisy results")
        self.summary["settle"] = {"steady": False}

    def period_test(self):
        self._experiment = "period"
        zones = []
        for frac in ZONES:
            lba = self._align(frac)
            reads = [self._measure(lba, f"zone{frac}") for _ in range(self.period_reads)]
            times = [r.t_end_ns for r in reads if self._usable(r)]
            fit = analysis.estimate_period(times)
            zone = {"fraction": frac, "lba": lba, "usable": len(times), "durations": duration_stats(reads),
                    "nominal_radius_mm": round(self._nominal_spiral().radius(lba), 3)}
            if fit:
                zone.update(fit.summary())
            zones.append(zone)
            self.log(f"Zone {frac:.2f} (LBA {lba}): " + (
                f"T = {zone['period_ms']} ms ({zone['rpm']} rpm), jitter {zone['jitter_us']} us "
                f"= {zone['jitter_deg']} deg, coherence {zone['coherence']}" if fit else "no period found"))
        self.zones = zones
        self.summary["period"] = {"zones": zones, "rotation": self._classify(zones)}
        rotation = self.summary["period"]["rotation"]
        self.log(f"Rotation: {rotation['mode']}" + (f" ({rotation['reason']})" if "reason" in rotation else ""))
        self._check_period(zones)

    def _check_period(self, zones):
        """Catch a period that is not the spindle. A re-read from the disc takes whole turns on every
        drive so far. Reads served from cache follow the host instead: with a coarse sleep their
        completion times lock to the Windows timer tick (15.625 ms) and its harmonics."""
        periods = [z["period_ms"] for z in zones if "period_ms" in z]
        # The cache test runs before the spindle settles, so its FUA time can span two speeds.
        settle = self.summary.get("settle", {})
        fua = settle["read"]["p50_us"] if self.strategy == "fua" and "read" in settle else None
        if not periods or not fua:
            return
        T = statistics.median(periods)
        turns = fua / 1e3 / T
        self.summary["period"]["fua_read_turns"] = round(turns, 3)
        if abs(turns - round(turns)) > 0.1:
            self.log(f"Warning: a FUA read takes {turns:.2f} turns of this period, not a whole number, "
                     "so this period may not be the spindle")
        if self.strategy in ("plain", "evict") and any(abs(15.625 / k - T) < 0.15 for k in (1, 2, 3)):
            self.log("Warning: this period looks like the Windows timer tick (15.625 ms), not the spindle")

    def _nominal_key(self) -> str:
        return self.family if self.family in NOMINAL else "dvd"

    def _nominal_spiral(self):
        if self.media == "cd":
            from . import cd
            from .geometry import Spiral
            return Spiral(cd.R0_MM, cd.PITCH_UM * 1e-3, cd.SECTOR_BITS * cd.BIT_NM * 1e-6)
        return NOMINAL[self._nominal_key()]

    def _classify(self, zones) -> dict:
        valid = [z for z in zones if z.get("period_ms") and z.get("coherence", 0) > 0.5]
        noisy = [z["fraction"] for z in zones if z.get("period_ms") and z.get("coherence", 0) <= 0.5]
        if noisy:  # a speed still changing shows up like this, and the two other zones alone can look CAV
            return {"mode": "unknown", "reason": f"zones {noisy} have no clear period; the speed may be changing, "
                                                 "try a fixed --speed"}
        if len(valid) < 2:
            return {"mode": "unknown", "reason": "fewer than two zones with a clear period"}
        inner, outer = valid[0], valid[-1]
        ratio = outer["period_ms"] / inner["period_ms"]
        clv_ratio = outer["nominal_radius_mm"] / inner["nominal_radius_mm"]
        if abs(ratio - 1) < 0.03:
            mode = "CAV"
        elif abs(ratio - clv_ratio) / clv_ratio < 0.12:
            mode = "CLV"
        else:
            mode = "mixed (P-CAV / Z-CLV?)"
        return {"mode": mode, "period_ratio_outer_inner": round(ratio, 4),
                "nominal_clv_ratio": round(clv_ratio, 4)}

    def phase_test(self):
        self._experiment = "phase"
        ref = self._align(self.ref_fraction)
        prior = None
        for z in getattr(self, "zones", []):
            if z.get("period_ms") and z["fraction"] == min(ZONES, key=lambda f: abs(f - self.ref_fraction)):
                prior = z["period_ms"] / 1e3
        spiral = self._nominal_spiral()
        results = []
        span = -(-max(self.sectors, 1) // self.block) * self.block  # whole blocks the drive reads
        for frac in self.targets:
            x = self._align(frac)
            ref_times, x_times, x_reads = [], [], []
            for _ in range(self.reps):
                r = self._measure(ref, "ref")
                if self._usable(r):
                    ref_times.append(r.t_end_ns)
                xr = self._measure(x, "target")
                x_reads.append(xr)
                if self._usable(xr):
                    x_times.append(xr.t_end_ns)
            entry = {"target_fraction": frac, "ref_lba": ref, "target_lba": x, "read_end_lba": x + span,
                     "nominal_turns_between": round(spiral.turns(ref + span, x + span), 2),
                     "target_durations": duration_stats(x_reads)}
            if self.media == "cd":
                from .cd import read_end_bits, SECTOR_BITS
                nr, nx = read_end_bits(ref, self.sectors), read_end_bits(x, self.sectors)
                entry.update(read_end_bits=int(nx), read_tail_frames=108,
                             nominal_turns_between=round(spiral.turns(nr / SECTOR_BITS, nx / SECTOR_BITS), 2))
            fit = analysis.estimate_period(ref_times, prior_s=prior) if len(ref_times) >= 5 else None
            if fit and x_times:
                entry["ref"] = fit.summary()
                entry["phase"] = analysis.robust_circular_mean(analysis.phase_offsets(fit, x_times))
                self.log(f"Target {frac:.2f} (LBA {x}): phase {entry['phase']['mean_deg']} deg "
                         f"+/- {entry['phase']['sem_deg']} (single-shot std {entry['phase']['std_deg']}, "
                         f"n={entry['phase']['used']}), ref jitter {entry['ref']['jitter_deg']} deg")
            else:
                entry["error"] = "not enough usable reads"
                self.log(f"Target {frac:.2f}: not enough usable reads")
            results.append(entry)
        rotation = self.summary.get("period", {}).get("rotation", {}).get("mode")
        self.summary["phase"] = {
            "valid_only_under_cav": True, "rotation_mode": rotation, "targets": results,
            "note": "phase = spindle phase of target completion minus reference completion; "
                    "it equals the disc angle between the ends of the two read blocks plus a "
                    "constant decode-latency term, modulo 360 degrees"}
        if rotation != "CAV":
            self.log("Warning: drive did not look CAV; phase values are not disc angles.")

    def run(self) -> dict:
        gc_was = gc.isenabled()
        gc.disable()
        try:
            self.setup()
            self.cache_test()
            self.settle_spindle()
            self.period_test()
            mode = self.summary["period"]["rotation"]["mode"]
            if self.stop_if_not_cav and mode != "CAV":
                self.log(f"Rotation is {mode}, not CAV, so the phase test would not give disc angles; skipping it. "
                         "Try another --speed, or pass --force to run it anyway.")
            else:
                self.phase_test()
        finally:
            if gc_was:
                gc.enable()
        return self.summary

    def events_as_rows(self):
        return [asdict(e) for e in self.events]
