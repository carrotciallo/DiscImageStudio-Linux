"""CD acceptance tests: standard mapping, independent reconstruction and timing."""

from __future__ import annotations

import itertools
import math
import os
import tempfile

import numpy as np

from . import cd, cdimage, cdrings, imagedisc, ringscan
from .calib import theta
from .geo import Ladder
from .sim import SimDrive


def _mapping(c):
    print("CD scrambler and forward/inverse CIRC")
    vector = bytes.fromhex("01 80 00 60 00 28 00 1e 80 08 60 06 a8 02 fe 81 80 60 60 28 28 1e 9e 88 68 66 ae aa fc 7f 01 e0")
    c.check(cd.SCRAMBLE[12:44].tobytes() == vector and cd.lfsr_period() == 32767,
            "Annex B 32-byte prefix and 32767-bit period")
    # Independent byte-at-a-time formulation, cross-checked with redumper's
    # cd_scrambler.ixx at fa5d2434c755a2dc26199fee2d20fc246a9e51c9.
    reg, reference = 1, []
    for _ in range(2340):
        reference.append(reg & 255)
        for _ in range(8):
            reg = (reg // 2) + (16384 if (reg & 1) != ((reg // 2) & 1) else 0)
    c.check(cd.SCRAMBLE[12:].tobytes() == bytes(reference), "all 2340 scramble bytes agree with redumper formulation")
    c.check(np.array_equal(cd.payload_for(0x0D, 0), cd.payload_for(0x0D, 12345)),
            "scrambler resets after every sector sync")
    f, s = cd.user_to_physical(0, np.array([0, 1]))
    c.check(f.tolist() == [22, 19] and s.tolist() == [5, 4], "clause 16 adjacent swap before CIRC")
    ref = [-72, -143, -256, -327, -440, -511, -646, -717, -830, -901, -1014, -1085,
           -1556, -1627, -1740, -1811, -1924, -1995, -2130, -2201, -2314, -2385, -2498, -2569]
    c.check((cd.INPUT_SLOT - 24 * cd.DELAY).tolist() == ref,
            "all 24 DIS 46fa699 DelayFor values agree with figure C.4")
    rng = np.random.default_rng(713)
    lba = rng.integers(0, cd.CAPACITY, 8000)
    byte = rng.integers(0, 2048, 8000)
    q = rng.integers(0, 256, 8000, dtype=np.uint8)
    payload = q ^ cd.MASK[byte]
    frame, slot = cd.user_to_physical(lba, byte)
    back_lba, back_byte, ok = cd.physical_to_user(frame, slot)
    n = cd.channel_position(frame, slot)
    recovered = payload ^ cd.MASK[back_byte]
    c.check(bool(ok.all() and np.array_equal(lba, back_lba) and np.array_equal(byte, back_byte)
                 and np.array_equal(q, recovered) and np.all(n % 588 == 51 + 17 * slot)),
            "8000 random bytes round-trip value, sector, offset and channel position")
    cd.set_sector_layout("mode2form1")
    try:
        rec = cd.payload_for(np.full(2048, 0x0D, np.uint8)) ^ cd.SCRAMBLE[24:24 + 2048]
        f24, s24 = cd.user_to_physical(3, 0)
        il2, ib2, _, _ = cdimage.inverse_positions(97, 2)
        f2, s2 = cd.user_to_physical(il2, ib2)
        _, b2, ok2 = cd.physical_to_user(f2, s2)
    finally:
        cd.set_sector_layout("mode1")
    f16, s16 = cd.user_to_physical(3, 8)
    c.check(bool(np.all(rec == 0x0D) and (f24, s24) == (f16, s16) and len(il2) == 2 * 2048
                 and ok2.all() and np.array_equal(b2, ib2)),
            "Mode 2 Form 1 layout: textures pre-scrambled at byte 24, user byte 0 sits where Mode 1 byte 8 does")
    il, ib, ff, ss = cdimage.inverse_positions(97, 5)
    f, s = cd.user_to_physical(il, ib)
    c.check(len(il) == 5 * 2048 and np.array_equal(f, ff) and np.array_equal(s, ss),
            "independent inverse enumeration agrees across sector boundaries")
    _, _, ok = cd.physical_to_user(np.arange(32), np.arange(32))
    c.check(not np.any(ok[[12, 13, 14, 15, 28, 29, 30, 31]]), "parity slots are uncontrollable")
    f, s = cd.raw_to_physical(2351)
    c.check(int(f) == 202 and int(s) == 26 and cd.read_end_bits(0) == 206 * 588,
            "last raw pair spans frames 202/205; completion includes 108 tail frames")
    # The other byte of the final pair has the maximum delay.
    f, s = cd.raw_to_physical(2350)
    c.check(int(f) == 205 and int(s) == 27, "last raw-pair B symbol is at frame 205 slot 27")


def _iso(c):
    print("CD rings and physical-domain image ISO")
    lay = cdrings.RingLayout(groups=2, ring_width_mm=0.01, start_mm=25.05).build()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "rings.iso")
        cdrings.write_iso(path, lay, log=lambda *_: None)
        c.check(not cdrings.verify_iso(path, lay), f"small CD rings: {lay.total_sectors} sectors verified")
        with open(path, "r+b") as f:
            f.seek(lay.rings[3]["lba_start"] * 2048 + 100)
            b = f.read(1)
            f.seek(-1, 1)
            f.write(bytes([b[0] ^ 1]))
        c.check(bool(cdrings.verify_iso(path, lay)), "CD rings verifier detects a flipped byte")
        # A real 6000x6000 label map, with boundaries crossing the CIRC footprint.
        design = np.zeros((6000, 6000), np.uint8)
        design[:3000, :] = 1
        design[:, 3000:] += 2
        # Leave the ISO metadata footprint outside the drawing.
        x, y = imagedisc._grid_coords()
        design[np.hypot(x, y) < 25.03] = 0
        u, v = cd.R0_MM / (cd.BIT_NM * 1e-6), cd.PITCH_UM * 1e3 / cd.BIT_NM
        tex = ["AA", "0D", "10AA63", "MIX:10,63"]
        path = os.path.join(tmp, "image.iso")
        corr = lambda r: 0.15 * (r - 25)
        cdimage.write_iso(path, design, u, v, cd.BIT_NM, 512, textures=tex, correction=corr, log=lambda *_: None)
        c.check(not cdimage.verify_iso(path, design, u, v, cd.BIT_NM, 512, textures=tex, correction=corr, full=True),
                "every byte inverse-reconstructed: labels, physical sequences, MIX and correction")
        with open(path, "r+b") as f:
            f.seek(123 * 2048 + 42)
            value = f.read(1)
            f.seek(-1, 1)
            f.write(bytes([value[0] ^ 1]))
        c.check(bool(cdimage.verify_iso(path, design, u, v, cd.BIT_NM, 512, textures=tex, correction=corr, full=True)),
                "independent CD image reconstruction detects corruption")
        try:
            cdimage.write_iso(path, design, u, v, cd.BIT_NM, 512, textures=tex, log=lambda *_: None)
            c.check(False, "CD output overwrite refused")
        except ValueError:
            c.check(True, "CD output overwrite refused")
    for sectors in (20, cd.CAPACITY + 1):
        try:
            cd.check_capacity(sectors)
            c.check(False, "invalid CD capacity rejected")
        except ValueError:
            c.check(True, f"invalid CD capacity {sectors} rejected")


