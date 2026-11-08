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
	Name         string
	TotalSectors int
	InnerMM      float64
	OuterMM      float64
	PitchLinear  float64
	PitchQuad    float64
	PitchCubic   float64
	ChannelBitNm float64
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
	page int // 0 home, 1 design, 2 preview, 3 export, 4 burn, 5 settings
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
	return a
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
