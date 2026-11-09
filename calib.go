package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/egoist/mygo/ui"
	ov "github.com/oneo-me/onevra/source/components"
)

// The calibration page drives bczhc's disc-probe (python -m discprobe)
// the same way the other pages drive the official CLI: timing measures
// the spindle behaviour, geo fits the spiral geometry of a burned disc,
// disexport turns a geo result into a solver preset. All measurement
// math stays inside disc-probe; this file only runs it and parses its
// summary.json outputs.

// ---- result types & parsers (pure, unit-tested against real fixtures)

type TimingZone struct {
	Fraction  float64
	RadiusMM  float64
	RPM       float64
	JitterDeg float64
	Coherence float64
}

type TimingResult struct {
	Dir   string
	Drive string
	Disc  string
	Mode  string // rotation mode from the phase probe: CAV, CLV, ...
	Zones []TimingZone
}

type timingJSON struct {
	Identity struct {
		Drive string `json:"drive"`
		Disc  string `json:"disc"`
	} `json:"identity"`
	Period struct {
		Zones []struct {
			Fraction  float64 `json:"fraction"`
			RadiusMM  float64 `json:"nominal_radius_mm"`
			RPM       float64 `json:"rpm"`
			JitterDeg float64 `json:"jitter_deg"`
			Coherence float64 `json:"coherence"`
		} `json:"zones"`
	} `json:"period"`
	Phase struct {
		Mode string `json:"rotation_mode"`
	} `json:"phase"`
}

func parseTimingSummary(b []byte) (*TimingResult, error) {
	var j timingJSON
	if err := json.Unmarshal(b, &j); err != nil {
		return nil, err
	}
	r := &TimingResult{Drive: j.Identity.Drive, Disc: j.Identity.Disc, Mode: j.Phase.Mode}
	for _, z := range j.Period.Zones {
		r.Zones = append(r.Zones, TimingZone{z.Fraction, z.RadiusMM, z.RPM, z.JitterDeg, z.Coherence})
	}
	if len(r.Zones) == 0 {
		return nil, fmt.Errorf("timing summary 里没有 zones")
	}
	return r, nil
}

type GeoResult struct {
	Dir      string
	R0MM     float64
	PitchUm  float64
	BitNm    float64
	RMSDeg   float64
	Chi2     float64
	SigmaDeg float64
	SpanMM   [2]float64
}

type geoJSON struct {
	Fit struct {
		R0     float64   `json:"r0_mm_at_bit"`
		Pitch  float64   `json:"pitch_um_at_bit"`
		Bit    float64   `json:"bit_nm_assumed"`
		RMS    float64   `json:"residual_rms_deg"`
		Chi2   float64   `json:"chi2_per_dof"`
		Sigma  float64   `json:"angle_sigma_measured_span_deg"`
		SpanMM []float64 `json:"measured_span_mm"`
	} `json:"fit"`
}

func parseGeoSummary(b []byte) (*GeoResult, error) {
	var j geoJSON
	if err := json.Unmarshal(b, &j); err != nil {
		return nil, err
	}
	r := &GeoResult{
		R0MM: j.Fit.R0, PitchUm: j.Fit.Pitch, BitNm: j.Fit.Bit,
		RMSDeg: j.Fit.RMS, Chi2: j.Fit.Chi2, SigmaDeg: j.Fit.Sigma,
	}
	if len(j.Fit.SpanMM) == 2 {
		r.SpanMM = [2]float64{j.Fit.SpanMM[0], j.Fit.SpanMM[1]}
	}
	if r.R0MM == 0 {
		return nil, fmt.Errorf("geo summary 里没有拟合结果（测量可能中途停下了）")
	}
	return r, nil
}

type presetJSON struct {
	Preset struct {
		Name         string  `json:"displayName"`
		TotalSectors int     `json:"totalSectors"`
		InnerMM      float64 `json:"innerRadiusMm"`
		OuterMM      float64 `json:"outerRadiusMm"`
		ChannelBitNm float64 `json:"channelBitLengthNm"`
		PitchLinear  float64 `json:"pitchLinear"`
		PitchQuad    float64 `json:"pitchQuadratic"`
		PitchCubic   float64 `json:"pitchCubic"`
	} `json:"preset"`
}

