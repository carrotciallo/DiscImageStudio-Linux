"""CD image sampling in the physical domain, with an independent inverse verifier.

The sampling unit is one 12-data-symbol half-frame (F2 slots 0..11 or 16..27),
the CD equivalent of the DVD writer's 16-byte group. A sequence is phased by
physical frame * 32 + F2 slot, including the intervening parity slots. It does
not restart at a user sector boundary. No EFM period/colour is implied by a
byte sequence: merging bits, parity and the drive's DSV decisions matter.
"""

from __future__ import annotations

import json
import math
import os

import numpy as np

from . import cd, imagedisc as I, iso9660
from .calib import theta

CHUNK = 2048


def sectors_to_radius(u, v, bit_nm, radius):
    n = math.pi * ((radius / (bit_nm * 1e-6)) ** 2 - u * u) / v
    return int(n // cd.SECTOR_BITS)


def _labels(design, u, v, bit_mm, frame, slot, correction):
    # Data halves are contiguous on the physical track, unlike user byte groups.
    middle_slot = np.where(slot < 12, 5.5, 21.5)
    n = frame * 588 + 51 + middle_slot * 17
    r = bit_mm * np.sqrt(u * u + v * n / math.pi)
    th = -theta(n, u, v)
    if correction is not None:
        th += np.radians(correction(r))
    ix = np.floor((r * np.cos(th) + I.HALF_MM) / I.CELL_MM).astype(np.int64)
    iy = np.floor((I.HALF_MM - r * np.sin(th)) / I.CELL_MM).astype(np.int64)
    ok = (ix >= 0) & (ix < I.SIZE) & (iy >= 0) & (iy < I.SIZE)
    return np.where(ok, design[np.clip(iy, 0, I.SIZE - 1), np.clip(ix, 0, I.SIZE - 1)], 0)


def texture_bytes(spec, frame, slot, random_bytes):
    if spec == "RND":
        return random_bytes
    if spec.startswith("MIX:"):
        pool = np.array([int(b, 16) for b in spec[4:].split(",")], np.uint8)
        return pool[random_bytes.astype(np.int64) % len(pool)]
    seq = np.frombuffer(bytes.fromhex(spec), np.uint8)
    if len(seq) == 0:
        raise ValueError("empty texture")
    return seq[(frame * 32 + slot) % len(seq)]


def _sector_q(design, textures, u, v, bit_mm, lba0, count, correction):
    lbas = np.arange(lba0, lba0 + count)
    frame, slot = cd.user_to_physical(lbas[:, None], np.arange(2048)[None, :])
    # Evaluate the geometry once per physical half-frame, then gather in user
    # order. CIRC scatters a sector, but many bytes still share one sample.
    first, last = int(frame.min()), int(frame.max())
    labels_by_frame = _labels(design, u, v, bit_mm, np.arange(first, last + 1)[:, None],
                              np.array([0, 16])[None, :], correction)
    labels = labels_by_frame[frame - first, (slot >= 16).astype(np.int8)]
    rnd = I.texture_bytes("RND", lbas)
    q = np.empty(labels.shape, np.uint8)
    for i, spec in enumerate(textures):
        m = labels == i
        q[m] = texture_bytes(spec, frame[m], slot[m], rnd[m])
    return q


def _new_paths(path, suffix):
    base = os.path.splitext(path)[0]
    paths = [path, base + suffix, base + ".preview.png", base + ".tiles.json"]
    if any(os.path.exists(p) for p in paths):
        raise ValueError(f"CD output already exists: {paths}; choose a new filename")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


def write_iso(path, design, u, v, bit_nm, total_sectors, dark="0D", light="AA", log=print,
              meta=None, correction=None, textures=None):
    cd.check_capacity(total_sectors)
    texs = I._textures(design, dark, light, textures)
    # Metadata sectors and their CIRC footprint must be in background label 0.
    f, s = cd.user_to_physical(np.arange(16, 21)[:, None], np.arange(2048)[None, :])
    if np.any(_labels(design, u, v, bit_nm * 1e-6, f, s, correction) != 0):
        raise ValueError("ISO 9660 sectors overlap the drawing; leave an inner background margin")
    for t in texs:
        texture_bytes(t, np.array([0]), np.array([0]), np.array([0], np.uint8))
    _new_paths(path, ".image.json")
    done, next_report = 0, 0.0
    with open(path, "xb") as fh:
        while done < total_sectors:
            count = min(CHUNK, total_sectors - done)
            q = _sector_q(design, texs, u, v, bit_nm * 1e-6, done, count, correction)
            fh.write((q ^ cd.MASK).tobytes())
            done += count
            if done / total_sectors >= next_report:
                log(f"  {100 * done / total_sectors:5.1f} %")
                next_report += 0.2
    iso9660.add(path, total_sectors, "DISCPROBE_CD_IMAGE")
    spec = {"kind": "cd-picture", "media": "cd", "user_offset": cd.USER_OFFSET, "u": u, "v": v, "bit_nm": bit_nm,
            "total_sectors": total_sectors, "textures": texs, "cell_mm": I.CELL_MM,
            "sampling": "physical 12-data-symbol half-frame", "origin": "ECMA-130 fig C.4, sector byte 0 at F1 slot 1",
            "physical_origin_measured": False, **(meta or {})}
    if design.dtype == bool:
        spec.update(dark=dark, light=light)
    spec_path = os.path.splitext(path)[0] + ".image.json"
    with open(spec_path, "x", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2)
    return spec_path


def inverse_positions(lba0, count):
    """Independent figure C.4 enumeration: physical output -> raw input.

    No forward-map tables or writer sampling helpers are used. Enumerate the
    output frames, discard parity and sector overhead, then recover user indices.
    """
    slots = np.array(list(range(12)) + list(range(16, 28)))
    words = np.repeat([0, 4, 8, 1, 5, 9, 2, 6, 10, 3, 7, 11], 2)
    # Explicit output delays from figure C.4, D=4 (A, B for each word).
    delays = np.array([3, 6, 11, 14, 19, 22, 27, 30, 35, 38, 43, 46,
                       65, 68, 73, 76, 81, 84, 89, 92, 97, 100, 105, 108])
    frames = np.arange(lba0 * 98, (lba0 + count) * 98 + 108)[:, None]
    raw = ((frames - delays) * 24 + 2 * words + np.tile([0, 1], 12)) ^ 1
    lbas, byte = raw // 2352, raw % 2352 - cd.USER_OFFSET
    ok = (lbas >= lba0) & (lbas < lba0 + count) & (byte >= 0) & (byte < 2048)
    return lbas[ok], byte[ok], np.broadcast_to(frames, raw.shape)[ok], np.broadcast_to(slots, raw.shape)[ok]


def verify_iso(path, design, u, v, bit_nm, total_sectors, dark="0D", light="AA", samples=300,
               seed=3, correction=None, textures=None, full=False, reconstruction=None):
    """Inverse reconstruct physical samples, compare bytes and optionally splat a PNG.

    full=True reads every payload byte, except the five filesystem sectors.
    The raster shows only controlled symbols, not parity or optical appearance.
    """
    if os.path.getsize(path) != total_sectors * 2048:
        return ["size mismatch"]
    texs = I._textures(design, dark, light, textures)
    if full:
        ranges = [(a, min(32, total_sectors - a)) for a in range(0, total_sectors, 32)]
    else:
        picks = {0, total_sectors - 1, *np.random.default_rng(seed).integers(21, total_sectors, samples).tolist()}
        ranges = [(int(a), 1) for a in sorted(picks)]
    sums = np.zeros((1200, 1200), np.float64) if reconstruction else None
    hits = np.zeros((1200, 1200), np.int64) if reconstruction else None
    problems = []
    # Independent bit-stream scrambler, rather than the writer's byte mask.
    bits, reg = [], 1
    for _ in range(2340 * 8):
        bits.append(reg & 1)
        reg = (reg >> 1) ^ (0x4000 if (reg ^ (reg >> 1)) & 1 else 0)
    first = cd.USER_OFFSET - 12  # the scrambler starts at sector byte 12
    mask = np.packbits(np.array(bits, np.uint8), bitorder="little")[first:first + 2048]
    with open(path, "rb") as fh:
        for start, count in ranges:
            fh.seek(start * 2048)
            data = np.frombuffer(fh.read(count * 2048), np.uint8).reshape(count, 2048)
            lba, byte, frame, slot = inverse_positions(start, count)
            keep = ~np.isin(lba, list(iso9660.SECTORS))
            lba, byte, frame, slot = (a[keep] for a in (lba, byte, frame, slot))
            rec = data[lba - start, byte] ^ mask[byte]
            # Reconstruct the group's location with the rationalized closed form.
            n = frame * 588 + np.where(slot < 12, 144.5, 416.5)
            s = np.sqrt(u ** 2 + v * n / np.pi)
            angle = -2 * n / (s + u)
            radius = bit_nm / 1e6 * s
            if correction is not None:
                angle += correction(radius) * np.pi / 180
            x, y = radius * np.cos(angle), radius * np.sin(angle)
            col = np.floor((x + 60) * 50).astype(int)
            row = np.floor((60 - y) * 50).astype(int)
            inside = (row >= 0) & (row < 6000) & (col >= 0) & (col < 6000)
            label = np.where(inside, design[np.clip(row, 0, 5999), np.clip(col, 0, 5999)], 0)
            want = np.empty(rec.shape, np.uint8)
            rnd = I.texture_bytes("RND", np.arange(start, start + count))[lba - start, byte]
            for j, t in enumerate(texs):
                m = label == j
                if t == "RND":
                    want[m] = rnd[m]
                elif t.startswith("MIX:"):
                    pool = np.array([int(a, 16) for a in t[4:].split(",")], np.uint8)
                    want[m] = pool[rnd[m].astype(int) % len(pool)]
                else:
                    seq = np.frombuffer(bytes.fromhex(t), np.uint8)
                    want[m] = seq[(32 * frame[m] + slot[m]) % len(seq)]
            bad = rec != want
            if np.any(bad):
                problems.append(f"LBA {lba[bad][0]} byte {byte[bad][0]}: inverse physical reconstruction differs")
                if len(problems) >= 10:
                    break
            if sums is not None:
                # Actual bytes classified against the texture at this physical phase.
                val = np.zeros(rec.shape)
                for j, t in enumerate(texs):
                    candidate = texture_bytes(t, frame, slot, rnd)
                    val[rec == candidate] = j
                ix = np.clip(((x + 60) * 10).astype(int), 0, 1199)
                iy = np.clip(((60 - y) * 10).astype(int), 0, 1199)
                np.add.at(sums, (iy, ix), val)
                np.add.at(hits, (iy, ix), 1)
    if sums is not None:
        from PIL import Image
        raster = np.divide(sums, hits, out=np.zeros_like(sums), where=hits > 0)
        scale = 255 / max(1, len(texs) - 1)
        Image.fromarray(np.where(hits > 0, 255 - np.clip(raster * scale, 0, 255), 255).astype(np.uint8)).save(reconstruction)
    return problems
