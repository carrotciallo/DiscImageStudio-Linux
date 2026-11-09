package main

import (
	"log"
	"os"
	"strconv"

	"github.com/egoist/mygo"
	"github.com/egoist/mygo/ui"
	ov "github.com/oneo-me/onevra/source/components"
	ovtheme "github.com/oneo-me/onevra/source/theme"
)

// Palette: Onevra's light theme tokens (the studio UI is light by
// decision). The disc preview is the hero; chrome stays quiet around it.
var ovTh = ovtheme.LightPalette()

var (
	colBg       = ovTh.Background
	colPanel    = ovTh.Surface
	colPanel2   = ovTh.SurfaceHover
	colBorder   = ovTh.Border
	colText     = ovTh.Text
	colMuted    = ovTh.TextMuted
	colAccent   = ovTh.Accent
	colAccentBg = ovTh.SurfacePressed
	colDanger   = ovTh.Danger
	colOK       = ovTh.Success
)

var pageNames = []string{"首页", "设计", "校准", "导出", "刻录", "设置"}

func main() {
	a := newApp()
	// Verification hook: DISGUI_OPEN=<image> starts with that picture as a
	// layer, so automated runs can exercise the design page end to end.
	if p := os.Getenv("DISGUI_OPEN"); p != "" {
		if l, err := LoadLayer(p); err == nil {
			a.proj.Layers = append(a.proj.Layers, l)
			a.proj.Sel = 0
			a.page = 1
		}
	}
	mygo.App.WhenReady(func() {
		mygo.NewWindow(mygo.WindowOptions{
			Title:   "Disc Image Studio · Linux",
			Width:   1320,
			Height:  860,
			Content: ui.View(a.view),
		})
	})
	if err := mygo.App.Run(); err != nil {
		log.Fatal(err)
	}
}

// syncMirrors writes the float/string mirror fields back into the typed
// state before an action uses them.
func (a *App) syncMirrors() {
	a.geo.TotalSectors = int(a.geoTotalF)
	a.proj.FillSectors = int(a.fillF)
	if v, err := strconv.Atoi(a.speedSel); err == nil {
		a.set.BurnSpeed = v
	}
}

func (a *App) view(c *ui.Context) {
	a.setContext(c)
	c.SetTheme(ui.LightTheme()) // light first so Onevra picks its light palette
	ovtheme.Apply(c)
	_, _, _, jobErr := a.jobState()
	if a.settling() || a.scrollMoved() || a.designRefining() {
		c.AnimationFrame() // keep progress, logs, job results and scroll glides flowing
	}
	ui.Row(c).Fill().Background(colBg).Children(func() {
		a.nav(c)
		ui.Column(c).Grow(1).FillHeight().Padding(20).Gap(16).Children(func() {
			if jobErr != "" {
				ov.Text(c, "上次任务出错: "+jobErr).TextColor(colDanger).FontSize(13)
			}
			switch a.page {
			case 0:
				a.pageHome(c)
			case 1:
				a.pageDesign(c)
			case 2:
				a.pageCalib(c)
			case 3:
				a.pageExport(c)
			case 4:
				a.pageBurn(c)
			case 5:
				a.pageSettings(c)
			}
		})
	})
}

func (a *App) nav(c *ui.Context) {
	job, done, total, _ := a.jobState()
	ui.Column(c).Width(208).FillHeight().Background(colPanel).
		Padding(16, 14).Gap(6).Children(func() {
		ov.Text(c, "Disc Image Studio").FontSize(17).Bold().TextColor(colText)
		ov.Text(c, "Linux 图形前端 · MyGo").FontSize(11).TextColor(colMuted)
		ui.Box(c).Height(10)
		for i, name := range pageNames {
			variant := ov.ButtonGhost
			if a.page == i {
				variant = ov.ButtonSecondary
			}
			if ov.Button(c, name, variant).Width(180).Clicked() {
				a.page = i
				a.set.save()
			}
		}
		ui.Box(c).Grow(1)
		if job != "" {
			ui.Row(c).Gap(8).Children(func() {
				ov.Spinner(c, ov.SpinnerRing)
				label := jobLabel(job)
				if total > 0 {
					label += " " + itoa(done) + "/" + itoa(total)
				}
				ov.Text(c, label).FontSize(12).TextColor(colMuted)
			})
		} else {
			ov.Text(c, "后端: 官方 CLI").FontSize(11).TextColor(colMuted)
		}
	})
}

func jobLabel(job string) string {
	switch job {
	case "solve":
		return "正在生成 ISO"
	case "simulate":
		return "正在读回模拟"
	case "burn":
		return "正在刻录"
	case "selftest":
		return "正在自检"
	case "timing":
		return "正在测转速"
	case "geo":
		return "正在拟合几何"
	case "disexport":
		return "正在导出预设"
	}
	return job
}

func itoa(v int) string { return strconv.Itoa(v) }

// centerWrap lays its children in a column of at most maxW DIP,
// centred in the available width — the page layout the official GUI
// uses (its content column is capped at 1120 and centred), so pages
// stay put-together on wide windows instead of hugging the left edge.
func centerWrap(c *ui.Context, maxW float32, gap float32, children func()) {
	ui.Column(c).WidthPercent(100).AlignItems(ui.Center).Children(func() {
		ui.Column(c).WidthPercent(100).MaxWidth(maxW).Gap(gap).Children(children)
	})
}

// sectionCard draws a titled panel and lays its children inside.
func sectionCard(c *ui.Context, title string, children func()) {
	ui.Column(c).Background(colPanel).Radius(12).Border(1, colBorder).
		Padding(14).Gap(10).Children(func() {
		if title != "" {
			ov.Text(c, title).FontSize(13).Bold().TextColor(colMuted)
		}
		children()
	})
}

// logCard shows the last n log lines in a mono-ish muted block.
func (a *App) logCard(c *ui.Context, n int) {
	lines := a.logTail(n)
	sectionCard(c, "日志", func() {
		if len(lines) == 0 {
			ov.Text(c, "（暂无）").FontSize(12).TextColor(colMuted)
			return
		}
		for _, l := range lines {
			ov.Text(c, l).FontSize(12).TextColor(colMuted)
		}
	})
}

// progressRow shows a job progress bar when the named job is running.
func (a *App) progressRow(c *ui.Context, job string) {
	j, done, total, _ := a.jobState()
	if j != job {
		return
	}
	if total > 0 {
		ov.Progress(c, float64(done)/float64(total)).Label(jobLabel(job))
		ov.Text(c, itoa(done)+"/"+itoa(total)).FontSize(12).TextColor(colMuted)
	} else {
		ov.Progress(c, -1).Label(jobLabel(job))
	}
}

// ovSelect renders a Onevra select bound to value and reports whether the
// value changed this frame (Onevra selects surface no Changed event, so
// callers diff the value, as Onevra's own examples do). A positive width
// fixes the trigger width; otherwise it grows to fill its row.
func ovSelect(c *ui.Context, value *string, label string, choices []string, width float32) bool {
	before := *value
	sel := ov.Select(c, value)
	trigger := sel.Trigger.Label(label)
	if width > 0 {
		trigger.Width(width)
	} else {
		trigger.Grow(1)
	}
	trigger.Children(func() { ov.Text(c, *value).SingleLine() })
	sel.Popup(func(ui.Element) {
		for _, ch := range choices {
			sel.Item(ch).Label(ch).Children(func() { ov.Text(c, ch) })
		}
	})
	return before != *value
}