func parsePresetFile(b []byte) (GeoPreset, error) {
	var j presetJSON
	if err := json.Unmarshal(b, &j); err != nil {
		return GeoPreset{}, err
	}
	p := j.Preset
	if p.TotalSectors == 0 || p.InnerMM == 0 {
		return GeoPreset{}, fmt.Errorf("预设文件不完整")
	}
	return GeoPreset{
		Name: p.Name, TotalSectors: p.TotalSectors,
		InnerMM: p.InnerMM, OuterMM: p.OuterMM,
		PitchLinear: p.PitchLinear, PitchQuad: p.PitchQuad, PitchCubic: p.PitchCubic,
		ChannelBitNm: p.ChannelBitNm,
	}, nil
}

// geoVerdict grades a geo fit by disc-probe's own published thresholds:
// angle uncertainty ≤0.25° is clean, ≤0.6° usable but noisy, above that
// too noisy; χ²/dof above 2 means systematic deviation the cubic export
// fit is expected to absorb.
func geoVerdict(g *GeoResult) string {
	var s string
	switch {
	case g.SigmaDeg <= 0.25:
		s = "测量精度达标，可用"
	case g.SigmaDeg <= 0.6:
		s = "能用，但噪声偏大"
	default:
		s = "噪声太大，建议换速度或换盘重测"
	}
	if g.Chi2 > 2 {
		s += " · χ²/dof 偏高（系统偏差由导出三次拟合吸收）"
	}
	return s
}

// ---- result directory scanning

func resultDirs(probeDir, prefix string) []string {
	ents, err := os.ReadDir(filepath.Join(probeDir, "results"))
	if err != nil {
		return nil
	}
	var out []string
	for _, e := range ents {
		if e.IsDir() && strings.HasPrefix(e.Name(), prefix) {
			out = append(out, filepath.Join(probeDir, "results", e.Name()))
		}
	}
	sort.Slice(out, func(i, j int) bool {
		fi, _ := os.Stat(out[i])
		fj, _ := os.Stat(out[j])
		return fi.ModTime().Before(fj.ModTime())
	})
	return out
}

func newestResultDir(probeDir, prefix string, exclude map[string]bool) string {
	dirs := resultDirs(probeDir, prefix)
	for i := len(dirs) - 1; i >= 0; i-- {
		if exclude == nil || !exclude[dirs[i]] {
			return dirs[i]
		}
	}
	return ""
}

func snapshotDirs(probeDir, prefix string) map[string]bool {
	m := map[string]bool{}
	for _, d := range resultDirs(probeDir, prefix) {
		m[d] = true
	}
	return m
}

func loadTimingFrom(dir string) (*TimingResult, error) {
	b, err := os.ReadFile(filepath.Join(dir, "summary.json"))
	if err != nil {
		return nil, err
	}
	r, err := parseTimingSummary(b)
	if err != nil {
		return nil, err
	}
	r.Dir = dir
	return r, nil
}

func loadGeoFrom(dir string) (*GeoResult, error) {
	b, err := os.ReadFile(filepath.Join(dir, "summary.json"))
	if err != nil {
		return nil, err
	}
	r, err := parseGeoSummary(b)
	if err != nil {
		return nil, err
	}
	r.Dir = dir
	return r, nil
}

// loadLatestCalib parses the newest timing/geo results disc-probe has on
// disk, so the page opens showing the last measurement instead of blanks.
func (a *App) loadLatestCalib() {
	if t := newestResultDir(a.set.ProbeDir, "timing-", nil); t != "" {
		if r, err := loadTimingFrom(t); err == nil {
			a.calibTiming = r
		}
	}
	if g := newestResultDir(a.set.ProbeDir, "geo-", nil); g != "" {
		if r, err := loadGeoFrom(g); err == nil {
			a.calibGeo = r
		}
	}
	a.poke()
}

// ---- jobs

func (a *App) probeCmd(args ...string) (string, []string) {
	full := append([]string{"-m", "discprobe"}, args...)
	return a.set.Python, full
}

