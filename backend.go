package main

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
)

// SolveParams is the full input of one solve run: geometry preset, tone and
// mode switches. It mirrors the official CLI's solve options one to one.
type SolveParams struct {
	Geo            GeoPreset
	Dither         float64
	Brightness     float64
	SRGBLinear     bool
	FastOutput     bool
	ReadCompat     bool
	ConstraintStep float64
	FillSectors    int // 0 = total sectors
	StartLBA       int
}

func fnum(v float64) string {
	return strconv.FormatFloat(v, 'g', -1, 64)
}

func boolStr(b bool) string {
	if b {
		return "true"
	}
	return "false"
}

// solveArgs builds the official CLI argument vector for solve. Pure, so the
// parity tests can pin it down.
func solveArgs(canvasPNG, isoOut string, p SolveParams) []string {
	g := p.Geo
	fill := p.FillSectors
	if fill <= 0 {
		fill = g.TotalSectors
	}
	return []string{
		"solve",
		"--image", canvasPNG,
		"--iso-output", isoOut,
		"--total-sectors", strconv.Itoa(g.TotalSectors),
		"--fill-sectors", strconv.Itoa(fill),
		"--inner-radius-mm", fnum(g.InnerMM),
		"--outer-radius-mm", fnum(g.OuterMM),
		"--pitch-linear", fnum(g.PitchLinear),
		"--pitch-quadratic", fnum(g.PitchQuad),
		"--pitch-cubic", fnum(g.PitchCubic),
		"--channel-bit-length-nm", fnum(g.ChannelBitNm),
		"--tone-dither", fnum(p.Dither),
		"--tone-brightness", fnum(p.Brightness),
		"--tone-srgb-linearization", boolStr(p.SRGBLinear),
		"--fast-output", boolStr(p.FastOutput),
		"--read-compatibility", boolStr(p.ReadCompat),
		"--constraint-step", fnum(p.ConstraintStep),
		"--start-lba", strconv.Itoa(p.StartLBA),
	}
}

// simulateArgs builds the argument vector for simulate (read-back preview).
func simulateArgs(iso, outPNG string, g GeoPreset) []string {
	return []string{
		"simulate",
		"--iso", iso,
		"--output", outPNG,
		"--total-sectors", strconv.Itoa(g.TotalSectors),
		"--inner-radius-mm", fnum(g.InnerMM),
		"--outer-radius-mm", fnum(g.OuterMM),
		"--pitch-linear", fnum(g.PitchLinear),
		"--pitch-quadratic", fnum(g.PitchQuad),
		"--pitch-cubic", fnum(g.PitchCubic),
		"--channel-bit-length-nm", fnum(g.ChannelBitNm),
	}
}

var (
	blockRe  = regexp.MustCompile(`block (\d+)/(\d+)`)
	burnMBRe = regexp.MustCompile(`(\d+) of (\d+) MB written`)
	burnPct  = regexp.MustCompile(`(\d+(?:\.\d+)?)% done`)
)

// runStreaming runs a command, feeding each output line to onLine and block
// progress (solve) or write progress (xorriso) to onProgress.
func runStreaming(ctx context.Context, name string, args []string, onLine func(string), onProgress func(done, total int)) error {
	cmd := exec.CommandContext(ctx, name, args...)
	r, w := io.Pipe()
	cmd.Stdout = w
	cmd.Stderr = w
	done := make(chan struct{})
	go func() {
		defer close(done)
		sc := bufio.NewScanner(r)
		sc.Buffer(make([]byte, 64*1024), 1024*1024)
		for sc.Scan() {
			line := sc.Text()
			if onLine != nil {
				onLine(line)
			}
			if onProgress != nil {
				if m := blockRe.FindStringSubmatch(line); m != nil {
					d, _ := strconv.Atoi(m[1])
					t, _ := strconv.Atoi(m[2])
					onProgress(d, t)
				} else if m := burnMBRe.FindStringSubmatch(line); m != nil {
					d, _ := strconv.Atoi(m[1])
					t, _ := strconv.Atoi(m[2])
					onProgress(d, t)
				}
			}
		}
	}()
	err := cmd.Start()
	if err != nil {
		return err
	}
	err = cmd.Wait()
	_ = w.Close()
	<-done
	return err
}

