package main

import (
	"log"
	"strconv"

	"github.com/egoist/mygo"
	"github.com/egoist/mygo/ui"
)

// Palette: a calm dark studio theme. The disc preview is the hero; chrome
// stays quiet around it.
var (
	colBg       = ui.Hex("#101216")
	colPanel    = ui.Hex("#171a20")
	colPanel2   = ui.Hex("#1e222b")
	colBorder   = ui.Hex("#2a2f3a")
	colText     = ui.Hex("#e8eaf0")
	colMuted    = ui.Hex("#9aa3b2")
	colAccent   = ui.Hex("#6ea8fe")
	colAccentBg = ui.Hex("#24334d")
	colDanger   = ui.Hex("#ff7a7a")
	colOK       = ui.Hex("#7bd88f")
)

var pageNames = []string{"首页", "设计", "读回预览", "导出", "刻录", "设置"}
var pageKeys = []string{"home", "design", "preview", "export", "burn", "settings"}

func main() {
	a := newApp()
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
	job, _, _, jobErr := a.jobState()
	if job != "" {
		c.AnimationFrame() // keep progress and logs flowing
	}
	ui.Row(c).Fill().Background(colBg).Children(func() {
		a.nav(c)
		ui.Column(c).Grow(1).FillHeight().Padding(20).Gap(16).Children(func() {
			if jobErr != "" {
				ui.Text(c, "上次任务出错: "+jobErr).TextColor(colDanger).FontSize(13)
			}
			switch a.page {
			case 0:
				a.pageHome(c)
			case 1:
				a.pageDesign(c)
			case 2:
				a.pagePreview(c)
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
		ui.Text(c, "Disc Image Studio").FontSize(17).Bold().TextColor(colText)
		ui.Text(c, "Linux 图形前端 · MyGo").FontSize(11).TextColor(colMuted)
		ui.Box(c).Height(10)
		for i, name := range pageNames {
			b := ui.Button(c.Key("nav-"+pageKeys[i]), name).Label(name).Width(180)
			if a.page == i {
				b.Background(colAccentBg).TextColor(colText)
			}
			if b.Clicked() {
				a.page = i
				a.set.save()
			}
		}
		ui.Box(c).Grow(1)
		if job != "" {
			ui.Row(c).Gap(8).Children(func() {
				ui.Spinner(c)
				label := jobLabel(job)
				if total > 0 {
					label += " " + itoa(done) + "/" + itoa(total)
				}
				ui.Text(c, label).FontSize(12).TextColor(colMuted)
			})
		} else {
			ui.Text(c, "后端: 官方 CLI").FontSize(11).TextColor(colMuted)
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
		}
	return job
}

func itoa(v int) string { return strconv.Itoa(v) }

// sectionCard draws a titled panel and lays its children inside.
func sectionCard(c *ui.Context, title string, children func()) {
	ui.Column(c).Background(colPanel).Radius(12).Border(1, colBorder).
		Padding(14).Gap(10).Children(func() {
		if title != "" {
			ui.Text(c, title).FontSize(13).Bold().TextColor(colMuted)
		}
		children()
	})
}

// logCard shows the last n log lines in a mono-ish muted block.
func (a *App) logCard(c *ui.Context, n int) {
	lines := a.logTail(n)
	sectionCard(c, "日志", func() {
		if len(lines) == 0 {
			ui.Text(c, "（暂无）").FontSize(12).TextColor(colMuted)
			return
		}
		for _, l := range lines {
			ui.Text(c, l).FontSize(12).TextColor(colMuted)
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
		ui.Progress(c, float64(done)/float64(total)).Label(jobLabel(job))
		ui.Text(c, itoa(done)+"/"+itoa(total)).FontSize(12).TextColor(colMuted)
	} else {
		ui.Progress(c, -1).Label(jobLabel(job))
	}
}
