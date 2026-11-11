"""Build the offline Windows package: disc-probe with its own Python, unpacked and double-clicked, nothing installed.

    python tools/build_winpack.py --ref experiment/tui-lab --label lab --out D:/disc-probe-dist

It downloads the official embeddable Python and the wheels once, into OUT/cache, and writes OUT/disc-probe-LABEL-win64.zip
with its SHA-256 beside it. Run it with the same minor version of Python as PYTHON below, so the versions it pins exist.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

PYTHON = "3.13.14"
PACKAGES = ("numpy", "pillow", "scipy")
SOURCE = ("discprobe", "tools", "docs/MANUAL.md", "README.md", "README.en.md", "LICENSE")
LEAVE_OUT = ("__pycache__", "tests", "test", "*.pyi", "*.pdb")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

START = """@echo off
rem Double-click this. It opens a window ready for disc-probe, and installs nothing.
where wt >nul 2>nul
if %errorlevel%==0 (
    start "" wt -d "%~dp0." cmd /k "%~dp0python\\shell.cmd"
    exit /b
)
cmd /k "%~dp0python\\shell.cmd"
"""

# The window's own PATH finds this Python, so the commands disc-probe prints work as written.
SHELL = """@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "PATH=%~dp0;%PATH%"
title disc-probe
python -m discprobe guide
echo.
echo Type the commands above in this window. Close it when you are done.
echo 把上面的命令输入到这个窗口。用完直接关闭就行。
"""

NOTICE = """disc-probe, GPL-3.0-or-later. See LICENSE. Source: https://github.com/Ashley-QwQ/disc-probe

This package also carries, unchanged except for removed test folders:
  Python {python} (python\\LICENSE.txt)
  {packages}
Their licences are in python\\Lib\\site-packages\\*.dist-info.

To remove it, delete this folder. Results are in results\\ here, and Merge Sectors keeps its board in
%LOCALAPPDATA%\\disc-probe.
"""


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="main")
    ap.add_argument("--label", default="main")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if ".".join(map(str, sys.version_info[:2])) != ".".join(PYTHON.split(".")[:2]):
        sys.exit(f"run this with Python {PYTHON}, not {sys.version.split()[0]}")
    cache = os.path.join(a.out, "cache")
    os.makedirs(cache, exist_ok=True)
    embed = os.path.join(cache, f"python-{PYTHON}-embed-amd64.zip")
    if not os.path.exists(embed):
        url = f"https://www.python.org/ftp/python/{PYTHON}/python-{PYTHON}-embed-amd64.zip"
        print("downloading", url, flush=True)
        urllib.request.urlretrieve(url, embed)
    pins = [f"{p}=={importlib.metadata.version(p)}" for p in PACKAGES]
    wheels = os.path.join(cache, "site-packages")
    if not os.path.isdir(wheels):
        print("downloading", " ".join(pins), flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-compile", "--only-binary=:all:", "--platform", "win_amd64",
                        "--python-version", PYTHON.rsplit(".", 1)[0], "--implementation", "cp", "--target", wheels, *pins], check=True)
    commit = subprocess.run(["git", "-C", HERE, "rev-parse", "--short", a.ref], check=True, capture_output=True, text=True).stdout.strip()
    name = f"disc-probe-{a.label}-win64"
    root = os.path.join(a.out, name)
    if os.path.isdir(root):
        shutil.rmtree(root)
    py = os.path.join(root, "python")
    os.makedirs(py)
    with zipfile.ZipFile(embed) as z:
        z.extractall(py)
    tag = "python" + "".join(PYTHON.split(".")[:2])
    # Isolated by this file: nothing from the machine's own Python or environment gets in.
    with open(os.path.join(py, tag + "._pth"), "w", encoding="ascii") as f:
        f.write(f"{tag}.zip\n.\nLib\\site-packages\n..\nimport site\n")
    shutil.copytree(wheels, os.path.join(py, "Lib", "site-packages"), ignore=shutil.ignore_patterns(*LEAVE_OUT))
    source = subprocess.run(["git", "-C", HERE, "archive", "--format=tar", a.ref, *SOURCE], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(source)) as t:
        t.extractall(root, filter="data")
    with open(os.path.join(root, "开始 Start.bat"), "w", encoding="ascii", newline="\r\n") as f:
        f.write(START)
    with open(os.path.join(py, "shell.cmd"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(SHELL)
    with open(os.path.join(root, "NOTICE.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(NOTICE.format(python=PYTHON, packages=", ".join(pins)))
    with open(os.path.join(root, "package.json"), "w", encoding="utf-8") as f:
        json.dump(dict(ref=a.ref, commit=commit, python=PYTHON, packages=pins, embed_sha256=sha256(embed)), f, indent=1)
    archive = shutil.make_archive(root, "zip", a.out, name)
    digest = sha256(archive)
    with open(archive + ".sha256", "w", encoding="ascii") as f:
        f.write(f"{digest}  {os.path.basename(archive)}\n")
    print(f"{archive}: {os.path.getsize(archive) / 1e6:.0f} MB, commit {commit}, sha256 {digest[:20]}")


if __name__ == "__main__":
    main()
