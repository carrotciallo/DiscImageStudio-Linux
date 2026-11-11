"""Where a person stands in the workflow: past results, and the commands to run next.

Reads result folders and prints text; it never touches a drive. The commands it prints use
real paths and values, so they can be copied as they are.
"""

from __future__ import annotations

import datetime
import difflib
import importlib.util
import json
import math
import os
import re
import sys

from . import i18n, iso9660, mmc

RESULT_DIR = re.compile(r"^(?P<kind>[a-z]+)-(?:(?P<tag>.+)-)?(?P<stamp>\d{8}-\d{6})$")
PROG = "python -m discprobe"
# `latest` must not pick these. Results now say when they stopped early; these catch older ones, as far as they can:
# one stopped after 8 rungs says nothing, and looks complete.
MIN_RUNGS = 8
MAX_LATEST_CHI2 = 25.0
# Reports so far: under about 2 deg drives measured well; 3-24 deg (SP80NB80) and 10-14 deg
# (BW-16D1H-U) stopped or gave a wrong geometry.
GOOD_JITTER_DEG = 2.0
BAD_JITTER_DEG = 5.0
NARROW_SPAN_MM = 20.0
# When a varying pitch counts as worth a correction: it at least halves chi2/dof.
PITCH_CLEARLY_BETTER = 0.5
# Angle uncertainty (1 sigma, measured span) a geo verdict may call good. chi2/dof can't tell: a noisy drive
# has wide error bars and still fits. Clean full-span runs here gave 0.10-0.15 deg, and timing's 2 deg of
# jitter works out to about 0.21 (CD, 36 rungs) to 0.28 (DVD, 22 rungs). Past 0.6, about 5 deg of jitter,
# is where the CD run at 3226 rpm sat (0.77) that the drive table says can't be used.
GOOD_SIGMA_DEG = 0.25
BAD_SIGMA_DEG = 0.6
MATCH_INFO_S = 24 * 3600    # how far from a measurement an `info` run can be and still be taken for the same disc
ALTERNATIVE_SPEEDS = {"dvd": ("3324", "5540", "11080"), "cd": ("1411", "2822", "4234"), "bd": ("8990", "17980", "35960")}
RANDOM_SECTORS = {"dvd": 2295104, "cd": 359600}
# Spare room a random disc needs. CD: on a 359,847-sector disc 359,800 was refused and 359,600 went through.
# DVD: the usual 2,295,104 has burned many times on 2,295,104-sector discs, so it only has to fit. A smaller
# image for a smaller disc still leaves room: a 713,936-sector miniDVD refused its full count by 4 KB.
BURN_ROOM_SECTORS = {"dvd": 0, "cd": 200}
BURN_FILL = 0.98
INSTALL = "python -m pip install numpy pillow scipy"
PORTS = ("This repository drives real hardware on Windows only. Ports: Linux github.com/bczhc/disc-probe, "
         "macOS github.com/NaiveTomcat/discprobe-macos. Anything with --sim works here.")


def quote(path: str) -> str:
    return f'"{path}"' if " " in path else path


def short(path: str) -> str:
    """A path to paste into a command: relative when it is below the current folder."""
    try:
        rel = os.path.relpath(path)
    except ValueError:      # another drive on Windows
        return quote(os.path.abspath(path))
    return quote(os.path.abspath(path) if rel.startswith("..") else rel)


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _parsed(report: dict, key: str) -> dict:
    return (report.get(key) or {}).get("parsed") or {}


