# disc-probe

English | [简体中文](README.md)

disc-probe uses an ordinary optical drive to measure the spiral geometry of a disc, then burns pictures onto the data side of DVD-R or CD-R. You don't need to take photos or mark points by hand.

<p>
<img src="docs/showcase/qingming_title.jpg" width="42%" alt="Title and part of Along the River During the Qingming Festival on the data side of a DVD-R">
<img src="docs/showcase/qingming_full.jpg" width="55%" alt="The whole disc, with the painting laid out in two rings">
</p>

*Along the River During the Qingming Festival* on a Ritek F1 DVD-R, straight from the burner. The geometry came entirely from read timing, and the disc was burned once, with no test burn, photo calibration or scan correction. These are phone photos, cropped to the disc and downsized, with the background blurred.

## How it works

To burn a picture on the data side, you need to know the angle at which sector N lands on the disc. Track pitch and bit length differ very slightly from batch to batch. Over tens of thousands of turns that adds up, and the picture twists into a whirlpool. The usual fix is to burn a calibration pattern, photograph it, mark points and correct over several rounds.

disc-probe has the drive measure this instead. On a disc spinning at constant speed, a sector finishes reading at the moment it passes under the head. Read two sectors in turn, convert the difference in completion time to an angle, and you know how far apart they are on the disc. Each reading only gives the angle modulo 360°, so the tool works outward in steps, using the earlier steps to predict the number of whole turns. 22 steps cover a DVD and 36 cover a CD.

<picture>
<source media="(prefers-color-scheme: dark)" srcset="docs/showcase/how_it_works_en_dark.svg">
<img src="docs/showcase/how_it_works_en_light.svg" width="100%" alt="Sketch: read two sectors in turn, turn the time gap into an angle, then work outward in steps">
</picture>

The measurement only sends read commands. Its result can go straight into a burnable ISO or be exported as a [DiscImageStudio](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio) preset.

## Results

### Geometric accuracy

<img src="docs/showcase/grid_lines_zoom.jpg" width="60%" alt="Part of a grid disc scan with straight lines">

This is part of a test grid disc, from a 600 dpi flatbed scan with a high-pass filter, about 38 mm across. This disc also used timing alone and was burned once (HL-DT-ST GH70N, Ritek F1 DVD-R). Eight scans put the rotation error over 25 to 54 mm at 0.11° peak to peak and 0.03° rms. At a 50 mm radius, 0.03° is about 0.03 mm.

<img src="evidence/figures/bending_before_after.png" width="75%" alt="Rotation against radius for three grid discs">

The green line in this plot is that disc. The measurement plan was [registered before the burn](docs/PREREG_remeasure.md) (in Chinese).

### Fine detail

<img src="docs/showcase/dense_motifs.jpg" width="75%" alt="Macro photo of impossible triangles, small figures and line groups along the top">

A macro photo of the dense tiling disc, also burned once. The impossible triangles are 4.2 mm wide and the small figures are 6.8 mm tall. Along the top are groups of three lines for testing line width. The smallest triangle, 1 mm wide with edges of about 0.15 mm, is clearly visible to the naked eye. A 600 dpi scan separates 0.12 mm lines and barely resolves 0.08 mm, which is the scanner's limit.

### Colour (experimental)

