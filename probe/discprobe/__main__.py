"""Command line: python -m discprobe <command>; run it with -h, or `guide`, to see the commands."""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import sys

from . import guide, i18n, info, mmc, timing, ui

# Tile target palette: the A5/92 pair, B9 and 66, aperiodic mixes of the 3.2T (A5-like)
# and 8T (92-like) classes, then along-track periods 32T, 48T and 64T (16T is 92). The
# period sequences were found with discprobe/efmplus.py and hold their period from any
# start state (evidence/coverage/periods.txt).
DEFAULT_PALETTE = ("A5", "92", "B9", "66", "MIX:A5,62,B1,61,65,A7", "MIX:92,87,83,8D,60",
                   "8B", "2AE304", "ED00")


class _Rerun(Exception):
    """Start over with these arguments added, after the person agreed to them."""

    def __init__(self, extra):
        self.extra = extra


def _fail(message, hints=()):
    """Exit with an error, plus what to do about it at a terminal."""
    if ui.term().interactive and hints:
        print(message, file=sys.stderr)
        _next(hints)
        sys.exit(1)
    sys.exit(message)


def _reason(e: OSError) -> str:
    """The system's message, for a sentence of ours; it brings its own full stop. Scripts see it as it always was."""
    return e.strerror.rstrip(" .\u3002") if ui.term().interactive else e.strerror


def _os_error(e: OSError) -> str:
    """At a terminal a missing file is said plainly; scripts keep the form they always saw."""
    if isinstance(e, FileNotFoundError) and e.filename and ui.term().interactive:
        return f"no such file: {e.filename}"
    return f"error: {e}"


def _next(lines) -> None:
    """Advice after a command; the lines to copy stand out."""
    if lines:
        ui.say()
    for line in lines:
        ui.say(line, "cyan" if line.lstrip().startswith("python ") else None)


def _need_windows() -> None:
    if sys.platform != "win32":
        sys.exit(guide.PORTS)


def _choose_drive(args) -> None:
    """At a terminal a missing --drive can be worked out."""
    if args.drive or sys.platform != "win32" or not ui.term().interactive:
        return
    drives = guide.optical_drives()
    if len(drives) == 1:
        args.drive = drives[0]
        ui.say(f"Using the only optical drive, {args.drive}")
    elif not drives:
        sys.exit("no optical drive found; to try the flow without one, add --sim cav")
    elif ui.term().can_prompt():
        print("Optical drives: " + "  ".join(drives))
        while args.drive not in drives:
            try:
                answer = input(i18n.tr(f"Which drive? [{drives[0]}] ")).strip().upper()
            except EOFError:
                sys.exit("no drive chosen")
            answer = answer or drives[0]
            args.drive = answer if answer.endswith(":") else answer + ":"


def _open(args):
    if args.sim:
        from .sim import SimDrive
        mode, _, variant = args.sim.partition("-")
        return SimDrive(mode=mode, fua_honoured=variant == "", flush_honoured=variant == "flush",
                        seed=args.seed, media=getattr(args, "media", "dvd"))
    _choose_drive(args)
    if not args.drive:
        sys.exit("give --drive <device> (see `python -m discprobe list`) or --sim cav|clv|cav-nofua")
    if sys.platform.startswith("linux"):
        from .device import Device
        return Device(args.drive)
    _need_windows()
    transport = getattr(args, "transport", "auto")
    if transport != "imapi":
        from .spti import SptiDevice
        try:
            return SptiDevice(args.drive)
        except ValueError as e:
            sys.exit(f"{e} (see `python -m discprobe list`)")
        except OSError as e:
            # SPTI often needs an elevated process; IMAPI2 reaches the same drive without it.
            if transport == "spti" or e.errno != 5:
                sys.exit(f"{_reason(e)}. Optical drives here: {' '.join(guide.optical_drives()) or 'none'}")
            print("note: SPTI was refused (not elevated); using the IMAPI2 transport instead")
    from .imapi import ImapiDevice
    return ImapiDevice(args.drive)


def _check_disc(dev, args) -> None:
    """At a terminal, catch an empty tray or the wrong media settings before minutes of measuring."""
    if not ui.term().interactive:
        return
    from .scsi import DATA_IN, DATA_NONE
    ready = dev.execute(mmc.test_unit_ready(), 0, DATA_NONE)
    reason = mmc.not_ready(ready.sense)
    if reason:
        sys.exit(reason)
    cfg = dev.execute(mmc.get_configuration(), 4096, DATA_IN)
    family = mmc.media_family(mmc.parse_configuration(cfg.data).get("current_profile") if cfg.ok else None)
    if family == "cd" and args.media == "dvd":
        if ui.ask("This is a CD, but the command has DVD settings. Add --media cd?"):
            dev.close() if hasattr(dev, "close") else None
            raise _Rerun(["--media", "cd"])
    if family == "bd" and args.func is cmd_geo:
        ui.say("Note: geo supports DVD and CD; on this BD only timing is known to work.", "yellow")


def _blu_ray_speed(dev, args) -> None:
    """--media has no BD, so a multiple was worked out for DVD. Only the disc can tell."""
    multiple = getattr(args.speed, "multiple", None)
    if multiple is None or args.sim:
        return
    from .scsi import DATA_IN
    cfg = dev.execute(mmc.get_configuration(), 4096, DATA_IN)
    if cfg.ok and mmc.media_family(mmc.parse_configuration(cfg.data).get("current_profile")) == "bd":
        args.speed = round(multiple * mmc.BD_1X_KBPS)
        print(f"This is a Blu-ray disc, so {multiple:g}x is {args.speed} kB/s")


def _measuring(dev, args):
    """What the probe reads through: at a terminal, a wrapper that also draws the progress line."""
    if not ui.term().interactive:
        return dev
    limit = f" It gives up after {args.max_minutes:g} minutes." if getattr(args, "max_minutes", 0) else ""
    ui.say(f"Measuring on {getattr(dev, 'name', 'the drive')}. Ctrl+C stops and keeps what was measured.{limit}", "dim")
    return ui.ProgressDevice(dev)


def _identity(args, dev) -> dict | None:
    """Which drive and disc this is, for the results list. Before any timing; a simulated run has none."""
    if getattr(args, "sim", None):
        return None
    try:
        return info.identify(dev, getattr(args, "media", None))
    except Exception:       # a label, never worth stopping a measurement
        return None


def _geo_fit(args, media=None) -> dict:
    """Load --geo, which may be a summary.json, a geo result folder or `latest`."""
    try:
        if args.geo.lower() == "pick":
            from . import picker
            chosen = picker.choose(media)
            if chosen is None:
                sys.exit("Nothing chosen.")
            path = os.path.join(chosen.path, "summary.json")
            print(f"Using the geo result you chose: {guide.describe_chosen(path)}")
        else:
            path = guide.resolve_geo(args.geo, media)
    except ValueError as e:
        sys.exit(str(e))
    if args.geo.lower() == "latest":
        print(f"Using the latest geo result: {guide.describe_chosen(path)}")
        chosen = guide.latest_geo(media)
        if chosen is not None and not chosen.reliable():
            print("It was judged too noisy to rely on, and there is nothing better. To see them all: python -m discprobe results --pick")
        elif chosen is not None and guide.passed_over(chosen, media):
            print(f"Left out {guide.passed_over(chosen, media)} newer run(s) judged too noisy. To see them all: python -m discprobe results --pick")
    args.geo = path
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)["fit"]
    except FileNotFoundError:
        latest = guide.latest_geo(media)
        _fail(f"no such geo result: {path}",
              [f"Your last measurement is {guide.describe_chosen(os.path.join(latest.path, 'summary.json'))}.",
               "Use it with --geo latest."] if latest else ["Run geo first, then use --geo latest."])
    except (ValueError, KeyError, TypeError):
        sys.exit(f"{path} is not the summary.json of a geo run (it has no geometry fit)")


def _outdir(args, kind: str, dev) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    tag = getattr(dev, "name", "drive").replace(":", "")
    path = os.path.join(args.out, f"{kind}-{tag}-{stamp}")
    os.makedirs(path, exist_ok=True)
    _Parser.last_out = path
    return path