class Result:
    def __init__(self, path: str, kind: str, tag: str | None, stamp: str):
        self.path, self.kind, self.tag = path, kind, tag or ""
        self.when = datetime.datetime.strptime(stamp, "%Y%m%d-%H%M%S")
        self.simulated = self.tag.startswith("SIM")
        self.summary = _load(os.path.join(path, "summary.json")) or {}

    @property
    def fit(self) -> dict:
        return self.summary.get("fit") or {}

    @property
    def media(self) -> str:
        if self.kind == "geo":
            return "cd" if self.fit.get("media") == "cd" else "dvd"
        return "cd" if (self.summary.get("args") or {}).get("media") == "cd" else "dvd"

    def rungs(self) -> int:
        try:
            with open(os.path.join(self.path, "targets.csv"), encoding="utf-8") as f:
                return max(0, sum(1 for _ in f) - 1)
        except OSError:
            return 0

    @property
    def stopped(self) -> str | None:
        return self.summary.get("stopped")

    def geo_complete(self) -> bool:
        return (self.kind == "geo" and "u" in self.fit and not self.stopped and self.rungs() >= MIN_RUNGS
                and self.fit.get("chi2_per_dof", 0) <= MAX_LATEST_CHI2)

    @property
    def sigma(self) -> float | None:
        """How well this run knows the angles across what it measured, in degrees. Smaller is better."""
        return self.fit.get("angle_sigma_measured_span_deg")

    def reliable(self) -> bool:
        """Complete, and not judged too noisy to rely on."""
        return self.geo_complete() and (self.sigma is None or self.sigma <= BAD_SIGMA_DEG)

    def quality(self) -> str:
        if not self.geo_complete():
            return "stopped early"
        if not self.reliable():
            return "too noisy"
        span = self.fit.get("measured_span_mm") or [0, NARROW_SPAN_MM]
        if span[1] - span[0] < NARROW_SPAN_MM:
            return "narrow span"
        return "good" if self.sigma is not None and self.sigma <= GOOD_SIGMA_DEG and self.fit.get("chi2_per_dof", 0) <= 2 else "usable"

    def rotation(self) -> str | None:
        return ((self.summary.get("period") or {}).get("rotation") or {}).get("mode")

    def describe(self) -> str:
        if self.kind == "geo":
            f = self.fit
            if "u" not in f:
                return "stopped before the first fit"
            state = "" if self.geo_complete() else "  (stopped early)"
            span = f.get("measured_span_mm") or ["?", "?"]
            return (f"{self.rungs()} rungs, rms {f.get('residual_rms_deg', 0):.2f} deg, "
                    f"chi2/dof {f.get('chi2_per_dof', 0):.1f}, {span[0]}-{span[1]} mm{state}")
        if self.kind == "timing":
            mode = self.rotation()
            if not mode:
                return "stopped before the rotation test"
            jitter = _jitter(self.summary)
            return mode + (f", jitter {min(jitter):.2f}-{max(jitter):.2f} deg" if jitter else "") + ("  (stopped early)" if self.stopped else "")
        if self.kind == "info":
            inq = _parsed(_load(os.path.join(self.path, "info.json")) or {}, "inquiry")
            return f"{inq.get('vendor', '')} {inq.get('product', '')}".strip()
        return ""


def _jitter(summary: dict) -> list[float]:
    zones = (summary.get("period") or {}).get("zones") or []
    return [z["jitter_deg"] for z in zones if z.get("jitter_deg") is not None]


def scan(out: str = "results") -> list[Result]:
    """Result folders, newest first. Names containing `blind` are held-out data and stay unread."""
    found = []
    try:
        names = os.listdir(out)
    except OSError:
        return []
    for name in names:
        m = RESULT_DIR.match(name)
        path = os.path.join(out, name)
        if m and "blind" not in name.lower() and os.path.isdir(path):
            found.append(Result(path, m["kind"], m["tag"], m["stamp"]))
    return sorted(found, key=lambda r: r.when, reverse=True)


def latest_geo(media: str | None = None, out: str = "results") -> Result | None:
    """The newest measurement of a real disc that can be relied on, or failing that the newest complete one."""
    runs = [r for r in scan(out) if r.geo_complete() and not r.simulated and (media is None or r.media == media)]
    return next((r for r in runs if r.reliable()), runs[0] if runs else None)


def passed_over(chosen: Result, media: str | None = None, out: str = "results") -> int:
    """Newer complete runs that `latest` left out for being too noisy."""
    return sum(r.geo_complete() and not r.simulated and not r.reliable() and r.when > chosen.when and (media is None or r.media == media) for r in scan(out))


def info_runs(out: str = "results") -> list[Result]:
    return [r for r in scan(out) if r.kind == "info"]