func (a *App) runSolve(canvasPNG string) {
	a.setJob("solve")
	p := SolveParams{
		Geo: a.geo, Dither: a.proj.Dither, Brightness: a.proj.Brightness,
		SRGBLinear: a.proj.SRGBLinear, FastOutput: a.proj.FastOutput,
		ReadCompat: a.proj.ReadCompat, ConstraintStep: a.proj.ConstraintStep,
		FillSectors: a.proj.FillSectors,
	}
	args := solveArgs(canvasPNG, a.proj.ISOPath, p)
	a.logf("$ %s %s", a.set.CLIPath, strings.Join(args, " "))
	err := runStreaming(context.Background(), a.set.CLIPath, args,
		func(l string) { a.logf("%s", l) },
		func(d, t int) { a.setProgress(d, t) })
	if err != nil {
		a.logf("solve 失败: %v", err)
	} else {
		a.logf("solve 完成: %s", a.proj.ISOPath)
	}
	a.endJob(err)
}

func (a *App) runSimulate() {
	a.setJob("simulate")
	args := simulateArgs(a.proj.ISOPath, a.proj.SimPath, a.geo)
	a.logf("$ %s %s", a.set.CLIPath, strings.Join(args, " "))
	err := runStreaming(context.Background(), a.set.CLIPath, args,
		func(l string) { a.logf("%s", l) }, nil)
	if err != nil {
		a.logf("simulate 失败: %v", err)
	} else {
		a.loadSimBitmap()
		a.logf("simulate 完成: %s", a.proj.SimPath)
	}
	a.endJob(err)
}

func (a *App) runSelftest() {
	a.setJob("selftest")
	out, err := exec.Command(a.set.CLIPath, "selftest").CombinedOutput()
	for _, l := range strings.Split(strings.TrimSpace(string(out)), "\n") {
		a.logf("%s", l)
	}
	if err != nil {
		a.logf("selftest 失败: %v", err)
	}
	a.endJob(err)
}

// probeMedia reads the drive state with dvd+rw-mediainfo.
func probeMedia(device string) MediaInfo {
	out, err := exec.Command("dvd+rw-mediainfo", device).CombinedOutput()
	if err != nil {
		return MediaInfo{Status: "无盘或驱动器不可用"}
	}
	mi := MediaInfo{Loaded: true, Status: "未知"}
	for _, l := range strings.Split(string(out), "\n") {
		k, v, ok := strings.Cut(l, ":")
		if !ok {
			continue
		}
		switch strings.TrimSpace(k) {
		case "Disc status":
			mi.Status = strings.TrimSpace(v)
			mi.Blank = strings.Contains(v, "blank")
		case "Media ID":
			mi.Media = strings.TrimSpace(v)
		}
	}
	return mi
}

func (a *App) refreshMedia() {
	a.mu.Lock()
	a.media = probeMedia(a.set.Device)
	a.mu.Unlock()
	a.poke()
}

func (a *App) mediaInfo() MediaInfo {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.media
}

func (a *App) runBurn() {
	a.setJob("burn")
	args := []string{"-as", "cdrecord", "dev=" + a.set.Device, "-v",
		fmt.Sprintf("speed=%d", a.set.BurnSpeed), "-dao", a.proj.ISOPath}
	a.logf("$ xorriso %s", strings.Join(args, " "))
	err := runStreaming(context.Background(), "xorriso", args,
		func(l string) { a.logf("%s", l) },
		func(d, t int) { a.setProgress(d, t) })
	if err != nil {
		a.logf("刻录失败: %v", err)
	} else {
		a.logf("刻录完成，正在弹盘")
		_ = exec.Command("eject", a.set.Device).Run()
	}
	a.endJob(err)
	a.refreshMedia()
}

// ensureWorkDir makes sure the work directory and an output parent exist.
func ensureWorkDir(dir string) error {
	return os.MkdirAll(dir, 0o755)
}
