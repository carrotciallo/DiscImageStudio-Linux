package main

import (
	"encoding/json"
	"fmt"
	"image"
	"os"
	"path/filepath"
	"strconv"
	"sync"
	"time"

	"github.com/egoist/mygo/ui"
)

// Disc geometry in millimetres. The printable annulus of a DVD is
// r 24.173..57.912 on a 116 mm canvas.
const (
	DiscMM   = 116.0
	HubR     = 24.173
	RimR     = 57.912
	CanvasPx = 4096
)

// GeoPreset is one geometry profile for the solver: total sectors plus the
// pitch polynomial coefficients of the image mapping.
type GeoPreset struct {
	Name         string  `json:"name"`
	TotalSectors int     `json:"totalSectors"`
	InnerMM      float64 `json:"innerMM"`
	OuterMM      float64 `json:"outerMM"`
	PitchLinear  float64 `json:"pitchLinear"`
	PitchQuad    float64 `json:"pitchQuad"`
	PitchCubic   float64 `json:"pitchCubic"`
	ChannelBitNm float64 `json:"channelBitNm"`
}

var geoPresets = []GeoPreset{
	{
		Name: "GX40N · AM3 实测（定版）", TotalSectors: 2298336,
		InnerMM: 24.173269389549194, OuterMM: 57.912477520380705,
		PitchLinear: -9.075977475240458e-05, PitchQuad: 1.73650837387536e-04,
		PitchCubic: -9.966988425471086e-05, ChannelBitNm: 133.3,
	},
	{
		Name: "官方导出预设", TotalSectors: 2298336,
		InnerMM: 24.17331445, OuterMM: 57.91247752,
		PitchLinear: 0, PitchQuad: 0, PitchCubic: 0, ChannelBitNm: 133.3,
	},
}

// Layer is one picture placed on the disc canvas. X/Y are the offset of the
// picture centre from the disc centre in mm (Y down), HeightMM its height on
// the disc, Rotation clockwise degrees.
type Layer struct {
	Path     string
	Name     string
	X, Y     float64
	HeightMM float64
	Rotation float64

	img  image.Image // decoded source, kept for compositing
	imgW int
	imgH int
}

// Project is everything the design/export/burn pages share.
type Project struct {
	Layers  []*Layer
	Sel     int
	Preproc bool // 定版预处理: luminance autocontrast + unsharp

	Dither     float64
	Brightness float64
	SRGBLinear bool

	FastOutput     bool
	ReadCompat     bool
	ConstraintStep float64
	FillSectors    int // 0 = same as total sectors

	ISOPath string
	SimPath string
}

type Settings struct {
	CLIPath   string `json:"cliPath"`
	WorkDir   string `json:"workDir"`
	BurnSpeed int    `json:"burnSpeed"`
	Device    string `json:"device"`

	ProbeDir      string      `json:"probeDir"`
	Python        string      `json:"python"`
	CustomPresets []GeoPreset `json:"customPresets"`
}

func settingsPath() string {
	dir, err := os.UserConfigDir()
	if err != nil {
		dir = os.Getenv("HOME")
	}
	return filepath.Join(dir, "dis-gui", "settings.json")
}

func loadSettings() Settings {
	s := Settings{
		CLIPath:   filepath.Join(os.Getenv("HOME"), "muse/discimagestudio/official/disc-image-studio"),
		WorkDir:   filepath.Join(os.Getenv("HOME"), "muse/discimagestudio/work"),
		BurnSpeed: 8,
		Device:    "/dev/sr0",
		ProbeDir:  filepath.Join(os.Getenv("HOME"), "muse/discimagestudio/probe"),
		Python:    "python3",
	}
	if b, err := os.ReadFile(settingsPath()); err == nil {
		_ = json.Unmarshal(b, &s)
	}
	return s
}

func (s Settings) save() {
	_ = os.MkdirAll(filepath.Dir(settingsPath()), 0o755)
	if b, err := json.MarshalIndent(s, "", "  "); err == nil {
		_ = os.WriteFile(settingsPath(), b, 0o644)
	}
}