def _info_identity(run: Result) -> dict:
    report = _load(os.path.join(run.path, "info.json")) or {}
    inq = _parsed(report, "inquiry")
    from .info import disc_id
    return {"drive": f"{inq.get('vendor', '')} {inq.get('product', '')}".strip() or None,
            "disc": disc_id(_parsed(report, "dvd_prerecorded_0e"), _parsed(report, "dvd_plus_adip_11"), _parsed(report, "atip")),
            "last_lba": _parsed(report, "capacity").get("last_lba")}


def identity_of(run: Result, infos: list[Result] | None = None) -> dict:
    """{disc, drive, inferred}. Older runs recorded neither, so take them from the nearest `info` of the same disc on that drive letter."""
    known = run.summary.get("identity") or {}
    if known.get("disc") and known.get("drive"):
        return {"disc": known["disc"], "drive": known["drive"], "inferred": False}
    disc, drive = known.get("disc"), known.get("drive")
    last_lba = (run.summary.get("setup") or {}).get("last_lba")
    same_letter = [i for i in (info_runs() if infos is None else infos) if i.tag == run.tag]
    for i in sorted(same_letter, key=lambda i: abs((i.when - run.when).total_seconds())):
        who = _info_identity(i)
        drive = drive or who["drive"]
        if abs((i.when - run.when).total_seconds()) <= MATCH_INFO_S and last_lba is not None and who["last_lba"] == last_lba and who["disc"]:
            disc = disc or who["disc"]
            break
    return {"disc": disc or "unknown disc", "drive": drive or (f"drive {run.tag}:" if run.tag else "unknown drive"), "inferred": True}


def resolve_geo(value: str, media: str | None = None, out: str = "results") -> str:
    """--geo takes a summary.json, a geo result folder, or `latest`. Raises ValueError with what to do."""
    if value.lower() == "latest":
        r = latest_geo(media, out)
        if r is None:
            have = any(x.kind == "geo" for x in scan(out))
            why = "only simulated or stopped runs were found" if have else "there is no geo result yet"
            raise ValueError(f"--geo latest: {why} in {out}. Run geo first, or give a summary.json path.")
        return os.path.join(r.path, "summary.json")
    return os.path.join(value, "summary.json") if os.path.isdir(value) else value


def describe_chosen(path: str) -> str:
    folder = os.path.dirname(path)
    m = RESULT_DIR.match(os.path.basename(folder))
    if not m:
        return short(path)
    return f"{short(path)} ({i18n.tr(Result(folder, m['kind'], m['tag'], m['stamp']).describe())})"


def missing_packages() -> list[str]:
    return [pip for module, pip in (("numpy", "numpy"), ("PIL", "pillow"), ("scipy", "scipy"))
            if importlib.util.find_spec(module) is None]


def optical_drives() -> list[str]:
    if sys.platform != "win32":
        return []
    from .spti import list_optical_drives
    return list_optical_drives()


def drive_flag(args=None) -> str:
    """How the next command should name the drive."""
    if args is not None and getattr(args, "sim", None):
        return f"--sim {args.sim}"
    if args is not None and getattr(args, "drive", None):
        return f"--drive {args.drive}"
    drives = optical_drives()
    return f"--drive {drives[0]}" if drives else "--drive E:"


def _carry(args) -> str:
    """Options the next drive command should repeat."""
    parts = [drive_flag(args)]
    if getattr(args, "media", "dvd") == "cd":
        parts.append("--media cd")
    if getattr(args, "sectors", 1) == 16:
        parts.append("--sectors 16")
    if getattr(args, "transport", "auto") != "auto":
        parts.append(f"--transport {args.transport}")
    if getattr(args, "out", "results") != "results":
        parts.append(f"--out {quote(args.out)}")
    return " ".join(parts)


def _other_speed(args, family: str | None = None) -> str:
    media = "bd" if family == "bd" else getattr(args, "media", "dvd")
    current = str(getattr(args, "speed", ""))
    return next(s for s in ALTERNATIVE_SPEEDS[media] if s != current)


def _speed_word(args) -> str:
    """How to name _other_speed. It is a higher one when this run is already at the lowest we list."""
    current = getattr(args, "speed", None)
    return "a lower speed" if current and int(_other_speed(args)) < current else "a different speed"