Write the same data over and over and that patch of disc acts as a grating, splitting white light. The repeat length decides which colour goes in a given direction, and the colour changes with the angle. This is still an experiment, followed in [#108](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/108).

<img src="docs/showcase/roses_source.jpg" width="42%" alt="The rose picture made with GPT Image"> <img src="docs/showcase/roses_7185.jpg" width="42%" alt="Photo of the burned rose DVD-R, with some petals showing purple">

On the left is the original, made with GPT Image. On the right is a photo of the burned DVD-R, with the background masked. This disc was designed for purple, and from the right angle some petals come close to the original purple, only darker. It only looks right from one angle, the petals change colour when the phone moves, and you can't choose just any colour: purple is the only target so far. Details are in [#168](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/168). The same disc also holds 1.38 GB of data and read back with no errors, see [#170](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/170). These are early results from one disc, and the tool for the rose disc isn't published yet.

<img src="docs/showcase/rosettes_closeup.jpg" width="75%" alt="Petals of one flower showing several colours under a flash">

The one you can burn yourself is this flower disc, with 3 to 4 colours on one flower. We've only burned it on RITEKF1 DVD-R. Measure your disc as in [Quick start](#quick-start), then build the design. This step doesn't touch the drive:

```bash
python tools/compose_rosettes.py
```

It prints the next command, which builds the ISO:

```bash
python -m discprobe image --geo latest --design-npy iso/rosettes_design.npy --textures "MIX:92,87,83,8D,60" A5 92 66 ED00 2AE304 --r-max 57.6 --output iso/rosettes.iso
```

The preview's colours only tell the textures apart, so it won't match the disc. To photograph it, turn off the room lights, use only the phone flash and hold the phone a little to one side. [#108](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/108) has the steps.

### Other drives and discs

- On RITEKF1 discs, our timing result is within about ±0.05° of bczhc's independent photo calibration ([DiscImageStudio #53](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/53)).
- A laptop drive about 15 years old (PLDS DS8A8SH, through a SATA-to-USB adapter) measured a geometry about 0.05° rms from our GH70N.
- CMC CD-R takes an extra step, because timing can't tell where the data sits along the track in absolute terms. A burned grid disc sets this constant. On the GH70N it is about 206 frames, and a second disc checked it to within +0.6 frames. The pitch on this batch also has a wave, which left 0.16° rms on the second disc.

## Quick start

> If you exported a preset with `--correction` before 2026-11-06, the correction may not be in it. Update and export again; you don't need to measure again.

You need blank discs from the same batch: at least 2 for DVD (measuring, picture) and at least 3 for CD (measuring, calibration, picture). The measuring disc can't take a picture afterwards, but keep it: other discs of that batch don't need a new one. You also need Windows, Python 3.10 or later and a drive that can burn. For Linux and macOS, see the ports listed under the [table of reports](#drives-with-hands-on-reports). The steps below are for DVD. For CD, see the [CD route](#cd-route) further down.

Open a terminal as administrator, install the dependencies, and check your setup on the simulated drive. If you cannot run as administrator, add `--transport imapi` to the drive commands: it sends the same CDBs through Windows' own IMAPI2 recorder interface (`IDiscRecorder2Ex`), which a standard user may call. The default, `auto`, switches to it when SPTI is refused.

```bash
git clone https://github.com/Ashley-QwQ/disc-probe
```

```bash
cd disc-probe
```

```bash
python -m pip install numpy pillow scipy
```

```bash
python -m discprobe selftest
```

If you're not sure what to run next, run `guide`. It reads the `results` folder, shows which steps are done and prints the next command. It doesn't touch the drive:

```bash
python -m discprobe guide
```

At a terminal, `timing` and `geo` end with a one-line verdict, and each command also ends by printing the next one, ready to copy. Scripts and pipes don't get these. See [Using it by hand](#using-it-by-hand) for the rest.

<img src="docs/showcase/cli_demo_en.gif" width="100%" alt="Terminal recording: the opening disc, next-step hints, the measuring progress line and snake">

*Recorded on the simulated drive, so this isn't a real measurement. A script presses the snake keys; the game only opens when you press `g` while measuring.*

### Step 1: burn a random-data disc

The measuring disc must hold plain data, since discs with burned patterns often can't be read. Burn `iso/random.iso` with Windows Disc Image Burner.

```bash
python -m discprobe random --output iso/random.iso
```

### Step 2: check the drive

This takes 1 to 3 minutes. The tray may have opened after the burn, so push it back in and wait a few seconds first. You want to see `CAV` and as little jitter as possible. With only one drive, you can leave out `--drive` at a terminal.

```bash
python -m discprobe timing --drive H:
```

### Step 3: measure the geometry

This takes about 5 minutes. A DVD gets 22 steps, and the progress line at a terminal shows which one it's on.

```bash
python -m discprobe geo --drive H:
```

The pitch on some discs drifts slowly. RITEKF1 is fine with a constant pitch, while `CMC MAG. AM3` and one RITEK DVD+RW needed a quadratic correction (residuals fell from 0.38° and 0.61° to about 0.08°).

When the residual is high, `geo` compares the two models at the end, with no new measurement. If quadratic is clearly better, it asks you to write a correction file and puts `--correction` in the next commands, ready to copy. Otherwise it says this is probably read noise and you can carry on. The command for the correction file looks like this:

```bash
python tools/geo_polyfit.py results/geo-H-... --write-correction correction.json --order quadratic
```

### Step 4: build a picture ISO and burn it to a blank disc from the same batch

`--geo latest` uses your newest real measurement that can be relied on and prints which one it chose; `results --pick` lets you choose by disc and drive, then by precision or date; a result folder or a `summary.json` path works too. Add `--correction correction.json` if you have a correction file. The picture's longer side spans 116 mm (`--diameter-mm` changes it) and it keeps its shape, with the rest left blank. The tool then samples sectors and compares them byte by byte with the design.

```bash
python -m discprobe image --geo latest --picture my_picture.png --output iso/picture.iso
```

To keep working in DiscImageStudio, export a preset. Set `--sectors` to your disc's sector count (`info` on a blank disc prints it, and DiscImageStudio takes the same number; too high a count can make the close fail) and the radius range to what `geo` measured, and add `--correction correction.json` if you have one. The command `geo` prints at the end has these filled in. It prints the conversion error against the measurement, so check that before burning. For now you enter the preset in DiscImageStudio by hand: create a project and fill in the inner and outer radius, sector count and the three pitch terms:

```bash
python -m discprobe disexport --geo latest --sectors YOUR_SECTOR_COUNT --r-min 25.8 --r-max 54.5 --output dis_preset.json
```

### Step 5: look at the disc and photograph it

The data side works like a mirror, so a photo mostly shows what it reflects. Room lights and bright walls can cover the picture, and a burned image may not show at first glance. The rainbow "pizza slices" are diffraction from the factory groove and aren't part of what you burned. The whole image shows up with a small, bright light right next to your eye or camera.

<img src="docs/showcase/lighting_setup.png" width="80%" alt="Two lighting setups seen from above: a light to one side gives rainbow bands, a small light beside a far camera shows the picture">

1. Turn off the room lights and keep one small light. A phone torch works, or a small white square on a black monitor.
2. Put the light beside the phone, both away from the disc. About 1 m is best, or as far as you can.
3. Tilt the disc slightly so it reflects something dark, not the light. Turn it slowly while watching the screen, and the picture appears when the disc goes dark.
4. After focusing, pull the phone's exposure down a little.
5. Keep what's behind the disc and the phone dark, and keep your hands away from the disc.

We've tried this on DVD. A flatbed scanner also works, since a scan isn't affected by reflections in the room.

### CD route

CD has one more constant that timing can't see, so it takes one more disc for calibration. This is the route we recommend: measure, export a preset, then run fine calibration in [DiscImageStudio](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio). Grid discs, texture rings and the other ways are in the [manual](docs/MANUAL.md#cd-r纹理计时与刻图), which is in Chinese for now.

1. Burn the measuring disc on your first blank. At 8x this took about 11 minutes on a GH70N. The tray opens when the burn ends, and `-Reload` only pulls it back in, without opening it first; on a slim drive, push it in yourself.

   ```bash
   python -m discprobe random --media cd --output iso/cd-random.iso
   ```

   ```bash
   powershell -ExecutionPolicy Bypass -File tools/burn_imapi.ps1 -Drive H: -Iso iso/cd-random.iso -Speed 8 -Burn -Reload
   ```

2. Measure. `timing` takes 1 to 3 minutes and `geo` about 5 minutes for 36 steps. If `timing` says the rotation isn't CAV, change speed as it suggests and use the same speed for `geo`. The `geo` command `timing` prints is shorter and uses the default range, which also works; it's written out here to reach a larger radius.

   ```bash
   python -m discprobe timing --media cd --drive H: --speed 1411
   ```

   ```bash
   python -m discprobe geo --media cd --drive H: --speed 1411 --host-delay-ms 35 --ranges 2000-356000
   ```

3. Export the preset. The `disexport` command `geo` prints at the end has the values filled in, so copy it. Its `--sectors` may only be how much the measuring disc holds, so run `info` on a blank disc and change it if `info` differs. Enter the same number in DiscImageStudio. One user [reported](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19442161) that its read-from-disc gave too high a count and closing the disc failed, so don't use that number.
4. Run fine calibration on your second blank. In DiscImageStudio, enter the preset, choose fine calibration on the assisted calibration page, create a target, burn it, rectify a photo, trace points, solve and apply, then save it as a preset. Its [calibration guide](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/blob/main/docs/CALIBRATION.md) has the steps.
5. Burn your picture with those parameters in DiscImageStudio, on your third blank.

<a name="drive-compatibility"></a>

## Drives with hands-on reports

This lists drives someone has tested so far, and a drive that isn't listed may still work. Run `timing` to find out. Most of the data comes from `timing`. You can add yours in [DiscImageStudio discussion #107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107).

### Pictures burned

Most of these are user reports judged from the finished disc, usually with no measured image error.

| Drive | Disc | Result | Source |
|---|---|---|---|
| HL-DT-ST GH70N (NYA2) | Ritek F1 DVD-R | Measuring and burning both verified, about 0.1° on the first burn | this repo |
| HL-DT-ST GH70N (NYA2) | CMC CD-R | Use `--speed 1411`. Along-track constant checked on two grid discs | this repo |
| MATSHITA BD-MLT UJ260AF (macOS) | RITEKF1 DVD-R | `geo` and `disexport` work, and someone has burned a picture with them | NaiveTomcat, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| MATSHITA BD-MLT UJ272 | RITEKF1 DVD-R | Preset went straight into DIS. Cross lines straight and perpendicular by eye, and a finished picture burned | domerawind, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19421274) |
| HL-DT-ST GP90NB70 | `CMC MAG. AM3` DVD-R | Clear picture from the constant-pitch preset, even at the maximum 8x (photo to come) | li-yifei, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19410771) |
| HL-DT-ST GP57EB40 | `CMC MAG. AM3` DVD-R | Burned through DIS with the preset, same outline as the design. The lowest jitter reported so far | MasterMT9, [disc-probe #1](https://github.com/Ashley-QwQ/disc-probe/issues/1) |
| HL-DT-ST GP65NB60 | Ritek DVD+RW (`RITEK/004/48`) | Use `--speed 3324` with a quadratic correction. `--ranges 10000-2290000 --chi2-abort 100` measured 24 to 58 mm, and the corrected result burned a picture, with the outermost radial lines curling slightly (user report, no measured image error) | FanJZSS, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19445201) |
| PIONEER DVR-S21 (PA01) | DVD-R (`MCC 03RG20`, authenticity unknown) | Use `--speed 22160`. The same picture burned once from an `image` ISO and once with DIS (16x CAV, using the disc-probe preset as is), neither with visible error; the DIS one may be slightly scaled. DIS fine calibration had shown no lines before | Lakida0, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19434982) |
| HL-DT-ST SP80NB80 (RC00) | DVD-R, Verbatim AZO (`MCC 03RG20`) | Use `--speed 3324` (about 1432 rpm). `geo` finished, then DIS fine calibration; the picture lined up after 5 discs in all (user report, no measured image error). Not suitable on `CMC MAG. AM3`, see below | Sliicy, [DIS #171](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/171) |
| HL-DT-ST GHB0N (JE01) | Banana DVD-R (`MCC 03RG20`) | Use `--speed 5540`. `geo` finished, and hand-tuned values burned clean rings and radial lines (user report, no measured image error). About 0.05° rms from a disc with the same inner code measured on a Pioneer DVR-S21 | dhao2001, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19438546) |
| Lenovo PLDS DS8A8SH (KL31) | Off-brand DVD+R (羽毛/旭宇达) | Photo analysis had been stuck; a picture burned with the preset worked | anyezhixie, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19426856) |
| PLDS DU8A6SH (macOS) | UGREEN DVD+R (`MCC 004`) | Exported ISO burned by the system at 3x came out right. DIS streaming burn at 2x went wrong, cause not investigated | ShiroiTree, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS SDRW-08D2S-U | Verbatim CD-R | Use `--speed 4234`. Preset with no fine calibration, burned at the lowest speed, same outline as the original | moodyos, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19424471) |
| ASUS SDRW-08D2S-U (B911, Linux) | Verbatim DVD+R | `geo` plus a grid-scan correction, exported as a preset, and pictures burned with it | NO-ob, [disc-probe #6](https://github.com/Ashley-QwQ/disc-probe/issues/6) |
| Sony Optiarc AD-7201S | Memorex CD-R | Clean images only after `geo` plus fine calibration in DIS (about 15 failed discs before) | pugod124, [disc-probe #2](https://github.com/Ashley-QwQ/disc-probe/issues/2) |

### Measures, with burning partly shown or not yet reported

| Drive | Disc | Result | Source |
|---|---|---|---|
| Slimtype DS8A9SH | CD-R (ATIP 97:15:17) | High jitter (2.9 to 3.4°). `geo` finishes, and it calibrated with two discs (user report) | kasumikira, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19415813) |
| PLDS DS8A8SH | RITEK ARITA DVD-R | `geo` works on Windows and Linux. About 0.05° rms from the GH70N on Windows | bczhc, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS DRW-24D5MT | DVD+R (`MCC/004/0`) | `geo` finishes, rms 0.29° at constant pitch | Disappear9, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS SDRW-08U9M-U | RITEK ARITA DVD-R | Only `timing` so far; `geo` not yet run | bczhc, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| HP BD-RE BU20N | Lenovo Thinkplus CD-R | Measured with WindowsNoEditor's own probe using the same method, not this tool | WindowsNoEditor, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| PLDS DU-8A5LH | POSO CD-R | Also with that probe. Fine for whole-disc calibration, not for local detail | WindowsNoEditor, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| TSSTcorp SN-208FB (CH00) | DVD-R (`RITEKF1`) | Measures very well, about 0.05° rms from our GH70N. Ordinary data discs burn fine (up to 8x), but picture discs failed repeatedly (`0xC0AA0301`, from about 0.3 MB to about 284 MiB) on three kinds of disc. Use another drive to burn pictures | Lakida0, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19435910) |

### Not recommended for now

This is the result for the reported disc and speed, and other conditions may differ.

| Drive | Disc | Result | Source |
|---|---|---|---|
| ASUS BW-16D1H-U | RITEK ARITA DVD-R; BD-R | `geo` finishes, but don't burn with its result: about 9.5° peak to peak over 27 to 54 mm | bczhc, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| HL-DT-ST SP80NB80 | DVD-R (`CMC MAG. AM3`) | Too noisy. `geo` stops at its second step, and asking for a lower speed doesn't slow it | Sliicy, [disc-probe #1](https://github.com/Ashley-QwQ/disc-probe/issues/1) |
| HL-DT-ST BD-RE WH14NS40 (1.02) | DVD-R (Verbatim AZO 95101 2201-203) | CAV at about 9280 rpm after reloading the disc, and `timing` looks fine. `geo` ran 18 minutes and only got 6 points, between 42.3 and 42.8 mm, then called it too noisy. `--speed` puts it in CLV until the disc is reloaded. A picture burned with someone else's numbers came out well (one disc, reported by the user) | sanitysama, [#171](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/171#issuecomment-6701560294) |
| MATSHITA UJ8B1 (user calls it ThinkPlus GP90NS60) | Ritek DVD+RW (`RITEK/004/48`) | `--speed 3324 --sectors 16` cuts jitter from about 307 µs (`--speed 5540`) to about 82 µs, but 29 to 33 mm jumped 5 to 10° locally on both runs and `geo` stopped there. Skipping that leaves 34 to 54 mm, rms 1.54° | Doctor-shengru, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19444762) |
| HP HLDS GUD0N | DVD-R (`CMC MAG. AM3`) | `geo` finishes, but rms 3.7° and single steps off by up to about 8°, so the result is not reliable | Sliicy, [disc-probe #1](https://github.com/Ashley-QwQ/disc-probe/issues/1) |

<details>
<summary>Full data: interface, cache, rotation, jitter and details</summary>

| Drive | Interface / OS | Disc | Cache | Rotation | Per-read jitter | Notes | Source |
|---|---|---|---|---|---|---|---|
| HL-DT-ST GH70N (NYA2) | SATA / Windows | Ritek F1 DVD-R | `fua` | CAV, about 2830 rpm at 4x | 0.43 to 0.55° | Ladder and burning both verified (about 0.1° on the first burn). Changes speed at about 53 mm | this repo |
| HL-DT-ST GH70N (NYA2) | SATA / Windows | CMC CD-R | `fua` | CAV. Use `--speed 1411` (about 2080 rpm). `--speed 2822` (3226 rpm) completes about 0.2 ms late past 49.8 mm and can't be used | 0.5 to 0.76° | CD ladder works. On this path (IMAPI burn, READ(12)) the along-track constant is about 206 frames, checked on two grid discs (+0.6 frames left on the second). This batch has a pitch wave of about 0.45° peak to peak | this repo |
| MATSHITA BD-MLT UJ260AF (1.01) | USB 3.0 / macOS ([discprobe-macos](https://github.com/NaiveTomcat/discprobe-macos)) | RITEK RiDATA printable DVD-R (MID `RITEKF1`) | `fua` | CAV, 2364 rpm | 0.65 to 0.87° | `geo` and `disexport` work, parameters in [#87](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/87), and someone has burned a picture with them. 0.13° rms from our GH70N Ritek F1 result over 25 to 58 mm (within ±0.2° past 30 mm). FUA re-reads always take two turns. SET CD SPEED to 4x doesn't change speed. `--sectors 16` recommended | NaiveTomcat, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| MATSHITA DVD+-RW UJ8B1 (D.03, user calls it ThinkPlus GP90NS60) | Windows, interface not reported | Ritek ExcellentX DVD+RW 4X (`RITEK/004/48`), random data | `fua` | CAV: about 4691 rpm with no `--speed`, about 2354 rpm with both `--speed 3324` and `--speed 5540` | 2.79 to 9.81° at 4691 rpm; 1.50 to 6.06° at 2354 rpm (106 to 429 µs), 0.79 to 4.84° with `--sectors 16` (56 to 342 µs) | Not recommended for measuring. Jitter when `geo` starts: 307 µs with `--speed 5540`, 82 µs with `--speed 3324 --sectors 16`, 192 µs with `--speed 5540 --sectors 16`, all at the same rpm, so 3324 is better on this drive. `--speed 5540 --reps 32` finishes, but with rms 2.68° and about 1.7° uncertainty, and 28.9 to 32.7 mm jumps from +5° to −8°. `--speed 3324 --sectors 16` stopped after a 10° miss at LBA 358368 (about 31.8 mm). The same stretch failing twice doesn't look like random noise; the cause wasn't found and there was no reburn to compare. Skipping it with `--ranges 450000-1950000` [finishes](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19444762), covering 34.22 to 54.39 mm with 0.59° uncertainty, rms 1.54° and chi2/dof 4.9, and LBA 1949984 is still 3° off. In 34 to 54 mm that is about 0.2° rms from FanJZSS's GP65NB60 result on the same kind of disc, within the uncertainty. | Doctor-shengru, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19444762) |
| MATSHITA BD-MLT UJ272 (1.02) | USB 2.0 adapter / Windows | RiDATA silver DVD-R (`RITEKF1`, PW104), random data | `fua` | CAV, 2364 rpm (`--speed 5540`) | 0.61 to 0.80° | `geo` finishes, rms 0.28° at constant pitch, about 0.15° rms from the GH70N here. The preset went straight into DIS with no further calibration; cross lines came out straight and perpendicular (by eye, no measured error), and a finished picture was burned too. Photo calibration had never worked before With calibration data from Lakida0 (2295104 sectors) [the disc closed normally](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19440415); 4x was set but it burned at 2x throughout, and the grid and text came out clear (user report). On BD-R (MID `RITEK (000)`, reported as BD-ROM) it reads at constant linear velocity, so [`timing` finds no CAV](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19440933): about 1.6x by default or at 3324, about 2.1x at 8990 and 26974, and `--cav` has no effect. Ritek mini DVD-R (`RITEKG04`): a 700000-sector measuring disc, `geo` covering 24.44 to 36.02 mm, and a 713936-sector preset in DIS [burned a picture](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19442161) at 2x, with the vertical line and F slightly bent and very small text readable (user report). The same drive on Ritek e-series DVD-R (`RITEKF1`): `geo` 22 steps, rms 0.219°, chi2/dof 1.34, [about 0.1° rms from the RiDATA preset](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19442592) (about 0.35° peak to peak) and about 0.07° rms from the GH70N here, all within the uncertainty. A preset refitted with `disexport --sectors 2297888` on RiDATA (`RITEKF1`) [closed normally](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183#issuecomment-6690200194), at an actual 4x with a normal picture (user report, one disc, drive not stated). The 608 sectors fewer than 2298496 are overhead for closing the disc (TBO 592 plus BSGA 16), as [the DIS author explains](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183#issuecomment-6691519009). | domerawind, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19421274) |
| HL-DT-ST GP65NB60 (PF00) | USB / Windows | Ritek ExcellentX DVD+RW (`RITEK/004/48`), random data | `fua` | CAV: 2355 rpm with no `--speed`, 1432 rpm with `--speed 3324`, 3596 rpm with `--speed 11080` | 0.23 to 0.29° at 1432 rpm (26 to 34 µs), 0.53 to 0.65° at 2355 rpm, 1.07 to 1.12° at 3596 rpm | Very low jitter in degrees, so `--speed 3324` is recommended. Phases at 1432 and 2355 rpm agree within 0.17°. At 3596 rpm they differ by up to +0.97° near 52 mm. A disc with a burned calibration pattern couldn't be read, so use random data. `geo` finished 22 steps (`--speed 3324`) with rms 0.61° and chi2/dof 10.8 at constant pitch, and 0.078° and 0.20 at quadratic pitch, so the pitch on this disc drifts slowly and needs a correction. A calibration pattern burned at 2.4x with the corrected preset shows radial lines only slightly off by eye, after a dozen manual attempts before just to see them With a CD-RW (AnyBurn 10x): `disexport --along-track-frames -100` is about 2 frames from DIS fine calibration, and the radial lines look straight (user report). Both show a step of about 0.2 mm near 33 to 34 mm (rough, from photos). Later, `--speed 3324 --ranges 10000-2290000` stopped in the inner area (fit error ratio 27). With `--chi2-abort 100` it finished 22 steps covering 24.20 to 58.09 mm, with rms 0.951° and chi2/dof 26.2 at constant pitch, and 0.092° and 0.27 at quadratic. [A picture burned with the quadratic correction](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19445201), with the outermost radial lines curling slightly (user report). | FanJZSS, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19445201) |
| HL-DT-ST GP90NB70 (1.00, IO-DATA external) | USB / Windows | VHR12JP53SV4 DVD-R (MID `CMC MAG. AM3`), random data | `fua` | CAV, 2355 rpm (`--speed 5540`) | 0.25 to 0.28° (18 to 20 µs) | Very low jitter. `geo` (22 steps) and `disexport` work. Constant pitch gives rms 0.38° and quadratic pitch 0.087°, so the pitch on this disc drifts slowly. The user's [follow-up](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19410771) reports a clear picture from the constant-pitch preset, even at the drive's maximum 8x write speed (photo to come, no quantitative image-error measurement yet). FUA re-reads take three turns | li-yifei, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS BW-16D1H-U (E116) | USB / Windows, Linux | RITEK ARITA DVD-R, random data; BD-R | `fua` | DVD: CAV, 9204 rpm (requests for 2770 and 5540 don't slow it). BD-R: about 9705 rpm at inner and middle zones, about 1655 rpm at the outer zone, unstable on the first run, judged mixed | about 200 µs at every speed (DVD 10 to 14°, BD-R 2 to 15°) | `geo` finishes, but **don't burn with its result**. Against the geometry of the same batch as [#53](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/53), it is off by about 9.5° peak to peak over 27 to 54 mm (+7.7° at 54 mm), which fits a completion-time jump of about 0.2 ms past 50 mm bczhc's [report](https://gist.github.com/bczhc/0323c1762b0d47a46b59159a83353703): `SET CD SPEED` is accepted but the speed doesn't change, and `SET STREAMING` is rejected (5/24/00). DVD-RW stays at about 4840 rpm with 4.8–7.0° jitter. Teardown posts say it's a Pioneer BDR-209 (not readable over SCSI, not measured). Use another drive to measure; it can still burn. On BD-R, asking for 5540 gives [constant linear velocity](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19441086), about 2x. | bczhc, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| PLDS DVD-RW DS8A8SH | SATA-to-USB / Windows, Linux ([bczhc/disc-probe](https://github.com/bczhc/disc-probe)) | RITEK ARITA DVD-R, random data | `fua` | CAV, 2388 rpm | Windows 0.52 to 0.88° (36 to 61 µs), Linux 1.37 to 1.62° (96 to 113 µs) | Laptop drive about 15 years old. `geo` works on Windows (22 points, rms 0.21°), about 0.05° rms from our GH70N and 0.02 to 0.23° from bczhc's photo calibration ([#53](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/53)) at 5 points. `geo` also works on Linux, 0.33° rms from the GH70N (about −0.85° at 27 mm) | bczhc, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| Lenovo PLDS DVD-RW DS8A8SH (KL31) | USB 3.0 / Windows | Off-brand DVD+R (羽毛/旭宇达), random data | `fua` | CAV, 2389 rpm (`--speed 5540`) | 1.18 to 2.53° (56 to 120 µs) at the default speed | `geo` finished all 22 steps, with a constant-pitch rms of 0.178° and chi2/dof 0.82, so no higher-order correction is needed. Max preset conversion error 0.001°. Photo analysis had been stuck, and a picture burned with this preset worked (user report, no measured image error) | anyezhixie, [DiscImageStudio [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107)](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19426856) |
| ASUS SDRW-08U9M-U | USB / Windows | RITEK ARITA DVD-R, random data | `fua` | CAV, 2355 rpm | 0.79 to 1.08° (56 to 76 µs) | Its 5 phases differ from the same disc on the DS8A8SH by −0.23, +0.25, −0.67, −0.05 and −0.04°. `geo` not yet run On DVD-RW, `--speed 2770` gives about 1432 rpm with 0.69° jitter, so it does respond (bczhc's report). | bczhc, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| HP BD-RE BU20N (LG OEM, 0403) | USB / Windows, with WindowsNoEditor's own probe | Lenovo Thinkplus CD-R 80 min | reads far away first, READ CD single sector | CAV, 1241 rpm (`0x0583`), 2482 rpm (`0x0B06`) | about 0.45° at 1241 rpm (about 60 µs), about 1.3 to 3.0° at 2482 rpm | Measured with a different tool using the same method. Found a seam of about +0.2 mm along the track near sector 65,600 | WindowsNoEditor, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| Sony Optiarc AD-7201S (1H9K) | Windows | Memorex CD-R (ATIP 97:15:17), random data | `fua` | CAV, 2168 rpm (`--speed 2822`) | 0.61 to 0.68° (47 to 53 µs) | `geo` finished 36 steps, rms 0.51° with constant pitch and 0.35° with quadratic. A few points are far off, cause unknown. Along-track constant not yet measured. After `geo`, fine calibration in DIS gave clean images, after about 15 failed discs before. On DVD-R (`CMC MAG. AM3`) it runs at about 7514 rpm even when asked for 4x or 2x, with 1.7 to 2.1° jitter and a worse inner zone, and rms 0.51° at constant pitch, 0.41° at quadratic | pugod124, [disc-probe #2](https://github.com/Ashley-QwQ/disc-probe/issues/2) |
| Slimtype DVD A DS8A9SH (EA16) | Windows | CD-R (ATIP 97:15:17) | `fua` | CAV, about 2033 rpm | 2.9 to 3.4° (238 to 275 µs) | `geo` finished 36 steps, chi2/dof 2.75, with some later points 1 to 2° off. Either constant pitch isn't enough or it's the jitter; not separated. Calibrated with two discs (user report, no measured image error) | kasumikira, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19415813) |
| HL-DT-ST SP80NB80 (RC00) | USB / Windows | DVD-R (MID `CMC MAG. AM3` as read on the HP) | `fua` (about 200 ms, 8 turns) | CAV, 2355 rpm | about 236 to 1714 µs (3 to 24°) | Too noisy, and `geo` stops at its second step. `--speed 3324` doesn't slow it down and the noise is worse (723 to 3368 µs), so it isn't suitable | Sliicy, [disc-probe #1](https://github.com/Ashley-QwQ/disc-probe/issues/1) |
| HP HLDS GUD0N (SD03) | internal / Windows | DVD-R (MID `CMC MAG. AM3`) | `flush` | Unstable at the default speed (mixed, CLV); CAV, 2401 rpm with `--speed 3324` | 3.0 to 3.3° (206 to 228 µs) at 2401 rpm | The latest `geo` finished all 22 steps, but with rms 3.7°, chi2/dof 9.4 and single steps off by up to about 8°, so the result is not reliable | Sliicy, [disc-probe #1](https://github.com/Ashley-QwQ/disc-probe/issues/1) |
| HL-DT-ST GP57EB40 | Windows | DVD-R (MID `CMC MAG. AM3`), random data | `fua` | CAV, 2355 rpm | 0.11 to 0.16° (7.5 to 11 µs) | The lowest jitter reported so far. `geo` finished all 22 steps, with a constant-pitch rms of 0.78° and quadratic 0.53°; three steps are noisier than the rest. u and v almost match li-yifei's result on the same disc type from a GP90NB70 (179792.143 against 179792.142, 5.5374125 against 5.5374129). Preset conversion error is at most 0.366°, rms 0.086°. A picture burned through DIS with the preset came out clean, with the same outline as the design ([photo](https://github.com/Ashley-QwQ/disc-probe/issues/1#issuecomment-6672481372), user report, no measured image error) | MasterMT9, [disc-probe #1](https://github.com/Ashley-QwQ/disc-probe/issues/1) |
| PLDS DVD±RW DU-8A5LH | Windows, with WindowsNoEditor's own probe | POSO CD-R 80 min (ATIP 97:27:18) | reads far away first, READ CD | CAV, 2032 rpm (`0x06E4`); not constant at `0x0583` | median per-step σ 0.47° | Ladder residual rms 0.73°. Against the BU20N on the same disc, the geometry matches apart from an along-track constant of about 25 frames. When this drive reads, some sectors complete a fixed 0.5° or so early or late. The same disc doesn't show it on the HP, so it comes from this drive's reading, not the disc: fine for whole-disc calibration, not for local detail. | WindowsNoEditor, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS DRW-24D5MT (1.00) | Windows | DVD+R (MID `MCC/004/0`), random data | `fua` | CAV: 2353 rpm with `--speed 5540`, 4747 rpm by default and with `--speed 11080` | 0.49 to 0.55° at 2353 rpm (35 to 39 µs), 0.78 to 0.98° at 4747 rpm | Phases agree within 0.4° across the two speeds. `geo` finished 22 steps, rms 0.29° at constant pitch and chi2/dof 2.35 | Disappear9, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS SDRW-08D2S-U | USB / Windows | Verbatim CD-R | `fua` (2 turns, 57.4 ms) | CLV at about 4x with `--speed 1411`; CAV, 2090 rpm with `--speed 4234` | 0.19 to 0.28° (15 to 23 µs) at 2090 rpm | `geo` finished all 36 steps (`--media cd --speed 4234`), with a constant-pitch rms of 0.485°. The `disexport` preset was imported into DIS through `disc-presets.json` and used with no fine calibration. A picture burned on the same drive at its lowest speed came out with the same outline as the original ([photo](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19424471), user report, no measured image error). The disc is thin and nearly transparent, so it shows best lit away from the mirror reflection | moodyos, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| ASUS SDRW-08D2S-U (B911) | USB / Linux (bczhc's port) | Verbatim DVD+R (hub code `ZE0460-DVR-T47D`) | not reported | not reported | not reported | `geo` plus a grid-scan correction, exported as a preset with a max conversion error of 0.118°, and pictures burned with it (user report, no measured image error); another Verbatim preset did not work on this disc. Preset and photos in [DiscImageStudio #140](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/140) | NO-ob, [disc-probe #6](https://github.com/Ashley-QwQ/disc-probe/issues/6) |
| PLDS DVD-RW DU8A6SH | macOS ([discprobe-macos](https://github.com/NaiveTomcat/discprobe-macos)) | UGREEN DVD+R (MID `MCC 004`, ring `PR25014-P16`), random data | `fua` | CAV, 1796 rpm (`--speed 4155`; 2x and 3x are the same step, `geo` stops at 4x) | about 0.68 to 0.83° | `geo` finishes 22 steps, rms 1.45°; a noisy band at 51.4 to 52.8 mm, not fully repeatable, and 0.21° without it, with u and v almost unchanged. About 0.15° rms from zhajial's DIS photo calibration of the same disc ([DiscImageStudio #132](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/132)). An exported ISO burned by the system at 3x came out right; DIS streaming burn at 2x went wrong, cause not investigated | ShiroiTree, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107) |
| PIONEER DVD-RW DVR-S21 (PA01) | Windows, interface not reported | DVD-R labelled Verbatim, outer packaging SOKCK, which the user thinks may be counterfeit; authenticity unknown (MID `MCC 03RG20`, ring `111102-S1`), random data | `fua` | CAV, about 4747 rpm (`--speed 22160`, 16x) | 0.54 to 0.70° (19 to 25 µs) | `geo` finished all 22 steps, constant-pitch rms 0.188°, chi2/dof 0.97. The same picture burned once from an `image` ISO and once with DIS (16x CAV, using the disc-probe preset as is), neither with visible error; the DIS one may be slightly scaled (user report, no measured image error). Before this, three rounds each of DIS coarse and edge calibration, and fine calibration showed no lines A RiDATA disc from the same box as the UJ272 row, using domerawind's preset directly at 16x, gave straight, perpendicular reference lines (user report). DIS 1.4.1 and 1.4.2 report a failed close on both this drive and the UJ272, though the picture is complete. The preset had 2298496 sectors, more than a blank can take (a blank RITEKF1 reports 2297888 in `info` on the GH70N). The UJ272 closes normally with 2295104; there is no reburn result from this drive yet. [DIS #183](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183#issuecomment-6691519009) found that the extra 608 sectors are overhead for closing the disc (TBO 592 plus BSGA 16), and on `RITEKF1` a preset refitted to 2297888 [closed normally](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/183#issuecomment-6690200194) (the report in the UJ272 row). `--speed 5540` does slow it to about 2354 rpm. | Lakida0, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19434982) |
| HL-DT-ST SP80NB80 (RC00) | Windows | Verbatim DVD-R AZO 95101 2201-203 (MID `MCC 03RG20`), random data | `fua` | about 1432 rpm (`--speed 3324`) | not reported | `geo` finished, constant pitch rms 0.43°, chi2/dof 4.79, quadratic pitch 0.33°, 2.95. Then DIS fine calibration; the picture lined up after 5 discs in all (user report, no measured image error). On `CMC MAG. AM3` the same drive was too noisy, see the earlier entry | Sliicy, [DIS #171](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/171) |
| HL-DT-ST BD-RE WH14NS40 (1.02) | SATA / Windows | Verbatim DVD-R AZO 95101 2201-203, random data | `fua` | CAV at about 9280 rpm after reloading the disc. `--speed 1411`, `3324` and `5540` all gave CLV, which stayed even with no `--speed` until the disc was reloaded | 0.22–0.49° (3.9–8.9 µs) | `geo` stopped after about 18 minutes with 6 points across 42.3–42.8 mm, rms 0.47°, chi2/dof 6.58. Not usable | sanitysama, [#171](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/issues/171#issuecomment-6701560294) |
| HL-DT-ST GHB0N (JE01) | SATA / Linux (bczhc's port) | Banana blue DVD-R GSD-B-401 (MID `MCC 03RG20`, inner code `111102-S1`), random data | `fua` | CAV, 2361 rpm (`--speed 5540`) | 0.54–0.56° (38–39 µs) | `geo` finished, constant pitch rms 0.176°, chi2/dof 0.90. About 0.05° rms (0.17° peak to peak) from Lakida0's disc with the same MID and inner code, measured on a Pioneer DVR-S21. The user saw slight wiggles and hand-tuned the values, and the radial lines came out straighter by eye; the tuned values are about 0.08° rms from `geo`, within the measurement uncertainty | dhao2001, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19438546) |
| TSSTcorp CDDVDW SN-208FB (CH00) | Windows, interface not reported | Ritek e-series DVD-R (MID `RITEKF1`, PW104), random data written on another drive | `fua` | CAV, about 2351 rpm (`--speed 5540`) | 0.48–0.58° | `geo` finished all 22 steps, rms 0.097°, chi2/dof 0.27; 0.129°, 0.49 when requesting 8x, about 0.03° rms between the two. About 0.05° rms from our GH70N on Ritek F1 (0.17° peak to peak). The same kinds of disc burned fine with ordinary data, up to 8x (user report), but failed with pictures: four RITEKF1 discs with DIS streaming and an ISO stopped near 0.3 MB; RiDATA at 4x near 284 MiB and another DVD at 4x near 270 MB (`0xC0AA0301`). The RiDATA and that other DVD burn fine on the Pioneer | Lakida0, [#107](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio/discussions/107#discussioncomment-19435910) |

</details>

bczhc ported the tool to Linux: [bczhc/disc-probe](https://github.com/bczhc/disc-probe) (see its `README-linux.md`). NaiveTomcat ported it to macOS: [NaiveTomcat/discprobe-macos](https://github.com/NaiveTomcat/discprobe-macos) (GPL-3.0-or-later). The release includes a signed, notarized universal helper, so you don't need to compile anything.

## Using it by hand

<details>
<summary>Next-step hints, drive letters, result paths, common options, Tab completion, language and games</summary>

The hints, progress and animation below only appear when stdout is a terminal. Pipes, redirects and scripts get essentially the same output as before, and result files keep their format. To turn them off in a terminal, set `DISCPROBE_PLAIN=1`.

- What to run next: `guide` shows which steps are done and prints the next command, without touching the drive. Running `python -m discprobe` with no arguments does the same. `info`, `timing`, `geo`, `random`, `image` and `disexport` also end with the next command. `timing` adds a verdict: try another speed if it isn't CAV or above about 2° of jitter, and above about 5° the drive is probably not suitable. These limits come from the reports table and aren't exact. A `geo` that stops gets advice based on why it stopped. One that finishes with more than noise left (chi²/dof above 2) compares a constant and a quadratic pitch after closing the drive: if quadratic at least halves chi²/dof, it asks for a correction file and the next commands use it; otherwise it says this is probably read noise and you can carry on.
- Drive letter: `list` shows the drives. At a terminal you can leave out `--drive`: with one drive it's used, with several you're asked.
- Result paths: `--geo` also takes a result folder, `pick` to choose, or `latest`, which skips simulated runs and runs that stopped early. Results now say when they stopped early; older ones can only be judged by under 8 rungs or chi²/dof above 25, so one that stopped after 8 rungs can't be told apart. `results geo` lists past runs, and `results geo --latest` prints one folder for scripts.
- `--sectors` means three things: In `timing` and `geo` it's sectors per read; `16` reads a whole DVD ECC block. In `random` it's how much to burn. In `disexport` it's the disc's capacity, and DiscImageStudio takes the same number. `info` prints a value and where it came from; go by the one from a blank disc.
- `--speed` takes kB/s or a multiple like `4x`, counted from the 1x of `--media`. DVD: `2.4x` = 3324, `4x` = 5540 (the `geo` default), `8x` = 11080. CD: `8x` = 1411 (the default), `16x` = 2822, `24x` = 4234. Lower is usually quieter, but not every drive changes speed, so check the rpm that `timing` prints.
- `--ranges` takes LBA ranges `a-b,c-d`. The default, 3–85 % of the recorded area, suits most discs. Leave out an area where `geo` keeps stopping or where the speed jumps. Widen it for more radius if the drive reads that far cleanly; on a GP65NB60 that removed the outer error. `info` shows the last LBA.
- CD and DVD: The steps are the same, with `--media cd` on each command. At a terminal, a CD with DVD settings gets a question first, and an empty tray is reported straight away. `disexport` follows the `--geo` result, so its `--media` is only a check.
- When something goes wrong part way: If the tray opens or the disc is taken out or changed during a measurement, `timing` and `geo` stop at once, say why and exit with code 1. What was measured is kept and marked as stopped early, and `--geo latest` won't use it. If an ISO write is interrupted, the unfinished file is removed; where nothing could clean up, such as a closed window, `guide` still won't take it for finished.
- Tab completion: `python -m discprobe completion install` sets it up for PowerShell, bash or zsh: it writes a script to your home folder and adds one line to your shell's startup file, and `completion uninstall` takes both out. The current window doesn't have it until you open a new one or run the line it prints. In PowerShell, Tab on a `discprobe` line opens a list with what each option takes; elsewhere Tab is unchanged. Pressing Tab never starts Python, because the commands and options are written into the script, so install again after an update. Other `python` commands still complete paths, but in bash and zsh it replaces any completion those shells had for `python`.
- Language: At a terminal it follows the system, so a Chinese system gets Chinese help, hints and measuring output. Choose with `--lang zh` or `--lang en` anywhere on the command, or `DISCPROBE_LANG=zh`. Pipes, redirects and `DISCPROBE_PLAIN=1` stay English and ignore `DISCPROBE_LANG`; only `--lang` on the command itself changes them. Result files are never translated.
- Progress: `timing` and `geo` show a bar, the current stage, the time spent and the time left. A narrow window drops parts instead of wrapping. ISO writers use the same line, following the file's real size. Ctrl+C keeps what was measured and says where it is.
- Games: While measuring, press `g` to open a game of snake under the progress line: arrows or WASD steer, `r` plays again, `q` closes it. `n` changes to Fill the Disc: blocks fly in from the right and stack on the left, up and down move them, right spins, left drops, and a full column clears. Measuring output keeps printing above them. They don't exist until you press `g`, and never appears in pipes, with `DISCPROBE_PLAIN=1` or with `--no-animation`.

The progress line and the games have no background thread, because one could delay the completion timestamps. They're drawn on the main thread during the random pause before each timed read, and the drawing time comes off that pause. On the simulated drive, the same seed gives identical summaries and events with or without them. The game works the same way: keys, moves and drawing all happen in that pause, only changed cells are drawn, and it has its own random generator. On the simulated drive, playing also leaves summaries and events identical. The animation still draws at most 8 frames a second, like the earlier progress line, though a colour frame writes more bytes. `timing` was compared with that earlier line on a real drive: the difference with and without it (0.01–0.20°) matched the difference between repeats (0.02–0.23°). The new animation, the game and `geo` haven't been compared yet, so add `--no-animation` or use a pipe if you want to rule them out, and don't play during a measurement that matters.

`timing` and `geo` raise the process to high priority while measuring. Before 2026-11-06 this always failed on 64-bit Python, so earlier real measurements on 64-bit Python ran at normal priority, including the comparison above. Reports made with this tool on Windows probably did too; ports and other probes may differ. The effect of high priority on jitter hasn't been compared yet.

The opening screen of `guide` is a disc of coloured spaces with slashes and a few symbols on top. It falls back from true colour to 16 colours to plain text, and a small window gets the title alone. The turning disc on the progress line is decoration, not the real speed. Everything is 7-bit ASCII by default, so no code page or font can break it; `DISCPROBE_UNICODE=1` asks for finer glyphs. `NO_COLOR` turns off colour only; `--no-animation`, `DISCPROBE_NO_ANIMATION=1` and `CI` turn off animation. Details are in the [manual](docs/MANUAL.md#手动使用) (in Chinese).

</details>

## Another way to use it: timing plus fine calibration

If the timing result isn't perfect, you can use it just to get close, then finish with the image method in DiscImageStudio. pugod124 had failed on about 15 CDs and got clean images this way. See [disc-probe #2](https://github.com/Ashley-QwQ/disc-probe/issues/2#issuecomment-6650565706).

<img src="docs/showcase/pugod124_cd.jpg" width="60%" alt="pugod124's CD-R, burned after geo and then fine calibration in DiscImageStudio">

*A Memorex CD-R burned this way by pugod124, cropped to the disc.*

## Limitations

Discs with the same MID can still differ: two `CMC MAG. AM3` discs differ by about 0.7% in track pitch. Someone else's preset may not fit, so measure your own batch.

Drives vary a lot. A drive that isn't CAV, or has a lot of jitter (200 µs, for example), may give a geometry you can't use, so run `timing` first.

Fast reads near the outer edge can mislead. At 3226 rpm the GH70N finishes CD reads about 0.2 ms late past 49.8 mm, which looks like a change in geometry. The effect is gone at lower speed.

So far we have only burned pictures ourselves on the GH70N. Results for other drives come from timing comparisons and burns by a few users.

On CD, the along-track constant has to come from a grid disc, and 206 frames only applies to the GH70N with an IMAPI burn and READ(12) reads. CMC CD-R also drops about 0.4° near 33 mm, possibly a seam from burning, which we are still checking.

`geo` supports DVD and CD only. Blu-ray discs can only run `timing`.

## Safety

The drive code only sends read commands. A whitelist in [`discprobe/scsi.py`](discprobe/scsi.py) rejects any other opcode before it reaches the device, and the self-test confirms that WRITE, CLOSE TRACK and FORMAT UNIT are refused. The one command that changes drive state is `SET CD SPEED`, sent only if you pass `--speed` or `--cav`. Burning is left to Windows' own burning components, and [`tools/burn_imapi.ps1`](tools/burn_imapi.ps1) only writes when given `-Burn`.

## Documentation

The manual, notes and CD model are in Chinese for now.

| Document | Contents |
|---|---|
| [Manual](docs/MANUAL.md) | How each command works, its options, outputs and self-test results, including the spoke disc, texture ring disc, multi-hypothesis calibration disc and CD |
| [Notes](docs/KNOWLEDGE.md) | Method, hardware measurements, pitfalls and conclusions |
| [CD physical model](docs/CD_PHYSICAL_MODEL.md) | CD implementation and timing assumptions |
| [Showcase](docs/showcase/README.md) | Which disc each photo shows and how it was burned (in English) |
| [`evidence/`](evidence/README.md) | Raw measurements and figures, reproducible |
| [dis-cd-timing](https://github.com/WindowsNoEditor/disc-probe/tree/dis-cd-timing/contrib/dis-cd-timing) | WindowsNoEditor's C# probe, fitting scripts and raw data (in their fork) |

## Prior work and thanks

Measuring sector angles from read timing didn't start here:

- Data Position Measurement (DPM) in disc copy protection, used by SecuROM 4 and later.
- A 2025 discussion on the redump forum about timing a full turn by re-reading one sector with FUA.
- Philips patent US7538787B2 on writing labels on optical discs (priority 2002, lapsed 2017), which describes the same idea for burning visible labels in the data area: timestamps at the end of ECC blocks, repeated reads for the rotation period, and jump distances doubling each round.

This repository adds an open source implementation that can be reproduced on ordinary consumer drives and handles the problems real drives have. It uses covariance-driven stepwise measurement with uncertainty estimates, checks results on burned grid discs, carries corrections across discs, and exports DiscImageStudio presets.

The data-side encoding follows [DiscImageStudio](https://github.com/JiaFeiMiao-K-Cat/DiscImageStudio), and `discprobe/efmplus.py` is ported from it. Thanks to NaiveTomcat and bczhc for the ports, and to anyezhixie, bczhc, Disappear9, domerawind, FanJZSS, kasumikira, Lakida0, li-yifei, MasterMT9, moodyos, NaiveTomcat, NO-ob, pugod124, ShiroiTree, Sliicy, WindowsNoEditor and zhajial for their reports.

## License

Copyright (C) 2026 Ashley-QwQ

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY, without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See [LICENSE](LICENSE). SPDX: `GPL-3.0-or-later`.