def _write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def cmd_list(args):
    if sys.platform.startswith("linux"):
        from .device import list_optical_drives
        drives = list_optical_drives()
    else:
        _need_windows()
        drives = guide.optical_drives()
    print("\n".join(drives) if drives else "no optical drives found")
    _next(guide.after_list(drives))


def cmd_info(args):
    dev = _open(args)
    try:
        report = info.collect(dev)
    finally:
        dev.close() if hasattr(dev, "close") else None
    out = _outdir(args, "info", dev)
    _write_json(os.path.join(out, "info.json"), report)
    for line in info.summarize(report):
        print(line)
    print(f"\nFull dump: {os.path.abspath(out)}")
    _next(guide.after_info(args, report))


def cmd_timing(args):
    if not args.sim:
        if sys.platform.startswith("linux"):
            from .device import raise_priority
        else:
            _need_windows()
            from .spti import raise_priority
        if not raise_priority():
            print("note: could not raise process priority")
    dev = _open(args)
    _check_disc(dev, args)
    _blu_ray_speed(dev, args)
    targets = [float(x) for x in args.targets.split(",")] if args.targets else timing.DEFAULT_TARGETS
    reader = _measuring(dev, args)
    probe = timing.TimingProbe(
        reader, read_method=args.read, reps=args.reps, period_reads=args.period_reads,
        targets=targets, ref_fraction=args.ref, speed_kbs=args.speed, pure_cav=args.cav,
        evict_sectors=args.evict_sectors, sectors=args.sectors, host_delay_ms=args.host_delay_ms, media=args.media,
        stop_if_not_cav=not args.force, time_limit_s=args.max_minutes * 60 if args.max_minutes else None)
    probe.summary["identity"] = _identity(args, dev)
    progress = None
    if reader is not dev:
        progress = reader.progress = ui.Progress(ui.timing_status(probe, reader), keys=ui.open_keys())
        probe.log = progress.log
    stopped = None
    finished = False
    try:
        summary = probe.run()
        finished = True
    except timing.NoReadableDisc as e:
        stopped = str(e)
    finally:
        if progress:
            progress.close()
        dev.close() if hasattr(dev, "close") else None
        out = _outdir(args, "timing", dev)
        rows = probe.events_as_rows()
        if rows:
            with open(os.path.join(out, "events.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
        summary = probe.summary
        if not finished:        # also for Ctrl+C or a drive that vanished, which pass through here
            summary["stopped"] = stopped or "interrupted"
        summary["device"] = getattr(dev, "name", None)
        summary["args"] = {k: v for k, v in vars(args).items()
                           if k != "func" and (k != "media" or v != "dvd")}
        _write_json(os.path.join(out, "summary.json"), summary)
        print(f"\nRaw events and summary: {os.path.abspath(out)}")
    if stopped:
        _fail(stopped, guide.after_timing_stop(args, stopped))
    if progress:
        ui.say(f"Finished in {ui.clock(ui.time.monotonic() - progress.started)}", "dim")
    _next(guide.after_timing(args, summary))


def cmd_spokes(args):
    from .spokes import SpokeSpec, generate
    spec = SpokeSpec(radius_mm=args.radius_mm, size_px=args.size)
    spec_path = generate(args.output, spec)
    print(f"Pattern: {os.path.abspath(args.output)}\nSpec:    {os.path.abspath(spec_path)}")
    print(f"Make the image exactly fill the DiscImageStudio canvas (radius {args.radius_mm} mm), centred.")


def cmd_scan(args):
    from .scan import analyse
    from .spokes import SpokeSpec
    spec = SpokeSpec.load(args.spec)
    centre = tuple(float(v) for v in args.centre.split(",")) if args.centre else None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(args.out, f"scan-{os.path.splitext(os.path.basename(args.image))[0]}-{stamp}")
    try:
        analyse(args.image, spec, out, dpi=args.dpi, centre=centre, r_min=args.r_min, r_max=args.r_max)
    except RuntimeError as e:
        sys.exit(str(e))
    print(f"\nphase.csv, summary.json and check images: {os.path.abspath(out)}")


def cmd_rings(args):
    from .rings import RingLayout, describe, verify_iso, write_iso
    if args.media == "cd":
        from .cdrings import RingLayout, verify_iso, write_iso
    layout = RingLayout(textures=tuple(t.strip().upper() for t in args.textures.split(",")),
                        groups=args.groups, ring_width_mm=args.ring_width_mm, start_mm=args.start_mm,
                        r0_mm=args.r0_mm, pitch_um=args.pitch_um, bit_nm=args.bit_nm,
                        filler=args.filler.upper()).build()
    for line in describe(layout):
        print(line)
    if args.describe:
        return
    try:
        print(f"\nWriting {os.path.abspath(args.output)}")
        with ui.writing(args.output, layout.total_sectors) as log:
            spec_path = write_iso(args.output, layout, log=log)
    except ValueError as e:
        sys.exit(str(e))
    with ui.busy("Checking what was written..."):
        problems = verify_iso(args.output, layout)
    print("Verified: sampled sectors in every ring record the intended byte" if not problems
          else "VERIFY FAILED:\n  " + "\n  ".join(problems[:10]))
    print(f"Layout: {os.path.abspath(spec_path)}  (needed by ringscan)")
    print("Burn with any image burner (Windows Disc Image Burner works) and note the speed. "
          "The file system is an empty ISO 9660 placeholder.")
    if problems:
        sys.exit(1)


def cmd_ringscan(args):
    from .rings import RingLayout
    from .ringscan import analyse
    layout = RingLayout.load(args.layout)
    refs = args.refs or ("0D,AA" if layout.kind == "cd-texture-rings" else "A5,92")
    centre = tuple(float(v) for v in args.centre.split(",")) if args.centre else None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(args.out, f"ringscan-{stamp}")
    try:
        analyse(args.images, layout, out, dpi=args.dpi, centre=centre,
                refs=tuple(t.strip().upper() for t in refs.split(',')))
    except RuntimeError as e:
        sys.exit(str(e))
    print(f"\nrings.csv, textures.csv, summary.json and unrolled views: {os.path.abspath(out)}")


def cmd_calib(args):
    from .calib import CalLayout, describe, refine_layout, verify_iso, write_iso
    common = dict(start_mm=args.start_mm, end_mm=args.end_mm, guard_mm=args.guard_mm)
    try:
        if args.refine_from:
            with open(args.refine_from, encoding="utf-8") as f:
                fit = json.load(f).get("fit")
            if not fit:
                sys.exit(f"{args.refine_from} has no geometry fit")
            layout = refine_layout(fit, groups=args.groups or 20, **common)
        else:
            layout = CalLayout(s_range=args.s_range, s_step=args.s_step, groups=args.groups or 3,
                               r0_mm=args.r0_mm, pitch_um=args.pitch_um, bit_nm=args.bit_nm, **common).build()
    except ValueError as e:
        sys.exit(str(e))
    for line in describe(layout):
        print(line)
    if args.describe:
        return
    print(f"\nWriting {os.path.abspath(args.output)} (about a minute)")
    try:
        with ui.writing(args.output, layout.total_sectors) as log:
            spec_path = write_iso(args.output, layout, log=log)
    except ValueError as e:
        sys.exit(str(e))
    with ui.busy("Checking what was written..."):
        problems = verify_iso(args.output, layout)
    print("Verified: guards are pure, bands follow their patterns" if not problems
          else "VERIFY FAILED:\n  " + "\n  ".join(problems[:10]))
    print(f"Layout: {os.path.abspath(spec_path)}  (needed by calscan)")
    print("Burn with any image burner (Windows Disc Image Burner works). "
          "The file system is an empty ISO 9660 placeholder.")
    if problems:
        sys.exit(1)


def cmd_calscan(args):
    from .calib import CalLayout
    from .calscan import analyse
    layout = CalLayout.load(args.layout)
    centre = tuple(float(v) for v in args.centre.split(",")) if args.centre else None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(args.out, f"calscan-{os.path.splitext(os.path.basename(args.image))[0]}-{stamp}")
    try:
        analyse(args.image, layout, out, dpi=args.dpi, centre=centre)
    except RuntimeError as e:
        sys.exit(str(e))
    print(f"\nbands.csv, phase.csv, summary.json and unrolled.png: {os.path.abspath(out)}")


def cmd_geo(args):
    from .geo import Ladder, write_outputs
    if args.sectors not in (1, 16) or (args.media == "cd" and args.sectors != 1):
        sys.exit(f"--sectors {args.sectors}: geo reads 1 sector, or on a DVD 16 for one whole ECC block")
    ranges = None
    if args.ranges:
        try:
            ranges = [tuple(int(x) for x in part.split("-")) for part in args.ranges.split(",")]
        except ValueError:
            ranges = [()]
        if any(len(r) != 2 or r[0] >= r[1] for r in ranges):
            sys.exit(f"--ranges {args.ranges}: give LBA ranges as start-end, for example 70000-1900000 "
                     "or 2000-90000,120000-356000")
    elif args.rings_layout:
        from .rings import RingLayout
        lay = RingLayout.load(args.rings_layout)
        m = args.margin_sectors
        ranges = [(r["lba_start"] + m, r["lba_end"] - m) for r in lay.rings
                  if r["texture"].upper() == args.texture.upper()]
    if not args.sim:
        if sys.platform.startswith("linux"):
            from .device import raise_priority
        else:
            _need_windows()
            from .spti import raise_priority
        raise_priority()
    dev = _open(args)
    _check_disc(dev, args)
    _blu_ray_speed(dev, args)
    reader = _measuring(dev, args)
    ladder = Ladder(reader, ranges=ranges, r0_mm=args.r0_mm, pitch_um=args.pitch_um, bit_nm=args.bit_nm,
                    reps=args.reps, max_targets=args.max_targets, ref_lba=args.ref_lba,
                    speed_kbs=None if args.sim else args.speed, host_delay_ms=args.host_delay_ms, media=args.media,
                    chi2_abort=args.chi2_abort, sectors=args.sectors)
    ladder.tp.summary["identity"] = _identity(args, dev)
    progress, log = None, print
    if reader is not dev:
        progress = reader.progress = ui.Progress(ui.geo_status(ladder, reader), keys=ui.open_keys())
        log = ladder.log = progress.log
    out = _outdir(args, "geo", dev)
    stopped = None
    res = None
    try:
        res = ladder.run()
    except RuntimeError as e:
        log(f"stopped: {e}")
        stopped = str(e)
    finally:
        if progress:
            progress.close()
        dev.close() if hasattr(dev, "close") else None
        if ladder.targets and ladder.cov is not None:
            write_outputs(ladder, out, None if res else stopped or "interrupted")   # also for Ctrl+C or a drive that vanished
    at_terminal = ui.term().interactive
    detail = (lambda text: ui.say(text, "dim")) if at_terminal else print    # at a terminal the plain summary comes first
    if res:
        print()
        if at_terminal:
            ui.say(guide.geo_summary(res, len(ladder.targets)))
        detail(f"u = r0/b = {res['u']:.3f}, v = p/b = {res['v']:.7f}  (chi2/dof {res['chi2_per_dof']:.2f}, "
               f"residual rms {res['residual_rms_deg']:.3f} deg)")
        detail(f"With bit length {res['bit_nm_assumed']} nm: r0 {res['r0_mm_at_bit']:.5f} mm, "
               f"pitch {res['pitch_um_at_bit']:.6f} um")
        detail(f"Angle uncertainty across the measured span {res['measured_span_mm'][0]}-"
               f"{res['measured_span_mm'][1]} mm: {res['angle_sigma_measured_span_deg']:.3f} deg (1 sigma); "
               f"across {'25' if args.media == 'cd' else '24'}-58 mm: {res.get('angle_sigma_deg', float('nan')):.2f} deg")
    if res and res["chi2_per_dof"] > 2 and not at_terminal:     # at a terminal the advice below settles this
        print(f"The constant-pitch fit leaves more than noise. See whether a varying pitch fits better: "
              f"python tools/geo_polyfit.py {out}")
    if ladder.targets and ladder.cov is not None:
        print(f"targets.csv, summary.json, events.csv: {os.path.abspath(out)}")
        if not res:
            print("It stopped early, so `--geo latest` won't use these. Don't burn from them.")
    elif stopped not in mmc.NOT_READY:
        print("no results written: it stopped before the first fit. Run `timing` to see how noisy this drive is.")
    if progress and res:
        ui.say(f"Finished in {ui.clock(ui.time.monotonic() - progress.started)}", "dim")
    _next(guide.after_geo(args, res, out) if res else guide.after_geo_stop(args, stopped or ""))
    if res is None:     # scripts must not take a run that stopped for one that finished
        sys.exit(1)


def cmd_image(args):
    from . import imagedisc
    writer = imagedisc
    if args.media == "cd":
        from . import cdimage as writer
    fit = _geo_fit(args, args.media)
    if args.media == "cd" and fit.get("media") != "cd":
        sys.exit("CD image needs a CD geometry fit (media=cd); DVD fits must not be reused")
    u, v, bit = fit["u"], fit["v"], fit["bit_nm_assumed"]
    if args.along_track_frames:
        # Timing cannot see an along-track offset d (read completion vs written position): theta(n - d)
        # is the same spiral with u^2 - v d / pi. Measure d on a burned grid disc.
        import math
        from .cd import FRAME_BITS
        if args.media != "cd":
            sys.exit("--along-track-frames is for CD")
        u = math.sqrt(u * u - v * args.along_track_frames * FRAME_BITS / math.pi)
    if args.design_npy:
        import numpy as np
        design = np.load(args.design_npy)
        if design.shape != (imagedisc.SIZE, imagedisc.SIZE):
            sys.exit(f"design must be {imagedisc.SIZE} x {imagedisc.SIZE} cells of {imagedisc.CELL_MM} mm")
        if args.textures:
            design = design.astype(np.uint8)
        elif design.dtype != bool:
            sys.exit("a label design (not boolean) needs --textures, one per label")
        kind = f"design {os.path.basename(args.design_npy)}"
    elif args.picture:
        design = imagedisc.picture_design(args.picture, args.diameter_mm)
        if args.media == "cd":      # the file system sits here, and write_iso refuses a drawing on top of it
            kept = imagedisc.clear_inside(design, 26.0)
            if (kept != design).any():
                ui.say("The middle of a CD holds its file system, so the picture is left out inside 26 mm radius.", "dim")
            design = kept
        kind = f"picture {os.path.basename(args.picture)}"
    else:
        design = imagedisc.grid_design(r_min=26.0 if args.media == "cd" else 24.5,
                                      r_max=args.r_max, line=args.line_mm)
        kind = f"grid, {args.line_mm} mm lines"
    total = writer.sectors_to_radius(u, v, bit, args.r_max + 0.6)
    if args.media == "dvd":
        total = min(total, 2295104)
    else:
        from .cd import check_capacity
        check_capacity(total)
    tex = f"textures {' '.join(args.textures)}" if args.textures else f"dark {args.dark}, light {args.light}"
    print(f"{kind}, geometry u {u:.3f}, v {v:.7f} from {args.geo}; {total} sectors "
          f"({total * 2048 / 1e9:.2f} GB), {tex}")
    corr = imagedisc.load_correction(args.correction) if args.correction else None
    try:
        with ui.writing(args.output, total) as log:
            spec = writer.write_iso(args.output, design, u, v, bit, total, args.dark, args.light,
                                    meta={"geometry_from": os.path.abspath(args.geo), "design": kind,
                                          "along_track_frames": args.along_track_frames,
                                          "correction": os.path.abspath(args.correction) if args.correction else None},
                                    correction=corr, textures=args.textures, log=log)
    except ValueError as e:
        sys.exit(str(e))
    with ui.busy("Checking what was written..."):
        problems = writer.verify_iso(args.output, design, u, v, bit, total, args.dark, args.light, correction=corr,
                                     textures=args.textures)
    print("Verified: sampled sectors match the design" if not problems else "VERIFY FAILED: " + "; ".join(problems[:5]))
    prev = os.path.splitext(args.output)[0] + ".preview.png"
    if design.dtype == bool:
        imagedisc.preview(design, prev)
    else:
        from . import tiledisc
        tiledisc.preview(design, args.textures, prev)
    print(f"Spec: {os.path.abspath(spec)}\nPreview (data-side view): {os.path.abspath(prev)}")
    if args.media == "cd" and problems:
        sys.exit(1)
    if not problems:
        _next(guide.after_image(args.output, prev, args.geo))


def cmd_gridscan(args):
    from . import gridscan, imagedisc
    design = imagedisc.grid_design(r_min=26.0 if args.media == "cd" else 24.5,
                                  r_max=args.r_max, line=args.line_mm)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for path in args.images:
        out = os.path.join(args.out, f"gridscan-{os.path.splitext(os.path.basename(path))[0]}-{stamp}")
        kw = {"r_min": 26.5} if args.media == "cd" else {}
        gridscan.analyse(path, design, out, dpi=args.dpi, force_mirrored=None if args.auto_mirror else False, **kw)
        print(f"  phi.csv and summary.json: {os.path.abspath(out)}")


def cmd_correction(args):
    from .gridscan import fit_correction
    c = fit_correction(args.phi, args.output, degree=args.degree, geometry=args.geo)
    print(f"{c['points_used']} rings from {len(args.phi)} scans, fit residual rms {c['residual_rms_deg']:.4f} deg")
    print(f"Angle correction: {os.path.abspath(args.output)}  (use with image --correction)")


def cmd_disexport(args):
    from .disexport import export
    fit = _geo_fit(args, args.media)
    is_cd = fit.get("media") == "cd"
    if args.media and args.media != ("cd" if is_cd else "dvd"):
        sys.exit(f"--media {args.media} does not match {args.geo}, which measured a {'CD' if is_cd else 'DVD'}")
    if not args.sectors:
        _fail("A preset needs --sectors: the capacity of your disc (`info` prints it)", [guide.sectors_hint(args.geo)])
    span = fit["measured_span_mm"] if is_cd else (25.8, 54.4)
    try:
        out = export(args.geo, args.sectors, args.correction, args.output,
                     args.r_min or span[0], args.r_max or span[1],
                     args.id or ("discprobe-cd" if is_cd else "discprobe-dvd-r"),
                     args.name or ("CD (drive-timing calibration)" if is_cd else "DVD-R (drive-timing calibration)"),
                     args.along_track_frames)
    except ValueError as e:
        sys.exit(str(e))
    f = out["fit"]
    print(f"inner {f['innerRadiusMm']:.9f} mm, outer {f['outerRadiusMm']:.9f} mm, pitch shape "
          f"{f['pitchLinear']:.3e} {f['pitchQuadratic']:.3e} {f['pitchCubic']:.3e}")
    print(f"angle difference to the measured map over {f['fit_range_mm'][0]}-{f['fit_range_mm'][1]} mm: "
          f"max {f['max_angle_diff_deg']:.4f} deg, rms {f['rms_angle_diff_deg']:.4f} deg")
    print(f"DiscImageStudio {'CD' if is_cd else 'DVD'} preset object in {os.path.abspath(args.output)} (key 'preset')")
    if is_cd and not args.along_track_frames:
        print("Timing cannot see the CD along-track constant and none was given, so radial lines may come out "
              "twisted. Measure it on a burned disc, then use --along-track-frames.")
    _next(guide.after_disexport(is_cd and not args.along_track_frames))


def cmd_tiles(args):
    from . import imagedisc, tiledisc
    writer = imagedisc
    if args.media == "cd":
        from . import cdimage as writer
    fit = _geo_fit(args, args.media)
    if args.media == "cd" and fit.get("media") != "cd":
        sys.exit("CD tiles need a CD geometry fit (media=cd)")
    u, v, bit = fit["u"], fit["v"], fit["bit_nm_assumed"]
    geo = {"ring_edges_mm": tuple(args.ring_edges), "tile_mm": args.tile_mm, "cols": args.cols,
           "scale_mm": tuple(args.scale) if args.scale else None, "gap_mm": args.gap_mm,
           "shuffle_seed": args.shuffle}
    labels, textures, layout = tiledisc.design(args.palette, **geo)
    if args.media == "cd":
        textures = [{"A5": "0D", "92": "AA"}.get(t, t) for t in textures]
        layout.update(media="cd", id_dark="0D", id_light="AA")
    outer = max(args.ring_edges[-1], args.scale[1] if args.scale else 0)
    total = writer.sectors_to_radius(u, v, bit, outer + 0.6)
    if args.media == "dvd":
        total = min(total, 2295104)
    else:
        from .cd import check_capacity
        check_capacity(total)
    print(f"{sum(layout['sectors_per_ring'])} tiles, palette {' '.join(args.palette)}; geometry u {u:.3f}, "
          f"v {v:.7f} from {args.geo}; {total} sectors ({total * 2048 / 1e9:.2f} GB)")
    corr = imagedisc.load_correction(args.correction) if args.correction else None
    meta = {"geometry_from": os.path.abspath(args.geo), "design": "tile palette target",
            "correction": os.path.abspath(args.correction) if args.correction else None}
    with ui.writing(args.output, total) as log:
        spec = writer.write_iso(args.output, labels, u, v, bit, total, meta=meta, correction=corr, textures=textures, log=log)
    with ui.busy("Checking what was written..."):
        problems = writer.verify_iso(args.output, labels, u, v, bit, total, correction=corr, textures=textures)
    print("Verified: sampled sectors match the design" if not problems else "VERIFY FAILED: " + "; ".join(problems[:5]))
    base = os.path.splitext(args.output)[0]
    tiledisc.save_layout({**layout, "textures": textures}, base + ".tiles.json")
    tiledisc.preview(labels, textures, base + ".preview.png")
    print(f"Spec: {os.path.abspath(spec)}\nLayout: {os.path.abspath(base + '.tiles.json')}\n"
          f"Preview (data-side view, false colours): {os.path.abspath(base + '.preview.png')}")
    if args.media == "cd" and problems:
        sys.exit(1)
    if not problems:
        _next(guide.after_image(args.output, base + ".preview.png", args.geo))


def cmd_beacons(args):
    from . import beacondisc, imagedisc
    fit = _geo_fit(args)
    u, v, bit = fit["u"], fit["v"], fit["bit_nm_assumed"]
    labels, textures, layout = beacondisc.design()
    total = min(imagedisc.sectors_to_radius(u, v, bit, beacondisc.MARK_BAND_MM[1] + 0.6), 2295104)
    print(f"{sum(layout['sectors_per_ring'])} tiles, palette {' '.join(layout['palette'])}; geometry u {u:.3f}, "
          f"v {v:.7f} from {args.geo}; {total} sectors ({total * 2048 / 1e9:.2f} GB)")
    corr = imagedisc.load_correction(args.correction) if args.correction else None
    meta = {"geometry_from": os.path.abspath(args.geo), "design": "beacon target",
            "correction": os.path.abspath(args.correction) if args.correction else None}
    with ui.writing(args.output, total) as log:
        spec = imagedisc.write_iso(args.output, labels, u, v, bit, total, meta=meta, correction=corr, textures=textures, log=log)
    with ui.busy("Checking what was written..."):
        problems = imagedisc.verify_iso(args.output, labels, u, v, bit, total, correction=corr, textures=textures)
    print("Verified: sampled sectors match the design" if not problems else "VERIFY FAILED: " + "; ".join(problems[:5]))
    base = os.path.splitext(args.output)[0]
    beacondisc.save_layout({**layout, "textures": textures}, base + ".tiles.json")
    beacondisc.preview(labels, textures, base + ".preview.png")
    print(f"Spec: {os.path.abspath(spec)}\nLayout: {os.path.abspath(base + '.tiles.json')}\n"
          f"Preview (data-side view, false colours): {os.path.abspath(base + '.preview.png')}")
    if problems:
        sys.exit(1)
    _next(guide.after_image(args.output, base + ".preview.png", args.geo))


def cmd_tilescan(args):
    from . import tilescan
    for i, path in enumerate(args.scans):
        out = os.path.join(args.output_dir, f"{i + 1}_{os.path.splitext(os.path.basename(path))[0]}")
        s = tilescan.analyse(path, args.layout, out, dpi=args.dpi)
        for name, v in s["levels_a5_0_92_1"].items():
            print(f"    {name:24s} {v}")


def cmd_random(args):
    from .randomdisc import write_iso
    print(f"Writing {os.path.abspath(args.output)}: {args.sectors} sectors of seeded random data")
    with ui.writing(args.output, args.sectors) as log:
        write_iso(args.output, args.sectors, args.seed, media=args.media, log=log)
    if not ui.term().interactive:   # at a terminal the advice below says this, with the right next step
        print("Burn it with any image burner, then run `geo` on it.")
    _next(guide.after_random(args))


def cmd_selftest(args):
    from .selftest import run
    language = i18n.active()
    i18n.pin("en")      # the checks read the English text; Chinese has its own checks
    passed = run()
    i18n.unpin(language)
    if passed:
        _next(guide.after_selftest())
    sys.exit(0 if passed else 1)


def cmd_guide(args):
    from . import greetings
    from .banner import show
    show()
    if ui.term().interactive:
        ui.say(greetings.pick(first_time=not any(not r.simulated for r in guide.scan())))
        ui.say()
    media = getattr(args, "guide_media", None)
    if media is None:   # carry on with what was measured last
        newest = next((r for r in guide.scan() if not r.simulated and r.kind in ("timing", "geo")), None)
        media = newest.media if newest else "dvd"
    for line in guide.guide_lines(media, notes=ui.term().interactive):
        print(ui.term().style(line, "cyan") if line.lstrip().startswith("python ") else line)
    from . import completion
    if not completion.installed():
        ui.say(f"Tab completion: {guide.PROG} completion install", "dim")


def _pick_results(args):
    from . import picker
    t = ui.term()
    if not t.can_prompt():
        found = picker.groups(picker.geo_runs(None, args.out), args.out)
        for line in picker.plain_lists(found, args.sort, args.reverse) or [f"no geo results in {args.out}"]:
            print(line)
        return
    try:
        chosen = picker.choose(None, args.out, args.sort, args.reverse)
    except ValueError as e:
        sys.exit(str(e))
    if chosen is None:
        return
    print(f"You chose: {guide.short(chosen.path)} ({i18n.tr(chosen.describe())})")
    flag = " --media cd" if chosen.media == "cd" else ""
    print("Use it with:")
    print(ui.term().style(f"  {guide.PROG} image{flag} --geo {guide.short(chosen.path)} --picture my_picture.png --output iso/picture.iso", "cyan"))
    print(ui.term().style(f"  {guide.PROG} disexport --geo {guide.short(chosen.path)} --sectors <sectors> --output dis_preset.json", "cyan"))


def cmd_results(args):
    if args.pick:
        _pick_results(args)
        return
    found = [r for r in guide.scan(args.out) if not args.kind or r.kind == args.kind]
    if args.latest:
        real = [r for r in found if not r.simulated and (r.kind != "geo" or r.reliable())]
        real = real or [r for r in found if not r.simulated and r.kind == "geo" and r.geo_complete()]
        if not real:
            sys.exit(f"no complete {args.kind or ''} result in {args.out}".replace("  ", " "))
        print(real[0].path)
        return
    if not found:
        print(f"no results in {args.out}")
        return
    for r in found[:args.count]:
        print(f"{r.when:%m-%d %H:%M}  {r.kind:9s} {r.tag[:14]:14s} {i18n.tr(r.describe())}")
        print(f"  {r.path}")
    if len(found) > args.count:
        print(f"... and {len(found) - args.count} older (-n {len(found)} shows all)")


class _Parser(argparse.ArgumentParser):
    """argparse, plus a way out of the error for people at a terminal."""
    argv: list[str] = []
    commands: dict = {}
    last_out: str | None = None     # where a stopped run left its files

    def error(self, message):
        hint = None
        if ui.term().interactive:
            argv, commands = _Parser.argv, _Parser.commands
            parser = commands.get(argv[0], self) if argv else self
            hint = guide.parser_hint(message, argv, commands, parser._option_string_actions)
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n" + (f"{hint}\n" if hint else ""))


class _SpeedX(float):
    """--speed given as a multiple of 1x; its kB/s depend on --media."""


class _SpeedKbs(int):
    """A multiple already worked out for --media, remembered in case the disc turns out to be a Blu-ray."""
    multiple = None


def _speed(text: str):
    try:
        return _SpeedX(text[:-1]) if text[-1:].lower() == "x" else int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a speed: give kB/s like 5540, or a multiple like 4x") from None


# (group title, commands); `main` fills in what each one does.
COMMAND_GROUPS = (
    ("Start here", ("guide", "selftest", "list")),
    ("Measure a disc", ("info", "timing", "geo", "results")),
    ("Make a disc image", ("random", "image", "tiles", "beacons", "rings", "calib", "spokes")),
    ("Read scans of burned discs", ("gridscan", "correction", "tilescan", "ringscan", "calscan", "scan")),
    ("Use elsewhere", ("disexport",)),
)
LANG_NOTE = ("Language: --lang zh or --lang en, or DISCPROBE_LANG; at a terminal it follows the system. "
             "Scripts and pipes stay English unless --lang is given. --no-animation keeps the screen still.\n"
             "Tab completion: python -m discprobe completion install")
LANG_NOTE_ZH = ("语言：--lang zh 或 --lang en，也可以设置环境变量 DISCPROBE_LANG；在终端里默认跟随系统语言。"
                "脚本和管道始终是英文，除非写了 --lang。--no-animation 可以关掉动画。\n"
                "Tab 补全：python -m discprobe completion install")
WORKFLOW = """\
The usual path, on DVD (CD: add --media cd to each command; steps in docs/MANUAL.md):
  python -m discprobe random --output iso/random.iso    then burn it to a disc
  python -m discprobe timing --drive E:                 can this drive measure?
  python -m discprobe geo --drive E:                    measure the geometry
  python -m discprobe image --geo latest --picture my_picture.png --output iso/picture.iso
  python -m discprobe disexport --geo latest --sectors <sectors> --output dis_preset.json

At a terminal, --drive can be left out when there is one drive, and each command ends by printing the next one.
`python -m discprobe <command> -h` shows a command's options."""
EXAMPLES = {
    "timing": """\
examples:
  python -m discprobe timing --drive E:                 first look at a drive, 1 to 3 minutes
  python -m discprobe timing --drive E: --speed 4x      fix the read speed
  python -m discprobe timing --drive E: --sectors 16    whole DVD ECC blocks; was cleaner on one drive
  python -m discprobe timing --drive E: --media cd      CD (default speed 1411 kB/s = 8x)

choosing --speed: lower usually means less noise, but not every drive changes speed; the
"Rotation" and "Zone" lines show what it did. It takes kB/s or a multiple (1x: DVD 1385, CD 176.4, BD 4495).
  DVD  2.4x 3324   4x 5540   8x 11080
  CD   8x 1411    16x 2822   24x 4234

This --sectors is sectors per read. Not the same as the disc capacity in disexport --sectors.""",
    "geo": """\
examples:
  python -m discprobe geo --drive E:                    DVD, fixed at 4x
  python -m discprobe geo --drive E: --speed 3324       a slower speed that timing showed to be cleaner
  python -m discprobe geo --drive E: --media cd         CD, fixed at 1411 kB/s

choosing --ranges: the default (3-85 % of the recorded area) suits most discs. Leave out an area that
keeps failing or sits past a speed change: the run prints the LBA it stopped at, and `info` shows
the last LBA. Widening it covers more radius, if the drive reads that far cleanly.
  python -m discprobe geo --drive E: --ranges 70000-1900000""",
    "info": """\
examples:
  python -m discprobe info --drive E:     works on a blank disc too; shows the MID or ATIP and the sector count""",
    "random": """\
examples:
  python -m discprobe random --output iso/random.iso
  python -m discprobe random --media cd --output iso/cd-random.iso

Burn it onto a blank disc (Windows: right-click the .iso, Burn disc image), then run timing on it.""",
    "image": """\
examples:
  python -m discprobe image --geo latest --picture my_picture.png --output iso/picture.iso
  python -m discprobe image --geo results/geo-E-20261105-120000 --correction correction.json --picture my_picture.png
  python -m discprobe image --media cd --geo latest --along-track-frames 206 --output iso/cd-grid.iso

--geo takes a summary.json, a geo result folder, or `latest` (the newest complete real measurement).""",
    "disexport": """\
examples:
  python -m discprobe disexport --geo latest --sectors <sectors> --r-min 25.8 --r-max 54.4 --output dis_preset.json
  python -m discprobe disexport --geo latest --sectors <sectors> --correction correction.json --output dis_preset_cd.json

--sectors is the capacity of your disc: take it from `info` on a blank disc, and enter the same number in
DiscImageStudio. One user found its read-from-disc too high. Not the same as timing --sectors.
--geo takes a summary.json, a geo result folder, `latest`, or `pick` to choose. A CD fit gives a CD preset; --media is only a check.""",
    "results": """\
examples:
  python -m discprobe results                 what has been run, newest first
  python -m discprobe results geo             only geo runs
  python -m discprobe results geo --latest    just the newest folder that can be relied on, for use in scripts
  python -m discprobe results --pick          choose a geo result: by disc and drive, then by precision or date""",
    "guide": """\
Reads the results folder, shows which steps are done and prints the next command. It does not touch the drive.""",
}


def _build_parser():
    p = _Parser(prog=guide.PROG, usage=f"{guide.PROG} <command> [options]", epilog=WORKFLOW,
                description="Measure a burned disc's spiral from read timing, then put pictures on discs. "
                            "Drive commands only read.", formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(required=True, metavar="<command>", help=argparse.SUPPRESS, prog=guide.PROG)

    sp = sub.add_parser("list", help="list optical drives")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("guide", help="show which steps are done and the next command to run")
    sp.add_argument("--media", dest="guide_media", choices=("dvd", "cd"),
                    help="which steps to show (default: what you measured last)")
    sp.set_defaults(func=cmd_guide)

    sp = sub.add_parser("results", help="list past results, newest first")
    sp.add_argument("kind", nargs="?", help="only this kind, e.g. geo, timing, info")
    sp.add_argument("--latest", action="store_true",
                    help="print only the newest folder, skipping simulated runs, stopped geo runs and ones judged too noisy")
    sp.add_argument("--pick", action="store_true", help="choose a geo result: by disc and drive, then by precision or date")
    sp.add_argument("--sort", choices=("precision", "date"), default="precision", help="for --pick: what to sort by (default: precision)")
    sp.add_argument("--reverse", action="store_true", help="for --pick: the other way round")
    sp.add_argument("-n", dest="count", type=int, default=15, help="how many to list (default 15)")
    sp.add_argument("--out", default="results", help="results directory (default: results)")
    sp.set_defaults(func=cmd_results)

    def common(sp):
        sp.add_argument("--drive", help="drive letter, e.g. E:; `list` shows them. At a terminal it can be left out "
                                        "when there is one drive")
        sp.add_argument("--sim", choices=["cav", "clv", "cav-nofua", "cav-flush"],
                        help="use the simulated drive (nofua: FUA ignored; flush: FUA ignored but a "
                             "zero-length FUA read drops the cache)")
        sp.add_argument("--transport", choices=["auto", "spti", "imapi"], default="auto",
                        help="Windows command path: spti may need an elevated terminal; imapi (IMAPI2 "
                             "IDiscRecorder2Ex) works as a standard user; auto tries spti, then imapi")
        sp.add_argument("--seed", type=int, default=1, help="simulation seed")
        sp.add_argument("--out", default="results", help="output directory (default: results)")

    sp = sub.add_parser("info", help="dump drive and disc information")
    common(sp)
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("timing", help="cache/FUA test, CAV check, sector phase measurement")
    common(sp)
    sp.add_argument("--read", choices=["auto", "read10", "read12", "readcd"], default="auto")
    sp.add_argument("--reps", type=int, default=40, help="R/X pairs per phase target")
    sp.add_argument("--period-reads", type=int, default=60, help="reads per zone in the period test")
    sp.add_argument("--targets", help="comma-separated disc fractions, default 0.15,0.35,0.55,0.75,0.95")
    sp.add_argument("--ref", type=float, default=0.05, help="reference sector as a disc fraction")
    sp.add_argument("--speed", type=_speed,
                    help="read speed in kB/s or as a multiple: 4x, or DVD 8x = 11080, 16x = 22160 "
                         "(omit to leave as is, sends SET CD SPEED otherwise)")
    sp.add_argument("--cav", action="store_true",
                    help="set the Rotational Control bit of SET CD SPEED; MMC defines it for writing, "
                         "so whether reads change is only known from the period test")
    sp.add_argument("--sectors", type=int, default=1,
                    help="sectors per measurement read, not the disc size; 16 reads one whole aligned DVD ECC block")
    sp.add_argument("--host-delay-ms", type=float, default=25.0,
                    help="random pause (0..N ms) before each timed read, so repeated reads do not all "
                         "span the same number of revolutions; should exceed one revolution")
    sp.add_argument("--evict-sectors", type=int, default=1024,
                    help="sectors read elsewhere before each measurement when the cache cannot be bypassed")
    sp.add_argument("--force", action="store_true", help="run the phase test even if the drive did not look CAV")
    sp.add_argument("--max-minutes", type=float, default=15.0, help="give up after this long (0 = no limit)")
    sp.set_defaults(func=cmd_timing)

    sp = sub.add_parser("spokes", help="generate the radial-spoke calibration pattern")
    sp.add_argument("--output", default="spokes.png")
    sp.add_argument("--radius-mm", type=float, default=58.0,
                    help="disc radius at the image edge: DiscImageStudio canvas radius (CD 57.5, DVD/BD the generation outer radius)")
    sp.add_argument("--size", type=int, default=4096, help="image size in pixels")
    sp.set_defaults(func=cmd_spokes)

    sp = sub.add_parser("scan", help="measure spoke rotation versus radius on a flatbed scan")
    sp.add_argument("image", help="scan file (PNG/TIFF; avoid JPEG)")
    sp.add_argument("--spec", required=True, help="the .spokes.json written next to the pattern")
    sp.add_argument("--dpi", type=float, help="scan resolution if the file does not record it")
    sp.add_argument("--centre", help="approximate disc centre X,Y in pixels if detection fails")
    sp.add_argument("--r-min", type=float, default=20.0)
    sp.add_argument("--r-max", type=float, default=59.0)
    sp.add_argument("--out", default="results")
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("rings", help="write the DVD texture-ring test ISO (one recorded byte per ring)")
    sp.add_argument("--output", default="rings.iso")
    sp.add_argument("--textures", default="A5,B9,66,64,E4,92,RND",
                    help="scrambled-domain bytes in hex, or RND; must include A5 and 92")
    sp.add_argument("--groups", type=int, default=3, help="repeats of the full texture set, inner to outer")
    sp.add_argument("--ring-width-mm", type=float, default=1.4)
    sp.add_argument("--start-mm", type=float, default=25.0, help="radius where the first ring starts")
    sp.add_argument("--filler", default="92", help="texture between the data start and the first ring")
    sp.add_argument("--r0-mm", type=float, default=24.0, help="nominal data start radius for placing rings")
    sp.add_argument("--pitch-um", type=float, default=0.74)
    sp.add_argument("--bit-nm", type=float, default=133.3)
    sp.add_argument("--describe", action="store_true", help="print the layout without writing")
    sp.set_defaults(func=cmd_rings)

    sp = sub.add_parser("ringscan", help="measure texture brightness on scans of the ring disc")
    sp.add_argument("images", nargs="+", help="one or more scans (PNG/TIFF, no auto adjustments); "
                                              "rotate the disc between scans for repeats")
    sp.add_argument("--layout", required=True, help="the .rings.json written next to the ISO")
    sp.add_argument("--refs", help="dark,bright references (DVD A5,92; CD 0D,AA) defining levels 0 and 1; "
                                                    "use the darkest and brightest textures the scan shows")
    sp.add_argument("--dpi", type=float, help="scan resolution if the file does not record it")
    sp.add_argument("--centre", help="approximate disc centre X,Y in pixels if detection fails")
    sp.add_argument("--out", default="results")
    sp.set_defaults(func=cmd_ringscan)

    sp = sub.add_parser("calib", help="write a multi-hypothesis calibration ISO (bracketing disc, or refinement disc)")
    sp.add_argument("--output", default="cal.iso")
    sp.add_argument("--refine-from", help="summary.json of a calscan run: write the refinement disc, every band "
                                          "drawn with that fit")
    sp.add_argument("--s-range", type=float, default=0.012, help="largest local-rate offset tried, e.g. 0.012 = 1.2 %%")
    sp.add_argument("--s-step", type=float, default=0.002)
    sp.add_argument("--groups", type=int, help="repeats of the hypothesis set (default 3; 20 for refinement)")
    sp.add_argument("--start-mm", type=float, default=25.0)
    sp.add_argument("--end-mm", type=float, default=57.0)
    sp.add_argument("--guard-mm", type=float, default=0.2)
    sp.add_argument("--r0-mm", type=float, default=24.0, help="centre geometry of the sweep")
    sp.add_argument("--pitch-um", type=float, default=0.74)
    sp.add_argument("--bit-nm", type=float, default=133.3)
    sp.add_argument("--describe", action="store_true", help="print the layout without writing")
    sp.set_defaults(func=cmd_calib)

    sp = sub.add_parser("calscan", help="fit the disc geometry from a scan of a calibration disc")
    sp.add_argument("image", help="scan (PNG/TIFF, grey or colour, no auto adjustments)")
    sp.add_argument("--layout", required=True, help="the .cal.json written next to the ISO")
    sp.add_argument("--dpi", type=float)
    sp.add_argument("--centre", help="approximate disc centre X,Y in pixels if detection fails")
    sp.add_argument("--out", default="results")
    sp.set_defaults(func=cmd_calscan)

    sp = sub.add_parser("geo", help="measure the spiral geometry of a burned DVD from read timing (ladder)")
    common(sp)
    sp.add_argument("--speed", type=_speed, default=5540,
                    help="read speed to fix, in kB/s or as a multiple like 4x (default 4x = 5540; CD 8x = 1411)")
    sp.add_argument("--ranges", help="readable LBA ranges a-b,c-d (default 3-85 %% of the recorded area); see below")
    sp.add_argument("--rings-layout", help="texture-ring layout file: use only the rings of --texture")
    sp.add_argument("--texture", default="RND")
    sp.add_argument("--margin-sectors", type=int, default=3000, help="kept away from ring edges")
    sp.add_argument("--ref-lba", type=int)
    sp.add_argument("--reps", type=int, default=24, help="reference/target read pairs per rung")
    sp.add_argument("--sectors", type=int, default=1,
                    help="sectors per measurement read, not the disc size: 1, or on a DVD 16 for one whole ECC block")
    sp.add_argument("--max-targets", type=int, default=22)
    sp.add_argument("--host-delay-ms", type=float, default=25.0)
    sp.add_argument("--r0-mm", type=float, default=24.0, help="prior geometry (loose)")
    sp.add_argument("--pitch-um", type=float, default=0.74)
    sp.add_argument("--bit-nm", type=float, default=133.3)
    sp.add_argument("--chi2-abort", type=float, default=25.0,
                    help="stop when chi2/dof of the constant-pitch fit exceeds this; raise it for media "
                         "whose pitch varies (CD: a smooth S of a few degrees), the 90-degree residual "
                         "check still catches whole-turn errors")
    sp.set_defaults(func=cmd_geo)

    sp = sub.add_parser("image", help="write a picture ISO placed with a measured geometry (grid test by default)")
    sp.add_argument("--geo", required=True, help="summary.json of a geo run, its folder, latest, or pick to choose")
    sp.add_argument("--output", default="iso/grid.iso")
    sp.add_argument("--picture", help="greyscale picture to threshold instead of the grid test")
    sp.add_argument("--design-npy", help="prepared boolean design (True = dark), 6000 x 6000 cells of 0.02 mm, data-side view")
    sp.add_argument("--diameter-mm", type=float, default=116.0, help="the picture's longer side on the disc, in mm; it keeps its shape")
    sp.add_argument("--r-max", type=float, default=56.0, help="outer radius of the drawing")
    sp.add_argument("--line-mm", type=float, default=0.3, help="grid line width")
    sp.add_argument("--correction", help="angle-correction file (phi(r) measured on a burned grid)")
    sp.add_argument("--along-track-frames", type=float, default=0.0,
                    help="CD: frames the read completion lies beyond the timing model, measured on a burned grid")
    sp.add_argument("--dark", default="A5")
    sp.add_argument("--light", default="B9", help="light texture (B9 scanned brightest on Ritek F1)")
    sp.add_argument("--textures", nargs="+", help="for a label design (uint8): one texture per label, "
                    "e.g. A5 92 8B00 RND MIX:92,4F")
    sp.set_defaults(func=cmd_image)

    sp = sub.add_parser("tiles", help="write a self-locating texture palette target (IDs + swatches in every tile)")
    sp.add_argument("--geo", required=True, help="summary.json of a geo run, its folder, latest, or pick to choose")
    sp.add_argument("--output", default="iso/tiles.iso")
    sp.add_argument("--palette", nargs="+", default=list(DEFAULT_PALETTE),
                    help="up to 9 textures: a byte (A5), a repeated sequence (8B00), RND, or MIX:92,4F")
    sp.add_argument("--correction", help="angle-correction file")
    sp.add_argument("--ring-edges", type=float, nargs="+", default=[25.0, 33.0, 41.0, 49.0, 57.0],
                    help="radii (mm) separating the tile rings")
    sp.add_argument("--tile-mm", type=float, default=8.0, help="tile size along the arc")
    sp.add_argument("--cols", type=int, default=7, help="cell columns per tile (4 hold the ID, the rest swatches)")
    sp.add_argument("--scale", type=float, nargs=2, metavar=("R0", "R1"), help="add an angle scale band (mm)")
    sp.add_argument("--gap-mm", type=float, default=0.5, help="background gap between tiles")
    sp.add_argument("--shuffle", type=int, metavar="SEED",
                    help="give every tile its own random swatch order (decouples texture from position)")
    sp.set_defaults(func=cmd_tiles)

    sp = sub.add_parser("beacons", help="write the beacon target (tiles readable from one photo, no whole-disc fit)")
    sp.add_argument("--geo", required=True, help="summary.json of a geo run, its folder, latest, or pick to choose")
    sp.add_argument("--output", default="iso/beacons.iso")
    sp.add_argument("--correction", help="angle-correction file")
    sp.set_defaults(func=cmd_beacons)

    sp = sub.add_parser("tilescan", help="read IDs and swatch levels from flatbed scans of the tile palette target")
    sp.add_argument("scans", nargs="+", help="scan images (PNG/TIFF/JPEG)")
    sp.add_argument("--layout", default="iso/tiles.tiles.json", help="layout file written by the tiles command")
    sp.add_argument("--dpi", type=float, default=600.0)
    sp.add_argument("--output-dir", default="results/tilescan")
    sp.set_defaults(func=cmd_tilescan)

    sp = sub.add_parser("gridscan", help="measure line straightness on scans of the burned grid test")
    sp.add_argument("images", nargs="+")
    sp.add_argument("--dpi", type=float, default=600.0)
    sp.add_argument("--r-max", type=float, default=56.0, help="must match the image command")
    sp.add_argument("--line-mm", type=float, default=0.3, help="must match the image command")
    sp.add_argument("--auto-mirror", action="store_true", help="let the (weak) mirror test decide orientation")
    sp.add_argument("--out", default="results")
    sp.set_defaults(func=cmd_gridscan)

    sp = sub.add_parser("correction", help="fit an angle-correction curve from gridscan phi.csv files")
    sp.add_argument("phi", nargs="+", help="phi.csv files written by gridscan")
    sp.add_argument("--output", default="angle_correction.json")
    sp.add_argument("--degree", type=int, default=4)
    sp.add_argument("--geo", help="summary.json of the geo run the grid disc was burned with (recorded only)")
    sp.set_defaults(func=cmd_correction)

    sp = sub.add_parser("disexport", help="fit the measured angle map as a DiscImageStudio DVD or CD preset (cubic pitch)")
    sp.add_argument("--geo", required=True, help="summary.json of a geo run, its folder, latest, or pick to choose; "
                                                    "a CD fit gives a CD preset")
    sp.add_argument("--correction", help="angle-correction file from the correction command")
    sp.add_argument("--sectors", type=int, help="the disc's capacity, not how much was burned (`info` on a blank disc prints it); required")
    sp.add_argument("--r-min", type=float, help="fit range: use the measured span (DVD default 25.8, CD the span geo measured)")
    sp.add_argument("--r-max", type=float, help="DVD default 54.4, CD the span geo measured")
    sp.add_argument("--along-track-frames", type=float, default=0,
                    help="CD only: along-track constant in frames, as in image --along-track-frames")
    sp.add_argument("--id")
    sp.add_argument("--name")
    sp.add_argument("--output", default="dis_preset.json")
    sp.set_defaults(func=cmd_disexport)

    sp = sub.add_parser("random", help="write a random-data ISO for full-disc timing calibration")
    sp.add_argument("--output", default="iso/random.iso")
    sp.add_argument("--sectors", type=int, default=2295104, help="how much to burn, not the disc size; it has to fit on the blank")
    sp.add_argument("--seed", type=int, default=1)
    sp.set_defaults(func=cmd_random)

    sp = sub.add_parser("selftest", help="parser checks and end-to-end runs on the simulated drive and a synthetic scan")
    sp.set_defaults(func=cmd_selftest)

    # Add media only to commands with an implemented CD path. Existing DVD
    # defaults are retained verbatim; explicit CD options override CD defaults.
    cd_defaults = {
        "rings": dict(output="iso/cd-rings.iso", textures="0D,AA,10,63,RND", filler="AA",
                      r0_mm=25.0, pitch_um=1.6, start_mm=26.0, ring_width_mm=2.0),
        "random": dict(output="iso/cd-random.iso", sectors=359600),  # IMAPI needs room to close the disc
        "geo": dict(r0_mm=25.0, pitch_um=1.6, speed=1411, reps=32, max_targets=36, host_delay_ms=35.0),
        "timing": dict(speed=1411, host_delay_ms=35.0),  # a turn takes about 29 ms at this speed
        "image": dict(output="iso/cd-grid.iso", dark="0D", light="AA", line_mm=0.6),
        "tiles": dict(output="iso/cd-tiles.iso", palette=["0D", "AA", "10", "63", "RND", "0DAA", "00FF", "1063", "0D10AA"]),
        "gridscan": dict(line_mm=0.6),
    }
    for name in cd_defaults:
        sub.choices[name].add_argument("--media", choices=("dvd", "cd"), default="dvd",
                                       help="disc type; cd also switches the defaults to CD values (default: dvd)")
    sub.choices["disexport"].add_argument("--media", choices=("dvd", "cd"),
                                          help="check that --geo measured this disc type; the fit decides the preset")
    for name in ("rings", "image", "tiles"):
        sub.choices[name].add_argument(
            "--cd-sector", choices=("mode2form1", "mode1"), default="mode2form1",
            help="CD only: sector layout the burner writes; IMAPI2 data burns are Mode 2 Form 1 "
                 "(user data from byte 24), so textures are pre-scrambled for that unless you burn Mode 1")
    # Each command's help names what it does, and the top level lists the commands in workflow order.
    tr = i18n.tr
    helps = {a.dest: tr(a.help) for a in sub._choices_actions}
    for name, parser in sub.choices.items():
        parser.description = helps[name]
        parser.epilog = i18n.block(name, EXAMPLES.get(name))
        parser.formatter_class = argparse.RawDescriptionHelpFormatter
        i18n.localize_parser(parser)
    p.description = tr(p.description) + "\n\n" + "\n\n".join(
        f"{tr(title)}:\n" + "\n".join(f"  {name:11s} {helps[name]}" for name in names) for title, names in COMMAND_GROUPS)
    p.epilog = i18n.block("workflow", p.epilog)
    if ui.term().interactive:   # scripts read the help as it always was
        p.epilog += "\n\n" + (LANG_NOTE_ZH if i18n.active() == "zh" else LANG_NOTE)
    i18n.localize_parser(p)
    return p, sub, cd_defaults


def _main(argv=None):
    p, sub, cd_defaults = _build_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    _Parser.argv, _Parser.commands = raw_args, sub.choices
    if not raw_args and ui.term().interactive:
        args = argparse.Namespace(func=cmd_guide)
        return args.func(args)
    args = p.parse_args(argv)
    if getattr(args, "media", "dvd") == "cd":
        from .cd import BIT_NM, set_sector_layout
        if hasattr(args, "cd_sector"):
            set_sector_layout(args.cd_sector)
        name = raw_args[0]
        defaults = cd_defaults.get(name, {}).copy()
        if name in ("rings", "geo"):
            defaults["bit_nm"] = BIT_NM
        # argparse accepted these, so a shortened option such as --sp is a prefix of exactly one flag.
        supplied = {a.split("=")[0] for a in raw_args if a.startswith("--") and len(a) > 2}
        for key, value in defaults.items():
            if not any(("--" + key.replace("_", "-")).startswith(given) for given in supplied):
                setattr(args, key, value)
    if isinstance(getattr(args, "speed", None), _SpeedX):
        one_x = 176.4 if getattr(args, "media", "dvd") == "cd" else 1385
        multiple = float(args.speed)
        args.speed = _SpeedKbs(round(multiple * one_x))
        args.speed.multiple = multiple
        ui.say(f"--speed is {args.speed} kB/s", "dim")
    elif getattr(args, "speed", None) and args.speed < 100:
        ui.say(f"Note: --speed is in kB/s, so {args.speed} is very slow. For a multiple, write {args.speed}x.", "yellow")
    args.func(args)


def main(argv=None):
    try:
        flag, rest = i18n.take_flag(list(sys.argv[1:] if argv is None else argv))
    except ValueError as e:
        sys.exit(str(e))
    i18n.setup(flag, ui.term())
    if "--no-animation" in rest:    # like --lang, it never reaches summary.json
        rest = [a for a in rest if a != "--no-animation"]
        ui.term().animate = False
    try:
        if rest[:1] == ["completion"]:      # not a parser command, so piped help and errors stay as they were
            from . import completion
            return completion.main(rest[1:], _build_parser, ui.term().stream)
        _main(rest)
    except _Rerun as again:
        main(list(sys.argv[1:] if argv is None else argv) + again.extra)
    except KeyboardInterrupt:
        kept = f" What was measured so far is in {os.path.abspath(_Parser.last_out)}" if _Parser.last_out else ""
        print(f"\nStopped by Ctrl+C.{kept}", file=sys.stderr)
        sys.exit(130)
    except ModuleNotFoundError as e:
        package = (e.name or "").split(".")[0]
        if package not in ("numpy", "scipy", "PIL"):
            raise
        sys.exit(f"this command needs {'Pillow' if package == 'PIL' else package}. "
                 f"Install what disc-probe uses with: {guide.INSTALL}")
    except OSError as e:
        sys.exit(_os_error(e))


if __name__ == "__main__":
    main()