def sectors_from_info(report: dict) -> tuple[int, str] | None:
    """The sector count `disexport --sectors` wants, from an `info` report, with where it came from."""
    track = _parsed(report, "track_1")
    if track.get("blank") and track.get("free_blocks"):
        return track["track_start"] + track["free_blocks"], "free space of this blank disc"
    atip = _parsed(report, "atip")
    if atip.get("last_leadout_start_lba"):
        return atip["last_leadout_start_lba"], "lead-out in the ATIP; `info` on a blank disc gives a closer count"
    cap = _parsed(report, "capacity")
    if cap.get("last_lba"):
        return cap["last_lba"] + 1, "last LBA + 1, the blank size only if this disc was burned full"
    return None


def _sectors_for(summary: dict, out: str) -> tuple[str, str]:
    """A --sectors value for the preset command, and what the reader should check about it."""
    media = "cd" if (summary.get("fit") or {}).get("media") == "cd" else "dvd"
    for r in scan(out):
        if r.kind == "info" and not r.simulated:
            report = _load(os.path.join(r.path, "info.json")) or {}
            found = sectors_from_info(report)
            profile = _parsed(report, "configuration").get("current_profile")
            # The newest `info` may be of the other kind of disc: its count would be far off.
            if found and mmc.media_family(profile) in (media, "unknown"):
                return str(found[0]), f"--sectors is from your last `info`: {found[1]}"
    last = (summary.get("setup") or {}).get("last_lba")
    if last:
        return str(last + 1), "--sectors is how much was burned on the measured disc. A blank can hold more: `info` on a blank gives its count."
    return "<sectors>", "run `info` on a blank disc to find --sectors"


def _random_for_blank(report: dict) -> list[str]:
    """What to say and the command for a random-data disc that fits this blank."""
    family = mmc.media_family(_parsed(report, "configuration").get("current_profile"))
    media = "cd" if family == "cd" else "dvd"
    flag, iso = (" --media cd", "iso/cd-random.iso") if media == "cd" else ("", "iso/random.iso")
    found = sectors_from_info(report)
    if found and _parsed(report, "track_1").get("blank") and found[0] - RANDOM_SECTORS[media] < BURN_ROOM_SECTORS[media]:
        sectors = int(found[0] * BURN_FILL) // 16 * 16
        return ["Nothing is recorded on this disc, so timing cannot use it. The usual random disc would not fit, so make a smaller one:",
                f"  {PROG} random{flag} --sectors {sectors} --output {iso}"]
    return ["Nothing is recorded on this disc, so timing cannot use it. Burn a random-data disc first:",
            f"  {PROG} random{flag} --output {iso}"]


def sectors_hint(geo_path: str) -> str:
    """What to do when a preset command has no --sectors."""
    sectors, why = _sectors_for(_load(geo_path) or {}, "results")
    if sectors == "<sectors>":
        return "Run `info` on a blank disc to get the count, and enter the same number in DiscImageStudio."
    return (f"Try --sectors {sectors} ({why}). Enter the same number in DiscImageStudio. "
            "`info` on a blank disc is the count to go by: one user found read-from-disc there too high.")


def after_list(drives: list[str]) -> list[str]:
    if not drives:
        return ["Plug the drive in and check that it shows up in Explorer,",
                f"or try the flow on the simulated drive: {PROG} timing --sim cav"]
    lines = ["Next, see what the drive and disc report:", f"  {PROG} info --drive {drives[0]}"]
    if len(drives) > 1:
        lines.append("With several drives, use the letter of the one holding your disc.")
    return lines


def after_info(args, report: dict) -> list[str]:
    if mmc.not_ready((report.get("test_unit_ready") or {}).get("sense")):
        return []
    lines = []
    found = sectors_from_info(report)
    if found:
        lines += [f"Sector count for disexport --sectors: {found[0]} ({found[1]}).",
                  "Enter the same number in DiscImageStudio. A blank disc's `info` is the count to go by: one user found read-from-disc there too high.", ""]
    cap = _parsed(report, "capacity").get("last_lba")
    if _parsed(report, "track_1").get("blank") or not cap or cap < 1000:
        return lines + _random_for_blank(report)
    return lines + ["Next, check the drive (1 to 3 minutes):", f"  {PROG} timing {_carry(args)}"]