// MediaInfo is the parsed state of the disc in the drive.
type MediaInfo struct {
	Loaded bool
	Blank  bool
	Status string
	Media  string
}

// App is the whole application state. The view reads it every frame; jobs
// mutate it under mu.
type App struct {
	page int // 0 home, 1 design, 2 calib, 3 preview, 4 export, 5 burn, 6 settings
	set  Settings
	proj Project
	geo  GeoPreset

	mu       sync.Mutex
	logs     []string
	job      string // "", "solve", "simulate", "burn", "selftest"
	jobDone  int
	jobTotal int
	jobErr   string
	lastEnd  time.Time
	media    MediaInfo

	flatMu    sync.Mutex
	flatDirty bool
	flatBmp   *ui.Bitmap // 1024px design preview
	simBmp    *ui.Bitmap
	simNote   string

	ctxMu sync.Mutex
	ctx   *ui.Context // latest view context, for Invalidate from job goroutines

	geoTotalF  float64 // float mirrors for NumberInput binding
	fillF      float64
	burnSpeedF float64
	speedSel   string
	geoName    string

	calibTiming     *TimingResult
	calibGeo        *GeoResult
	calibSpeed      string
	calibSectorsF   float64
	calibPresetName string

	scrolls      [7]ui.ScrollState // per-page tracked scroll offsets
	lastScrollY  [7]float32
	lastScrollAt time.Time
	wheelTarget  [7]float32 // app-side wheel glide destinations, per page
	wheelAccum   [7]float32 // banked hi-res (Precise) sub-steps, per page

	// Design canvas gestures: last drawn canvas size (DIP) and the
	// in-flight drag's mode and baselines (mm).
	canvasW, canvasH float32
	dragMode         int
	dragStart        [2]float64
	dragBaseX        float64
	dragBaseY        float64
	dragBaseH        float64
	dragBaseDist     float64
}

func newApp() *App {
	a := &App{set: loadSettings(), geo: geoPresets[0], flatDirty: true}
	a.proj = Project{
		Sel: -1, Preproc: true,
		Dither: 0.75, Brightness: -16,
		FastOutput: true, ReadCompat: true, ConstraintStep: 64,
		ISOPath: filepath.Join(a.set.WorkDir, "disc.iso"),
		SimPath: filepath.Join(a.set.WorkDir, "simulate.png"),
	}
	a.geoTotalF = float64(a.geo.TotalSectors)
	a.geoName = a.geo.Name
	a.burnSpeedF = float64(a.set.BurnSpeed)
	a.speedSel = strconv.Itoa(a.set.BurnSpeed)
	a.calibSpeed = "4x"
	a.calibSectorsF = float64(a.geo.TotalSectors)
	a.loadLatestCalib()
	return a
}

// allPresets is the export page's preset list: the two built-ins followed
// by any calibration presets the user has saved.
func (a *App) allPresets() []GeoPreset {
	out := append([]GeoPreset(nil), geoPresets...)
	return append(out, a.set.CustomPresets...)
}

func (a *App) logf(format string, args ...any) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.logs = append(a.logs, fmt.Sprintf(format, args...))
	if len(a.logs) > 400 {
		a.logs = a.logs[len(a.logs)-400:]
	}
}

func (a *App) logTail(n int) []string {
	a.mu.Lock()
	defer a.mu.Unlock()
	if len(a.logs) <= n {
		return append([]string(nil), a.logs...)
	}
	return append([]string(nil), a.logs[len(a.logs)-n:]...)
}

func (a *App) jobState() (job string, done, total int, err string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.job, a.jobDone, a.jobTotal, a.jobErr
}

func (a *App) setJob(job string) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.job, a.jobDone, a.jobTotal, a.jobErr = job, 0, 0, ""
}

func (a *App) setProgress(done, total int) {
	a.mu.Lock()
	a.jobDone, a.jobTotal = done, total
	a.mu.Unlock()
	a.poke()
}

