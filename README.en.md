# Disc Image Studio for Linux

[简体中文](README.md) | English

A Linux port of DiscImageStudio: etch visible images onto the surface of CD / DVD / Blu-ray discs (DiscT@2-style disc-surface drawing).

Ported from upstream [JiaFeiMiao-K-Cat/DiscImageStudio](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio) (GPL-3.0): the core algorithms were made cross-platform (image decoding via StbImageSharp, PNG encoding via a built-in implementation, WPF dependencies removed from the engines), and a Linux command-line host, a burning path, and an Avalonia GUI were added. The Windows WPF application is out of scope for this repository.

> **Temporarily unverified**: burning and the GUI have not yet been validated by burning a real disc; this note will be updated and real screenshots added once validation is complete.

## Components

- **Cross-platform core**: the Core plus the CD / DVD / Blu-ray engines — the same solver and encoding algorithms as upstream, targeting .NET 10.
- **Command line** (`src/DiscImageStudio.Cli`): the full generate / preview / burn workflow.
- **GUI** (`src/DiscImageStudio.App.Avalonia`): Generate / Preview / Burn pages, plus a simple Design page: a single layer placed in millimetres (drag to move, wheel or slider to scale, rotate), with guide circles marking the data ring; the composed 4096x4096 export feeds straight into generation. Shares the same command catalog and burning implementation as the CLI. The multi-layer .discproj projects and calibration-session workspaces of the WPF app were not ported.
- **Burning**: shells out to `xorriso` (ISO writing and media blanking) and `cdrdao` (CUE track writing) instead of reimplementing the MMC layer.

## Requirements

- Linux (developed and self-tested on an Arch-based distribution)
- .NET 10 SDK
- For burning: the `xorriso` and `cdrdao` command-line tools on PATH

## Build

```bash
dotnet build DiscImageStudio.slnx
```

## Command-line usage

```bash
dotnet run --project src/DiscImageStudio.Cli -- <command> [options]
```

Commands (see `--help` for full details):

| Module | Commands |
| --- | --- |
| CD | `cd-generate`, `cd-preview-warp`, `cd-preview-track` |
| DVD | `solve`, `encode`, `calibrate`, `simulate`, `selftest` |
| Blu-ray | `bd-info`, `bd-probe`, `bd-encode`, `bd-generate` |
| Burning | `burn-devices`, `burn` |
| Spoke calibration | `calibrate-spoke`, `calibrate-fit`, `calibrate-selftest` |

Examples:

```bash
# DVD: solve an image into an ISO
... -- solve --image art.png --iso-output out.iso --total-sectors 2297888

# DVD: render a generated ISO as a disc-surface preview
... -- simulate --iso out.iso --output preview.png --inner-radius-mm 24 --outer-radius-mm 58

# CD: generate WAV+CUE
... -- cd-generate --input art.png --output track.wav

# Blu-ray: generate an ISO (sector count must be a multiple of 32)
... -- bd-generate --input art.png --output out.iso --total-sectors 32000
```

(`...` stands for `dotnet run --project src/DiscImageStudio.Cli`.)

## GUI

```bash
dotnet run --project src/DiscImageStudio.App.Avalonia
```

Screenshots: to be added after real-hardware validation.

## Burning and safety design

```bash
# List optical drives and burning tools
... -- burn-devices

# Burn an ISO (without --yes this only probes the media and prints the plan)
... -- burn --device /dev/sr0 --image out.iso
# Burn for real, then read back and verify the SHA-256
... -- burn --device /dev/sr0 --image out.iso --verify --yes

# Spoke calibration: render the test pattern (spokes + measurement rings),
# burn it with a nominal geometry, measure the spoke rotation at each ring
... -- calibrate-spoke --output spoke.png
# Fit the true spiral geometry (pitch / revolutions) from the phase errors
... -- calibrate-fit --samples "25:-11.1,30:-51.8,35:-49.6,40:-20.7,45:24.0,50:87.9,55:158.2"
```

- Without `--yes`, `burn` only probes the media and prints the commands it would run; nothing is written.
- Non-blank media is refused unless `--blank` is given; media whose state cannot be probed is refused as well.
- `--verify` (ISO only) reads back the image length from the device after burning and compares SHA-256 hashes.
- Redrawing an image on rewritable (RW) media requires a full blank; images on write-once media cannot be changed.

## Verification status

- The engine regression suite `selftest` passes fully (including pixel-exact PNG codec round-trip assertions).
- Generation pipeline exercised for real: two `solve` runs produce identical SHA-256 output; `simulate`, `cd-generate`, and `bd-generate` all produce real artifacts.
- Burn command composition and both safety gates are covered by stub-tool tests across five paths; **burning on a real drive is still pending verification** (see the note at the top).

## License and upstream

GPL-3.0-or-later, same as upstream. This repository is an independently maintained Linux port; please file usage issues here first, and refer to the upstream repository for algorithm-level questions.