def after_timing(args, summary: dict) -> list[str]:
    media = getattr(args, "media", "dvd")
    rotation = ((summary.get("period") or {}).get("rotation") or {}).get("mode")
    if not rotation:
        return []
    family = (summary.get("setup") or {}).get("family")
    blu_ray = family == "bd"
    carry, other = _carry(args), _other_speed(args, family)
    simulated = ["This was the simulated drive, so the verdict below says nothing about your own drive.", ""] if getattr(args, "sim", None) else []
    if rotation != "CAV":
        return simulated + [f"Verdict: rotation is {rotation}, not CAV, so sector angles cannot be read at this speed.",
                "The Blu-ray drives reported so far kept a constant linear speed whatever was asked, so another speed may not change this. To try one:"
                if blu_ray else "Next, try another speed. Some drives never leave one, and the rotation test will show that:",
                f"  {PROG} timing {carry} --speed {other}"]
    jitter = _jitter(summary)
    worst = max(jitter) if jitter else None
    span = f"{min(jitter):.2f}-{worst:.2f} deg" if jitter else ""
    lines = list(simulated)
    if worst is None:
        lines.append("Verdict: rotation is CAV, but no jitter was measured.")
    elif worst <= GOOD_JITTER_DEG:
        lines.append(f"Verdict: CAV with {span} jitter. This drive looks usable.")
    else:
        lines.append(f"Verdict: CAV, but {span} jitter is noisy. Another speed may help:" if worst <= BAD_JITTER_DEG
                     else f"Verdict: CAV, but {span} jitter is too high: drives reported at this level stopped early "
                          "or gave a wrong geometry. Try another speed or another drive:")
        lines.append(f"  {PROG} timing {carry} --speed {other}")
        if media == "dvd" and not blu_ray and getattr(args, "sectors", 1) == 1:
            lines.append(f"  Or read whole ECC blocks, which was cleaner on one drive: {PROG} timing {carry} --sectors 16")
    if blu_ray:
        return lines + ["", "geo supports DVD and CD, so timing is as far as this disc goes for now."]
    usual = 1411 if media == "cd" else None
    speed = f" --speed {args.speed}" if getattr(args, "speed", None) not in (None, usual) else ""
    return lines + ["", "Next, measure the geometry:", f"  {PROG} geo {carry}{speed}"]


def after_timing_stop(args, reason: str) -> list[str]:
    flag = " --media cd" if getattr(args, "media", "dvd") == "cd" else ""
    if "cannot read" in reason or "recorded area" in reason or "fails on" in reason or "time limit" in reason:
        return [f"Make a plain data disc: {PROG} random{flag} --output iso/random.iso",
                "Burn it (Windows: right-click the .iso, Burn disc image) and run timing on it."]
    return []