func (a *App) runTiming() {
	a.setJob("timing")
	before := snapshotDirs(a.set.ProbeDir, "timing-")
	name, args := a.probeCmd("timing", "--drive", a.set.Device)
	a.logf("$ (cd %s) %s %s", a.set.ProbeDir, name, strings.Join(args, " "))
	err := runStreamingDir(context.Background(), a.set.ProbeDir, name, args,
		func(l string) { a.logf("%s", l) }, nil)
	if err == nil {
		dir := newestResultDir(a.set.ProbeDir, "timing-", before)
		if dir == "" {
			err = fmt.Errorf("timing 跑完了但没找到新结果目录")
		} else if r, perr := loadTimingFrom(dir); perr != nil {
			err = perr
		} else {
			a.calibTiming = r
			a.logf("timing 完成: %s，旋转模式 %s", filepath.Base(dir), r.Mode)
		}
	}
	if err != nil {
		a.logf("timing 失败: %v", err)
	}
	a.endJob(err)
}

func (a *App) runGeo() {
	a.setJob("geo")
	before := snapshotDirs(a.set.ProbeDir, "geo-")
	name, args := a.probeCmd("geo", "--drive", a.set.Device,
		"--speed", a.calibSpeed, "--sectors", "16")
	a.logf("$ (cd %s) %s %s", a.set.ProbeDir, name, strings.Join(args, " "))
	err := runStreamingDir(context.Background(), a.set.ProbeDir, name, args,
		func(l string) { a.logf("%s", l) }, nil)
	if err == nil {
		dir := newestResultDir(a.set.ProbeDir, "geo-", before)
		if dir == "" {
			err = fmt.Errorf("geo 跑完了但没找到新结果目录")
		} else if r, perr := loadGeoFrom(dir); perr != nil {
			err = perr
		} else {
			a.calibGeo = r
			a.logf("geo 完成: r0 %.5f mm，轨距 %.6f µm，%s", r.R0MM, r.PitchUm, geoVerdict(r))
		}
	}
	if err != nil {
		a.logf("geo 失败: %v", err)
	}
	a.endJob(err)
}

func (a *App) runDisexport() {
	if a.calibGeo == nil {
		return
	}
	a.setJob("disexport")
	sectors := int(a.calibSectorsF)
	out := filepath.Join(a.set.WorkDir, "calib-preset.json")
	_ = ensureWorkDir(a.set.WorkDir)
	name, args := a.probeCmd("disexport", "--geo", a.calibGeo.Dir,
		"--sectors", itoa(sectors), "--output", out)
	a.logf("$ (cd %s) %s %s", a.set.ProbeDir, name, strings.Join(args, " "))
	err := runStreamingDir(context.Background(), a.set.ProbeDir, name, args,
		func(l string) { a.logf("%s", l) }, nil)
	if err == nil {
		b, rerr := os.ReadFile(out)
		if rerr != nil {
			err = rerr
		} else if g, perr := parsePresetFile(b); perr != nil {
			err = perr
		} else {
			if strings.TrimSpace(a.calibPresetName) != "" {
				g.Name = a.calibPresetName
			}
			a.set.CustomPresets = append(a.set.CustomPresets, g)
			a.set.save()
			a.logf("预设已存入: %s（总扇区 %d，内径 %.4f，外径 %.4f）",
				g.Name, g.TotalSectors, g.InnerMM, g.OuterMM)
		}
	}
	if err != nil {
		a.logf("导出预设失败: %v", err)
	}
	a.endJob(err)
}

// ---- page

