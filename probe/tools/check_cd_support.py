"""Reproduce unattended CD delivery checks; never opens an optical drive.

Run from the repository root: python -X utf8 tools/check_cd_support.py
Creates new ISO files only. Use a fresh --prefix for another run.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from discprobe import cd, cdimage, imagedisc, iso9660, randomdisc, rings


def baseline_module(name):
    source = subprocess.check_output(["git", "show", f"main:discprobe/{name}.py"], cwd=ROOT).decode("utf-8")
    module = types.ModuleType(f"discprobe._baseline_{name}")
    module.__package__ = "discprobe"
    sys.modules[module.__name__] = module
    exec(compile(source, f"main:discprobe/{name}.py", "exec"), module.__dict__)
    return module


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dvd_regression():
    """Byte-identical DVD writer outputs against main, including filesystem sectors."""
    original_datetime = iso9660.datetime.datetime

    class FixedDate(original_datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 4, 12, 0, tzinfo=tz)

    iso9660.datetime.datetime = FixedDate
    checks = {}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for name, current in [("rings", rings), ("randomdisc", randomdisc), ("imagedisc", imagedisc)]:
                old = baseline_module(name)
                paths = [str(Path(tmp) / f"{name}-{i}.iso") for i in range(2)]
                for module, path in zip((old, current), paths):
                    if name == "rings":
                        lay = module.RingLayout(groups=2, ring_width_mm=0.01, start_mm=24.02).build()
                        module.write_iso(path, lay, log=lambda *_: None)
                    elif name == "randomdisc":
                        module.write_iso(path, 512, log=lambda *_: None)
                    else:
                        design = imagedisc.grid_design()
                        module.write_iso(path, design, 24 / 133.3e-6, 0.74e-3 / 133.3e-6,
                                         133.3, 512, log=lambda *_: None)
                hashes = [digest(p) for p in paths]
                assert hashes[0] == hashes[1], (name, hashes)
                checks[name] = {"identical": True, "sha256": hashes[0]}
    finally:
        iso9660.datetime.datetime = original_datetime
    return checks


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prefix", default="cd-support-20261104")
    args = p.parse_args()
    evidence = ROOT / "evidence" / args.prefix
    evidence.mkdir(exist_ok=True)
    output = ROOT / "iso"
    geo = evidence / "nominal-geometry.json"
    if geo.exists():
        raise SystemExit(f"choose a fresh --prefix: {geo} exists")
    fit = {"media": "cd", "u": cd.R0_MM / (cd.BIT_NM * 1e-6),
           "v": cd.PITCH_UM * 1e3 / cd.BIT_NM, "bit_nm_assumed": cd.BIT_NM,
           "measured": False, "note": "standard nominal geometry, NOT a timing measurement"}
    geo.write_text(json.dumps({"fit": fit}, indent=2), encoding="utf-8")
    result = {"physical_drive_commands": 0, "burns": 0, "geometry_measured": False,
              "dvd_writer_regression": dvd_regression(), "images": {}}
    commands = {
        "rings": ["rings", "--media", "cd"],
        "random": ["random", "--media", "cd"],
        "grid": ["image", "--media", "cd", "--geo", str(geo)],
        "tiles": ["tiles", "--media", "cd", "--geo", str(geo)],
    }
    for kind, command in commands.items():
        path = output / f"{args.prefix}-{kind}.iso"
        command += ["--output", str(path)]
        print("Running:", " ".join(command), flush=True)
        r = subprocess.run([sys.executable, "-X", "utf8", "-m", "discprobe", *command],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        (evidence / f"{kind}-generation.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
        assert r.returncode == 0, r.stdout + r.stderr
        sectors = path.stat().st_size // 2048
        cd.check_capacity(sectors)
        result["images"][kind] = {"path": str(path), "sectors": sectors,
                                 "bytes": path.stat().st_size, "sha256": digest(path), "command": command}
    # Full grid reconstruction is independent of generation: enumerate physical
    # symbols, invert CIRC, read ISO bytes, and splat the controlled data to a raster.
    grid = result["images"]["grid"]
    design = imagedisc.grid_design(r_min=26.0, line=0.6)
    problems = cdimage.verify_iso(grid["path"], design, fit["u"], fit["v"], cd.BIT_NM, grid["sectors"],
                                  full=True, reconstruction=str(evidence / "grid-reconstructed.png"))
    assert not problems, problems
    result["grid_full_inverse"] = {"all_payload_bytes_match": True,
                                    "checked_bytes": (grid["sectors"] - 5) * 2048,
                                    "excluded_filesystem_sectors": [16, 17, 18, 19, 20]}
    (evidence / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
