package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/egoist/mygo"
	"github.com/egoist/mygo/ui"
)

func (a *App) pageExport(c *ui.Context) {
	job, _, _, _ := a.jobState()
	ui.Scroll(c).FillHeight().Children(func() {
		ui.Column(c).Gap(12).MaxWidth(860).Children(func() {
			sectionCard(c, "几何", func() {
				ui.Row(c).Gap(8).Children(func() {
					ui.Text(c, "预设").Width(72).FontSize(13).TextColor(colMuted)
					presets := a.allPresets()
					names := make([]string, len(presets))
					for i, g := range presets {
						names[i] = g.Name
					}
					sel := ui.Select(c, &a.geoName, names).Label("几何预设").Grow(1)
					if sel.Changed() {
						for _, g := range presets {
							if g.Name == a.geoName {
								a.geo = g
								a.geoTotalF = float64(g.TotalSectors)
							}
						}
					}
				})
				fieldNum(c, "总扇区", &a.geoTotalF, 16, 4600000, 16)
				fieldNum(c, "内径 mm", &a.geo.InnerMM, 20, 40, 0.001)
				fieldNum(c, "外径 mm", &a.geo.OuterMM, 40, 59, 0.001)
				fieldNum(c, "pitch 一次", &a.geo.PitchLinear, -0.01, 0.01, 0.000001)
				fieldNum(c, "pitch 二次", &a.geo.PitchQuad, -0.01, 0.01, 0.000001)
				fieldNum(c, "pitch 三次", &a.geo.PitchCubic, -0.01, 0.01, 0.000001)
				fieldNum(c, "填充扇区", &a.fillF, 0, 4600000, 16)
				ui.Text(c, "填充扇区 0 = 与总扇区相同（整盘）。").FontSize(11).TextColor(colMuted)
			})
			sectionCard(c, "色调与模式", func() {
				fieldSlider(c, "抖动", &a.proj.Dither, 0, 1, "%.2f")
				fieldSlider(c, "亮度", &a.proj.Brightness, -64, 64, "%.0f")
				fieldNum(c, "约束步长", &a.proj.ConstraintStep, 1, 512, 1)
				ui.Row(c).Gap(16).Children(func() {
					ui.Checkbox(c, &a.proj.FastOutput, "快速输出").Label("快速输出")
					ui.Checkbox(c, &a.proj.ReadCompat, "读兼容").Label("读兼容")
					ui.Checkbox(c, &a.proj.SRGBLinear, "sRGB 线性化").Label("sRGB 线性化")
				})
			})
			sectionCard(c, "输出", func() {
				fieldText(c, "ISO 文件", &a.proj.ISOPath)
				ui.Row(c).Gap(8).Children(func() {
					b := ui.PrimaryButton(c.Key("run-solve"), "生成 ISO").Label("生成 ISO")
					if job != "" || len(a.proj.Layers) == 0 {
						b.Disabled(true)
					}
					if b.Clicked() {
						go a.exportPipeline()
					}
					if len(a.proj.Layers) == 0 {
						ui.Text(c, "先在设计页添加图层").FontSize(12).TextColor(colMuted)
					}
				})
				a.progressRow(c, "solve")
			})
			a.logCard(c, 12)
		})
	})
}

// exportPipeline composes the canvas at full size and runs the official
// solver on it.
func (a *App) exportPipeline() {
	if err := ensureWorkDir(a.set.WorkDir); err != nil {
		a.logf("建工作目录失败: %v", err)
		return
	}
	if dir := filepath.Dir(a.proj.ISOPath); dir != "" {
		_ = ensureWorkDir(dir)
	}
	a.syncMirrors()
	a.logf("合成画布 %dx%d（预处理 %v）…", CanvasPx, CanvasPx, a.proj.Preproc)
	canvas := ComposeCanvas(&a.proj)
	canvasPath := filepath.Join(a.set.WorkDir, "canvas.png")
	if err := SavePNG(canvasPath, canvas); err != nil {
		a.logf("保存画布失败: %v", err)
		return
	}
	a.runSolve(canvasPath)
}

func (a *App) pageBurn(c *ui.Context) {
	job, _, _, _ := a.jobState()
	mi := a.mediaInfo()
	ui.Column(c).Gap(12).MaxWidth(860).Children(func() {
		sectionCard(c, "驱动器", func() {
			ui.Text(c, fmt.Sprintf("设备 %s", a.set.Device)).FontSize(13).TextColor(colText)
			status := mi.Status
			if mi.Loaded && mi.Media != "" {
				status += " · " + mi.Media
			}
			ui.Text(c, "盘面状态: "+status).FontSize(13).TextColor(colText)
			if mi.Blank {
				ui.Text(c, "空白盘已就绪").FontSize(12).TextColor(colOK)
			}
			if ui.Button(c.Key("refresh-media"), "刷新状态").Label("刷新驱动器状态").Clicked() {
				go a.refreshMedia()
			}
		})
		sectionCard(c, "刻录", func() {
			fieldText(c, "ISO 文件", &a.proj.ISOPath)
			if st, err := os.Stat(a.proj.ISOPath); err == nil {
				ui.Text(c, fmt.Sprintf("大小 %.0f MiB", float64(st.Size())/1048576)).
					FontSize(12).TextColor(colMuted)
			} else {
				ui.Text(c, "ISO 不存在，先在导出页生成").FontSize(12).TextColor(colDanger)
			}
			ui.Row(c).Gap(8).Children(func() {
				ui.Text(c, "速度").Width(52).FontSize(13).TextColor(colMuted)
				ui.Select(c, &a.speedSel, []string{"4", "8", "12", "16"}).Label("刻录速度").Width(120)
				ui.Text(c, "×（定版为 8×）").FontSize(12).TextColor(colMuted)
			})
			ui.Row(c).Gap(8).Children(func() {
				b := ui.Button(c.Key("run-burn"), "开始刻录").Label("开始刻录")
				if job != "" || !mi.Blank {
					b.Disabled(true)
				}
				if b.Clicked() {
					go a.confirmAndBurn()
				}
				if ui.Button(c.Key("eject"), "弹盘").Label("弹盘").Clicked() {
					go func() {
						_ = runEject(a.set.Device)
						a.refreshMedia()
					}()
				}
			})
			a.progressRow(c, "burn")
		})
		a.logCard(c, 12)
	})
}

func runEject(device string) error {
	return exec.Command("eject", device).Run()
}

func (a *App) confirmAndBurn() {
	res, err := mygo.Dialog.Message(mygo.MessageOptions{
		Type:    mygo.MessageWarning,
		Message: "把 ISO 刻录到当前盘片？",
		Detail:  a.proj.ISOPath,
		Buttons: []string{"取消", "刻录"},
	})
	if err != nil || res.Button != 1 {
		return
	}
	a.syncMirrors()
	a.set.save()
	a.runBurn()
}