func (a *App) endJob(err error) {
	a.mu.Lock()
	a.job = ""
	a.lastEnd = time.Now()
	if err != nil {
		a.jobErr = err.Error()
	}
	a.mu.Unlock()
	a.poke()
}

// scrollMoved reports whether the current page's scroll offset is in
// motion: it changed in the latest frame, or within the last 350 ms.
// view() keeps requesting frames while it is true, so a wheel glide is
// presented at full cadence from its first step to its last, even on a
// backend that otherwise only renders on input.
func (a *App) scrollMoved() bool {
	y := a.scrolls[a.page].Y
	// A spring's asymptotic tail moves sub-pixel amounts for a long
	// while; that does not need frames. 0.05 DIP/frame is well below
	// anything visible mid-glide.
	moved := y-a.lastScrollY[a.page] > 0.05 || a.lastScrollY[a.page]-y > 0.05
	a.lastScrollY[a.page] = y
	if moved {
		a.lastScrollAt = time.Now()
		return true
	}
	return time.Since(a.lastScrollAt) < 350*time.Millisecond
}

// Wheel scrolling tuning: the engine's own notch is short on travel,
// and its 150 ms glide is presented in only a few frames on this stack,
// so a notch reads as a jump. The app takes wheel input over
// (smoothScroll) and drives the offset itself: farther per notch, on a
// spring, with frames kept flowing by scrollMoved until it settles.
// Hi-res wheels (the G502 X LS here sends 8 sub-steps of 15/120 per
// notch) arrive as Precise events; their sub-steps are too fine to
// present individually on this stack, so they are banked and released
// into the same spring target once preciseStep has accumulated.
const (
	wheelBoost     = 2.2
	wheelSpringDur = 380 * time.Millisecond
	preciseStep    = 25.0 // banked Precise travel (DIP) released per glide step
)

// smoothScroll returns the tracked vertical scroll container for a
// page, with wheel input taken over by the app: discrete notches go
// straight to the spring target, Precise sub-steps (hi-res wheels) are
// banked via wheelAccum until they make half a notch. This machine has
// no touchpad, so Precise input here only ever comes from hi-res
// wheels. Shift (sideways) and Ctrl (zoom) wheels stay with the engine.
func (a *App) smoothScroll(c *ui.Context, page int) ui.Element {
	st := &a.scrolls[page]
	el := ui.Scroll(c).TrackScroll(st)
	el.HandleInput(func(ev ui.InputEvent) bool {
		if ev.Kind != ui.InputScroll || ev.DY == 0 ||
			ev.Mods&(ui.Shift|ui.Ctrl) != 0 {
			return false
		}
		amt := ev.DY
		if ev.Precise {
			a.wheelAccum[page] += ev.DY
			if a.wheelAccum[page] > -preciseStep && a.wheelAccum[page] < preciseStep {
				return true // swallowed and banked; not a full step yet
			}
			amt = a.wheelAccum[page]
			a.wheelAccum[page] = 0
		}
		target := st.Y
		if st.Scrolling() {
			target = a.wheelTarget[page]
		}
		target = max(0, min(target+amt*wheelBoost, st.MaxY))
		a.wheelTarget[page] = target
		st.ScrollTo(st.X, target, ui.Animation{Spring: ui.SpringOptions{Duration: wheelSpringDur}})
		return true
	})
	return el
}

// settling reports whether the UI should keep animating frames: while a
// job runs, and briefly after it ends so its final state (preview bitmap,
// logs) is guaranteed a frame to land on.
func (a *App) settling() bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.job != "" || time.Since(a.lastEnd) < 2*time.Second
}

// setContext remembers the current view context so background jobs can ask
// for a frame when their state changes. Context.Invalidate is documented
// as safe from any goroutine.
func (a *App) setContext(c *ui.Context) {
	a.ctxMu.Lock()
	defer a.ctxMu.Unlock()
	a.ctx = c
}

// poke asks the UI for another frame; called by job goroutines whenever
// they change visible state.
func (a *App) poke() {
	a.ctxMu.Lock()
	c := a.ctx
	a.ctxMu.Unlock()
	if c != nil {
		c.Invalidate()
	}
}