def compare_pitch(out: str) -> tuple[float, float] | None:
    """chi2/dof of the constant-pitch and quadratic-pitch fits of a finished run, by tools/geo_polyfit.py."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "geo_polyfit.py")
    try:
        spec = importlib.util.spec_from_file_location("geo_polyfit", path)
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        n, y, s, fit = tool.load(out)
        scale = fit["bit_nm_assumed"] * 1e-6
        ratios = []
        for order in (0, 2):
            f = tool.fit(n, y, s, fit["u"], fit["v"], order, tool.RC_MM / scale, tool.RS_MM / scale)
            ratios.append(f["chi2"] / f["dof"])
        return ratios[0], ratios[1]
    except Exception:       # only advice depends on this; the measurement is already saved
        return None


def geo_summary(res: dict, rungs: int) -> str:
    span = res["measured_span_mm"]
    return (f"Measured {rungs} points across {span[0]}-{span[1]} mm: angles known to about "
            f"{res['angle_sigma_measured_span_deg']:.2f} deg, points {res['residual_rms_deg']:.2f} deg from the fit on average.")


def _angle(sigma: float) -> str:
    return f"{sigma:.2f} deg is about {math.radians(sigma) * 50:.2f} mm at 50 mm radius"


def _noisy(sigma: float) -> str:
    return (f"too noisy to rely on: {_angle(sigma)}." if sigma > BAD_SIGMA_DEG
            else f"usable, but noisy: {_angle(sigma)}.")


def after_geo(args, res: dict, out: str) -> list[str]:
    media = getattr(args, "media", "dvd")
    summary = _load(os.path.join(out, "summary.json")) or {}
    m = RESULT_DIR.match(os.path.basename(out))
    real_and_whole = m and not getattr(args, "sim", None) and Result(out, m["kind"], m["tag"], m["stamp"]).reliable()
    geo = "latest" if real_and_whole else short(out)
    flag = " --media cd" if media == "cd" else ""
    sectors, why = _sectors_for(summary, getattr(args, "out", "results"))
    span = res.get("measured_span_mm") or [25.8, 54.4]
    correction = ""
    lines = []
    if getattr(args, "sim", None):
        lines.append("This was the simulated drive: the verdict and commands below show the flow, do not burn from them.")
    compared = compare_pitch(out) if res["chi2_per_dof"] > 2 else None
    sigma = res["angle_sigma_measured_span_deg"]
    retry = [f"  {PROG} geo {_carry(args)} --speed {_other_speed(args)}"]
    word = _speed_word(args)
    too_noisy = sigma > BAD_SIGMA_DEG
    if res["chi2_per_dof"] <= 2:
        if sigma <= GOOD_SIGMA_DEG:
            lines.append(f"Verdict: good. Only noise is left after the fit, and {_angle(sigma)}.")
        else:
            lines += [f"Verdict: {_noisy(sigma)}", f"For a cleaner run, try {word} or another drive:", *retry]
    elif compared is None:
        lines.append("Verdict: not settled. More than noise is left, and the comparison below could not run here.")
    elif compared[1] <= PITCH_CLEARLY_BETTER * compared[0]:
        # The fit widened sigma by sqrt(chi2/dof), so what a correction leaves is that ratio undone.
        corrected = sigma * math.sqrt(max(1.0, compared[1]) / max(1.0, compared[0]))
        lines.append("Verdict: good once corrected." if corrected <= GOOD_SIGMA_DEG
                     else f"Verdict: a correction helps, but it stays noisy: {_angle(corrected)}.")
    elif too_noisy:
        lines.append(f"Verdict: {_noisy(sigma)}")
    else:
        lines.append("Verdict: usable, but noisy.")
    if span[1] - span[0] < NARROW_SPAN_MM:
        lines.append(f"This run only covers {span[0]}-{span[1]} mm, so angles outside that are extrapolated.")
    if res["chi2_per_dof"] > 2:
        if compared is None:
            lines += ["The fit left more than noise. Compare pitch models first, no new measurement needed; if quadratic is",
                      "clearly better, write a correction and add --correction correction.json to the commands below:",
                      f"  python tools/geo_polyfit.py {short(out)}",
                      f"  python tools/geo_polyfit.py {short(out)} --write-correction correction.json --order quadratic"]
        elif compared[1] <= PITCH_CLEARLY_BETTER * compared[0]:
            correction = " --correction correction.json"
            lines += [f"A varying track pitch fits clearly better (fit error ratio {compared[0]:.1f} -> {compared[1]:.1f}). "
                      "Write a correction first; the commands below use it:",
                      f"  python tools/geo_polyfit.py {short(out)} --write-correction correction.json --order quadratic"]
            if corrected > GOOD_SIGMA_DEG:
                lines += [f"For a cleaner run, try {word} or another drive:", *retry]
        elif too_noisy:
            lines += [f"A varying track pitch does not fit better (fit error ratio {compared[0]:.1f} -> {compared[1]:.1f}), so the "
                      f"extra scatter is probably read noise. Try {word} or another drive:", *retry]
        else:
            lines += [f"A varying track pitch does not fit better (fit error ratio {compared[0]:.1f} -> {compared[1]:.1f}), so the "
                      f"extra scatter is probably read noise. You can carry on. For a cleaner run, try {word}:", *retry]
    lines.append("")
    preset = [f"  {PROG} disexport --geo {geo}{correction} --sectors {sectors} --r-min {span[0]} --r-max {span[1]} "
              "--output dis_preset.json",
              "  Enter the same --sectors in DiscImageStudio.",
              f"  {why}"]
    picture = f"  {PROG} image{flag} --geo {geo}{correction} --picture my_picture.png --output iso/picture.iso"
    if media == "cd":
        return lines + ["Next, export a DiscImageStudio preset. CD has one more constant that timing cannot see, and fine",
                        "calibration there settles it on one more blank disc (the CD route in README.md):", *preset,
                        "Or make a picture ISO now (replace my_picture.png); radial lines may come out twisted without that constant:",
                        picture]
    return lines + ["Next, make a picture ISO (replace my_picture.png with your image):", picture,
                    "Or export a DiscImageStudio preset:", *preset]


def after_geo_stop(args, reason: str) -> list[str]:
    if reason in mmc.NOT_READY:
        return []
    carry, other, word = _carry(args), _other_speed(args), _speed_word(args)
    if "never settled" in reason or "near the reference" in reason:
        return [f"The drive would not hold one speed. Check it with timing, then try geo at {word}:",
                f"  {PROG} timing {carry}", f"  {PROG} geo {carry} --speed {other}",
                "USB slim drives are often too noisy here; an internal drive may simply work."]
    if "whole-turn" in reason or "safe" in reason:
        return [f"A whole-turn count went wrong, or the pitch varies more than the model allows. Try {word}:",
                f"  {PROG} geo {carry} --speed {other} --reps 32",
                "If it keeps stopping near one LBA, leave that area out with --ranges a-b (see `geo -h`).",
                "A disc whose pitch varies can take a higher limit, for example --chi2-abort 100."]
    if "ranges" in reason:
        return ["--ranges has to overlap the recorded area. See the last LBA with:", f"  {PROG} info {carry}"]
    if "recorded area" in reason or "medium" in reason or "fails on" in reason:
        flag = " --media cd" if getattr(args, "media", "dvd") == "cd" else ""
        return ["geo needs a burned disc of plain data. Make one, burn it and run geo again:",
                f"  {PROG} random{flag} --output iso/random.iso"]
    return [f"See how noisy this drive is: {PROG} timing {carry}"]


def after_random(args) -> list[str]:
    flag = " --media cd" if getattr(args, "media", "dvd") == "cd" else ""
    return ["Burn it onto a blank disc (Windows: right-click the .iso, Burn disc image), and keep some blanks of the same",
            "batch for pictures. If the burner says it does not fit, make a smaller one with --sectors.",
            "Then check the drive with it (1 to 3 minutes):",
            f"  {PROG} timing {drive_flag()}{flag}"]


def after_image(output: str, preview: str, geometry: str) -> list[str]:
    """What to do with a finished picture ISO. One made from a simulated run must not reach a disc."""
    lines = [f"Next, check the preview: {short(preview)}"]
    if "geo-SIM-" in geometry:
        return lines + ["This geometry came from the simulated drive, so it only shows the flow: do not burn this ISO."]
    return lines + [f"If it looks right, burn {short(output)} to a blank disc from the batch you measured",
                    "(Windows: right-click the .iso, Burn disc image)."]


def after_selftest() -> list[str]:
    missing = missing_packages()
    if missing:
        return [f"Those were only the checks that run without {', '.join(missing)}. Install what is missing and run it again:",
                f"  {INSTALL}"]
    return [f"Next, see where you are: {PROG} guide"]


def after_disexport(cd_constant_open: bool = False) -> list[str]:
    lines = ["Next, check the angle difference above (well under 0.1 deg is fine), then enter the preset in DiscImageStudio",
             "(inner and outer radius, sectors, the three pitch terms). Steps: docs/MANUAL.md."]
    if cd_constant_open:
        lines.append("On the CD route you can skip --along-track-frames: fine calibration in DiscImageStudio settles that constant.")
    return lines


def guide_lines(media: str = "dvd", out: str = "results", notes: bool = False) -> list[str]:
    """The workflow with what is already done ticked off, and the next command; `notes` says what each does."""
    flag = " --media cd" if media == "cd" else ""
    random_iso = "iso/cd-random.iso" if media == "cd" else "iso/random.iso"
    results = [r for r in scan(out) if not r.simulated and r.media == media]
    missing = missing_packages()
    drives = optical_drives()
    drive = f"--drive {drives[0]}" if drives else "--drive E:"

    timing = next((r for r in results if r.kind == "timing" and r.rotation() and not r.stopped), None)
    timing_good = timing is not None and timing.rotation() == "CAV"
    geo = next((r for r in results if r.geo_complete()), None)
    has_iso = os.path.exists(random_iso) and not os.path.exists(random_iso + iso9660.UNFINISHED)

    # A written file is not yet a disc. Scripts keep the tick they always saw.
    disc_done = timing is not None or (has_iso and not notes)
    rows = [(not missing, "Python packages", ", ".join(missing) + " missing" if missing else "numpy, pillow, scipy"),
            (bool(drives), "Optical drive", " ".join(drives) if drives else
             ("none found" if sys.platform == "win32" else "real drives need Windows or a port")),
            (disc_done, "Random-data disc",
             f"{random_iso} written; burn it" if has_iso and timing is None else
             "measured" if timing else "not made yet"),
            (timing_good, "Drive check (timing)", timing.describe() if timing else "not run yet"),
            (geo is not None, "Geometry (geo)", geo.describe() if geo else "not run yet")]

    if missing:
        commands = [("Install the Python packages disc-probe uses:", INSTALL)]
    elif sys.platform != "win32":
        commands = [("Try the flow on the simulated drive:", f"{PROG} timing --sim cav{flag}"), (None, PORTS)]
    elif not has_iso and timing is None:
        commands = [("Make the random-data disc: write this file, then burn it:", f"{PROG} random{flag} --output {random_iso}")]
    elif timing is None:
        commands = [(f"Burn {random_iso} to a disc and load it, then check this drive (1 to 3 minutes):", f"{PROG} timing {drive}{flag}")]
    elif not timing_good:
        commands = [("This speed did not work; try another (1 to 3 minutes):",
                     f"{PROG} timing {drive}{flag} --speed {ALTERNATIVE_SPEEDS[media][0]}")]
    elif geo is None:
        commands = [("Measure the disc's spiral (about 5 minutes):", f"{PROG} geo {drive}{flag}")]
    else:
        sectors = _sectors_for(geo.summary, out)[0]
        first = ("CD still needs one more constant, so the preset below is the usual way on (the CD route in README.md). A picture ISO:"
                 if media == "cd" else "Make a picture ISO (replace my_picture.png with your image):")
        commands = [(first, f"{PROG} image{flag} --geo latest --picture my_picture.png --output iso/picture.iso"),
                    ("Or export a preset for DiscImageStudio (enter the same --sectors there; `info` on a blank disc gives the count):",
                     f"{PROG} disexport --media {media} --geo latest --sectors {sectors} --output dis_preset.json")]

    other = "cd" if media == "dvd" else "dvd"
    lines = [f"Where you are, for {media.upper()} ({other.upper()}: {PROG} guide --media {other}):", ""]
    lines += [f"  [{'x' if done else ' '}] {i18n.pad(i18n.tr(name), 22)} {i18n.tr(detail)}" for done, name, detail in rows]
    lines += ["", "Next:"]
    for note, command in commands:
        lines += ([f"  {note}"] if notes and note else []) + [f"  {command}"]
    lines += ["", f"All commands: {PROG} -h    One command: {PROG} <command> -h    Details: docs/MANUAL.md"]
    return lines


def parser_hint(message: str, argv: list[str], commands=(), options=()) -> str | None:
    """A way out of an argparse error, for people at a terminal."""
    m = re.search(r"invalid choice: '([^']*)'", message)
    if m and commands:
        close = difflib.get_close_matches(m[1], list(commands), n=1, cutoff=0.5)
        return f"Did you mean: {PROG} {close[0]}" if close else f"See the commands with: {PROG} -h"
    if "required" in message and "--geo" in message:
        return f"Use your last measurement: {PROG} {' '.join(argv)} --geo latest"
    if "required" in message and "<command>" in message:
        return f"Not sure where to start? {PROG} guide"
    m = re.search(r"unrecognized arguments: (\S+)", message)
    if m:
        close = difflib.get_close_matches(m[1].split("=")[0], list(options), n=1, cutoff=0.6)
        if close:
            return f"Did you mean {close[0]}?"
        return f"See the options with: {PROG} {argv[0]} -h" if argv else None
    return None