def _ladder(c):
    print("CD timing ladder: four +/-1% geometries, 35 ms reread overhead")
    b = cd.BIT_NM * 1e-6
    for su, sv in itertools.product((-0.01, 0.01), repeat=2):
        u, v = cd.R0_MM / b * (1 + su), cd.PITCH_UM * 1e-3 / b * (1 + sv)
        sim = SimDrive(media="cd", seed=7, reread_delay_ms=35, cd_u=u, cd_v=v)
        lad = Ladder(sim, media="cd", speed_kbs=None, log=lambda *_: None)
        rep = lad.run()
        n = np.linspace(0, 0.85 * cd.CAPACITY * cd.SECTOR_BITS, 400)
        error = np.degrees(theta(n, lad.u, lad.v) - theta(n, u, v))
        span = float(np.ptp(error))
        c.check(span < 1.5, f"u {su:+.0%}, v {sv:+.0%}: {len(lad.targets)} rungs, 0-85% error {span:.3f} deg")
        c.check(rep["media"] == "cd" and lad.tp.summary["setup"]["read_method"] == "read12"
                and lad.tp.strategy == "fua", "CD data READ(12)+FUA and media-tagged fit")


def _scan(c):
    from .rings_selftest import synth_scan, DPI
    print("CD synthetic ringscan")
    lay = cdrings.RingLayout().build()
    truth = {"0D": 0.0, "AA": 1.0, "10": 0.3, "63": 0.65, "RND": 0.5}
    img = synth_scan(lay, truth=truth, r0_true=24.96, refs=("0D", "AA"))
    with tempfile.TemporaryDirectory() as tmp:
        s = ringscan.analyse(None, lay, tmp, dpi=DPI, images=[("cd", img)], refs=("0D", "AA"), log=lambda *_: None)
    fit = s["scans"][0]["radial_fit"]
    err = max(abs(s["levels"]["L"][t] - truth[t]) for t in truth)
    c.check(fit is not None and abs(fit["r0_mm"] - 24.96) < 0.03 and err < 0.03,
            f"CD ring edges and reference-normalised levels: max error {err:.3f}")


