# discimagestudio-linux

[简体中文](README.md) | English

A Linux GUI for DiscImageStudio: compose a picture, solve it with the
official CLI, and burn it onto a DVD — with a burn-safety pass that
makes any picture burnable.

A Linux frontend for the official DiscImageStudio GUI. The operation
surface mirrors the official WPF edition, all disc mathematics is
delegated to the official CLI, and none of the projection or solving
math is reimplemented here. The official CLI and disc-probe are
vendored in this repository (see "Bundled backends"), so a clone is
complete.

## Architecture

- Shell: native rendering with MyGo (github.com/egoist/mygo),
  widgets from the Onevra component library with a light theme
- Backends: the official DiscImageStudio CLI as a subprocess
  (`solve` / `simulate` / `selftest`); burning via
  `xorriso -as cdrecord -dao`; media probing via
  `dvd+rw-mediainfo`; calibration drives disc-probe as a subprocess
- Imaging: layer compositing in Go (golang.org/x/image); canvas
  preprocessing replicates the reference PIL pipeline (autocontrast
  cutoff=1 + UnsharpMask r6/80%/2 on the Y channel of YCbCr),
  visually equivalent to the reference output

## Bundled backends

- `official/`: the unmodified official CLI v1.5.0 (linux-x64)
  binary, with its LICENSE and THIRD-PARTY-NOTICES. Version and
  sha256 are pinned in `official/VERSION.json` (verified against
  upstream's published SHA256SUMS). The GUI uses the bundled copy
  by default; if Settings point at an external CLI whose sha256
  differs from the pin, the home page shows a notice —
  informational only, it never blocks work.
- `probe/`: disc-probe (bczhc's port, GPL-3.0). The calibration
  page runs `python3 -m discprobe` in this directory; this
  project's fitting scripts and preset JSONs live alongside.
  Provenance and trimming notes are in NOTICE.

## Pages

- Home: pipeline status, geometry presets, and an overview of the
  current parameters
- Design: multi-layer compositing (position / height / rotation
  via sliders, numeric inputs, canvas dragging and wheel scaling),
  a fixed view field, WYSIWYG
- Calibration: drives disc-probe timing (rotation speed / CAV
  determination) and geo (geometry fitting); fit results can be
  exported as solver presets
- Export: geometry and all solve parameters editable, ISO
  generation with readback preview (the official simulate render)
- Burn: media status, speed selection, burning and eject
- Settings: CLI path, work directory, burner device and speed

## Burn safety

Large flat dark areas are burn killers: after the solver's tone
processing they become ECC-block-scale plates of a single pit
pattern, which can make a burner die mid-disc with a media write
error — while flat bright areas (sparse pit patterns) are
naturally safe. The export pipeline therefore has a fixed,
single-pass construction (`burnsafe.go`) that makes any picture
burnable:

- Canvas areas not covered by the picture default to white
  (sparse pits), not black
- As the last compositing step, the canvas is scanned cell by
  cell in the same pass: a cell whose local mean is too low and
  which holds almost no above-threshold white pixels (the exact
  class-level shape of a flat dark field) has pixels flipped to
  white in a dispersed order under an exact quota, lifting the
  cell mean to a safety floor — calibration experiments show the
  solver's realized dark-class share is determined by local mean
  luminance alone, and the floor corresponds to a share of about
  0.75, below the 0.80 danger line
- One pass: no post-check, no re-solving, no knob for the user to
  worry about; brightness and friends are purely cosmetic again,
  and areas with real detail (above-threshold highlights) are not
  touched, pixel for pixel

Field notes on the measured drive and media are in the
[Appendix](APPENDIX.md): wake-up and power for the Apple USB
SuperDrive A1379 (GX40N mechanism) with CMC MAG. AM3 media, its
calibration values, and this drive's data-shape compatibility
boundary. (The appendix is in Chinese.)

## Build and run

Requirements: Go ≥ 1.24, xorriso, dvd+rw-tools (media probing),
eject (ejecting). The backends are bundled; there is nothing else
to fetch.

```sh
./run.sh          # build and launch
go test ./...     # tests (parity tests against reference outputs need DIS_FIXTURE_DIR)
```

Settings live in `~/.config/dis-gui/settings.json`; outputs
(canvas.png / disc.iso / simulate.png) land in the work directory
from Settings. When the CLI/probe paths are left at their
defaults, they resolve to the bundled copies first.

Hook: `DISGUI_OPEN=<image path>` loads that image as a layer at
startup and lands on the Design page.

## Known limitations

- DVD only; the official GUI's CD / Blu-ray tiers are not
  replicated
- The bundled CLI is the linux-x64 build; on other platforms,
  point Settings at your platform's official CLI (a version
  mismatch will be flagged)
- Calibration timing/geo needs an already-burned disc in the drive
- This project is a frontend: geometry, solving and readback
  rendering are the official CLI's job, and its version behaviour
  directly shapes the output

## License

GPL-3.0, see LICENSE. The relationship to the upstream project is
described in NOTICE.