func (a *App) pageCalib(c *ui.Context) {
	job, _, _, _ := a.jobState()
	busy := job != ""
	a.smoothScroll(c, 2).FillHeight().Children(func() {
		centerWrap(c, 860, 12, func() {
			sectionCard(c, "校准后端 · disc-probe", func() {
				ov.Text(c, fmt.Sprintf("目录 %s · 设备 %s", a.set.ProbeDir, a.set.Device)).
					FontSize(13).TextColor(colText)
				ov.Text(c, "timing/geo 读的是盘上已刻数据的相位：驱动器里要有一张已刻过的盘。geo 约需几分钟。").
					FontSize(12).TextColor(colMuted)
				if ov.Button(c, "载入最近一次结果", ov.ButtonSecondary).Clicked() {
					go a.loadLatestCalib()
				}
			})
			sectionCard(c, "转速测量 · timing", func() {
				ui.Row(c).Gap(8).Children(func() {
					b := ov.Button(c, "运行转速测量", ov.ButtonPrimary)
					if busy {
						b.Disabled(true)
					}
					if b.Clicked() {
						go a.runTiming()
					}
					ov.Text(c, "测三个半径区的转速与抖动，判 CAV/CLV").FontSize(12).TextColor(colMuted)
				})
				a.progressRow(c, "timing")
				if t := a.calibTiming; t != nil {
					ov.Text(c, fmt.Sprintf("驱动器 %s · 盘 %s · 旋转模式 %s", t.Drive, t.Disc, t.Mode)).
						FontSize(13).TextColor(colText)
					for _, z := range t.Zones {
						ov.Text(c, fmt.Sprintf("r %.1f mm · %.1f rpm · 抖动 %.2f° · coherence %.3f",
							z.RadiusMM, z.RPM, z.JitterDeg, z.Coherence)).
							FontSize(12).TextColor(colMuted)
					}
				} else {
					ov.Text(c, "还没有转速结果。").FontSize(12).TextColor(colMuted)
				}
			})
			sectionCard(c, "几何拟合 · geo", func() {
				ui.Row(c).Gap(8).Children(func() {
					ov.Text(c, "速度").Width(40).FontSize(13).TextColor(colMuted)
					ovSelect(c, &a.calibSpeed, "geo 速度", []string{"2.4x", "4x", "8x"}, 110)
					b := ov.Button(c, "运行几何拟合", ov.ButtonPrimary)
					if busy {
						b.Disabled(true)
					}
					if b.Clicked() {
						go a.runGeo()
					}
					ov.Text(c, "阶梯读相位拟合螺旋几何（16 扇区/读）").FontSize(12).TextColor(colMuted)
				})
				a.progressRow(c, "geo")
				if g := a.calibGeo; g != nil {
					ov.Text(c, fmt.Sprintf("r0 %.5f mm · 轨距 %.6f µm · bit %.1f nm · 测量跨度 %.1f–%.1f mm",
						g.R0MM, g.PitchUm, g.BitNm, g.SpanMM[0], g.SpanMM[1])).
						FontSize(13).TextColor(colText)
					ov.Text(c, fmt.Sprintf("残差 RMS %.3f° · χ²/dof %.2f · 角不确定度 %.3f°",
						g.RMSDeg, g.Chi2, g.SigmaDeg)).FontSize(12).TextColor(colMuted)
					ov.Text(c, geoVerdict(g)).FontSize(12).TextColor(colOK)
				} else {
					ov.Text(c, "还没有几何结果。").FontSize(12).TextColor(colMuted)
				}
			})
			sectionCard(c, "导出为求解预设 · disexport", func() {
				fieldNum(c, "总扇区", &a.calibSectorsF, 16, 4600000, 16)
				ov.Text(c, "总扇区填这张盘的容量（空白盘 info 的数），与导出页求解时一致。").
					FontSize(11).TextColor(colMuted)
				fieldText(c, "预设名", &a.calibPresetName)
				ui.Row(c).Gap(8).Children(func() {
					b := ov.Button(c, "导出并存为预设", ov.ButtonPrimary)
					if busy || a.calibGeo == nil {
						b.Disabled(true)
					}
					if b.Clicked() {
						go a.runDisexport()
					}
					if a.calibGeo == nil {
						ov.Text(c, "先跑一次几何拟合（或载入最近结果）").FontSize(12).TextColor(colMuted)
					} else {
						ov.Text(c, "存入后在导出页的预设列表里选用").FontSize(12).TextColor(colMuted)
					}
				})
				a.progressRow(c, "disexport")
			})
			a.logCard(c, 12)
		})
	})
}