def run(c):
    _mapping(c)
    _iso(c)
    _ladder(c)
    _scan(c)
    _efm(c)
    _timing(c)


def _efm(c):
    from . import efm
    print("CD EFM reference modulation (not a hardware encoder prediction)")
    rng = np.random.default_rng(142)
    state, output, consistent = efm.Boundary(), [], True
    for _ in range(120):
        levels, end = efm.encode_frame(rng.integers(0, 256, 33), state)
        consistent &= end.dsv - state.dsv == int(levels.sum()) and len(levels) == 588
        output.append(levels)
        state = end
    levels = np.concatenate(output)
    runs = np.diff(np.flatnonzero(np.diff(levels) != 0))
    c.check(consistent and runs.min() >= 3 and runs.max() <= 11,
            f"588 bits/frame, NRZI sum = DSV, runs {runs.min()}T-{runs.max()}T")


def _timing(c):
    from .timing import TimingProbe, NoReadableDisc
    print("CD timing CAV/CLV, sector sizes and READ CD rejection")
    for mode in ("cav", "clv"):
        sim = SimDrive(media="cd", mode=mode, seed=7, reread_delay_ms=35)
        probe = TimingProbe(sim, media="cd", log=lambda *_: None)
        res = probe.run()
        c.check(res["period"]["rotation"]["mode"] == mode.upper() and probe.strategy == "fua"
                and probe.block == 1 and all(e.command != "readcd" for e in probe.events),
                f"CD {mode}: rotation recognised, 2048-byte READ(12)+FUA, one-sector units")
        if mode == "cav":
            errors = []
            for target in res["phase"]["targets"]:
                truth = sim.true_phase_deg(target["ref_lba"], target["target_lba"])
                errors.append(abs((target["phase"]["mean_deg"] - truth + 180) % 360 - 180))
            c.check(max(errors) < 1.5, f"CD CAV phase matches completion-tail model: worst {max(errors):.3f} deg")
    sim = SimDrive(media="cd")
    try:
        TimingProbe(sim, media="cd", read_method="readcd", log=lambda *_: None).setup()
        c.check(False, "READ CD rejected for CD timing")
    except NoReadableDisc:
        c.check(True, "READ CD rejected for CD timing")
