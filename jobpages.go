package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/egoist/mygo"
	"github.com/egoist/mygo/ui"
	ov "github.com/oneo-me/onevra/source/components"
)

func (a *App) pageExport(c *ui.Context) {
	job, _, _, _ := a.jobState()
	a.smoothScroll(c, 3).FillHeight().Children(func() {
		centerWrap(c, 960, 12, func() {
			sectionCard(c, "几何", func() {
				ui.Row(c).Gap(8).Children(func() {
					ov.Text(c, "预设").Width(72).FontSize(13).TextColor(colMuted)
					presets := a.allPresets()
					names := make([]string, len(presets))
					for i, g := range presets {
						names[i] = g.Name
					}
					if ovSelect(c, &a.geoName, "几何预设", names, 0) {
						for _, g := range presets {
							if g.Name == a.geoName {
								a.geo = g
								a.geoTotalF = float64(g.TotalSectors)
							}
						}
					}
				})
				ui.Row(c).AlignItems(ui.Start).Gap(16).Children(func() {
					ui.Column(c).Grow(1).Gap(10).Children(func() {
						fieldNum(c, "总扇区", &a.geoTotalF, 16, 4600000, 16)
						fieldNum(c, "内径 mm", &a.geo.InnerMM, 20, 40, 0.001)
						fieldNum(c, "外径 mm", &a.geo.OuterMM, 40, 59, 0.001)
						fieldNum(c, "pitch 一次", &a.geo.PitchLinear, -0.01, 0.01, 0.000001)
					})
					ui.Column(c).Grow(1).Gap(10).Children(func() {
						fieldNum(c, "pitch 二次", &a.geo.PitchQuad, -0.01, 0.01, 0.000001)
						fieldNum(c, "pitch 三次", &a.geo.PitchCubic, -0.01, 0.01, 0.000001)
						fieldNum(c, "填充扇区", &a.fillF, 0, 4600000, 16)
					})
				})
				ov.Text(c, "填充扇区 0 = 与总扇区相同（整盘）。").FontSize(11).TextColor(colMuted)
			})
			sectionCard(c, "色调与模式", func() {
				fieldSlider(c, "抖动", &a.proj.Dither, 0, 1, 0.01)
				fieldSlider(c, "亮度", &a.proj.Brightness, -64, 64, 1)
				fieldNum(c, "约束步长", &a.proj.ConstraintStep, 1, 512, 1)
				ui.Row(c).Gap(16).Children(func() {
					ov.Checkbox(c, &a.proj.FastOutput, "快速输出")
					ov.Checkbox(c, &a.proj.ReadCompat, "读兼容")
					ov.Checkbox(c, &a.proj.SRGBLinear, "sRGB 线性化")
				})
			})
			sectionCard(c, "输出", func() {
				fieldText(c, "ISO 文件", &a.proj.ISOPath)
				ui.Row(c).Gap(8).Children(func() {
					b := ov.Button(c, "生成 ISO", ov.ButtonPrimary)
					if job != "" || len(a.proj.Layers) == 0 {
						b.Disabled(true)
					}
					if b.Clicked() {
						go a.exportPipeline()
					}
					if len(a.proj.Layers) == 0 {
						ov.Text(c, "先在设计页添加图层").FontSize(12).TextColor(colMuted)
					}
				})
				a.progressRow(c, "solve")
			})
			sectionCard(c, "读回预览", func() {
				_, isoErr := os.Stat(a.proj.ISOPath)
				ui.Row(c).Gap(10).Children(func() {
					b := ov.Button(c, "生成读回预览", ov.ButtonPrimary)
					if job != "" || isoErr != nil {
						b.Disabled(true)
					}
					if b.Clicked() {
						go a.runSimulate()
					}
					ov.Text(c, "对当前 ISO 跑官方 simulate，渲染盘面读回效果").FontSize(12).TextColor(colMuted)
				})
				a.progressRow(c, "simulate")
				if a.simBmp != nil {
					ui.Row(c).Children(func() {
						ui.Box(c).Grow(1)
						ui.Box(c).Width(620).Height(620).
							Background(colPanel2).Radius(16).Border(1, colBorder).Children(func() {
							ui.Image(c, a.simBmp).Fill().Fit(ui.Contain)
						})
						ui.Box(c).Grow(1)
					})
					if a.simNote != "" {
						ov.Text(c, a.simNote).FontSize(12).TextColor(colMuted)
					}
				} else if isoErr != nil {
					ov.Text(c, "先在上面生成 ISO，再生成读回预览。").FontSize(12).TextColor(colMuted)
				} else {
					ov.Text(c, "还没有预览。生成 ISO 后点「生成读回预览」看盘面效果。").FontSize(12).TextColor(colMuted)
				}
			})
			a.logCard(c, 12)
			ui.Row(c).Children(func() {
				ui.Box(c).Grow(1)
				b := ov.Button(c, "下一步：去刻录 →", ov.ButtonPrimary)
				if _, err := os.Stat(a.proj.ISOPath); err != nil {
					b.Disabled(true)
				}
				if b.Clicked() {
					a.page = 4
				}
			})
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
	centerWrap(c, 860, 12, func() {
		ui.Row(c).Children(func() {
			if ov.Button(c, "← 返回导出", ov.ButtonGhost).Clicked() {
				a.page = 3
			}
		})
		sectionCard(c, "驱动器", func() {
			ov.Text(c, fmt.Sprintf("设备 %s", a.set.Device)).FontSize(13).TextColor(colText)
			status := mi.Status
			if mi.Loaded && mi.Media != "" {
				status += " · " + mi.Media
			}
			ov.Text(c, "盘面状态: "+status).FontSize(13).TextColor(colText)
			if mi.Blank {
				ov.Text(c, "空白盘已就绪").FontSize(12).TextColor(colOK)
			}
			if ov.Button(c, "刷新状态", ov.ButtonSecondary).Clicked() {
				go a.refreshMedia()
			}
		})
		sectionCard(c, "刻录", func() {
			fieldText(c, "ISO 文件", &a.proj.ISOPath)
			if st, err := os.Stat(a.proj.ISOPath); err == nil {
				ov.Text(c, fmt.Sprintf("大小 %.0f MiB", float64(st.Size())/1048576)).
					FontSize(12).TextColor(colMuted)
			} else {
				ov.Text(c, "ISO 不存在，先在导出页生成").FontSize(12).TextColor(colDanger)
			}
			ui.Row(c).Gap(8).Children(func() {
				ov.Text(c, "速度").Width(52).FontSize(13).TextColor(colMuted)
				ovSelect(c, &a.speedSel, "刻录速度", []string{"4", "8", "12", "16"}, 120)
				ov.Text(c, "×（定版为 8×）").FontSize(12).TextColor(colMuted)
			})
			ui.Row(c).Gap(8).Children(func() {
				b := ov.Button(c, "开始刻录", ov.ButtonSecondary)
				if job != "" || !mi.Blank {
					b.Disabled(true)
				}
				if b.Clicked() {
					go a.confirmAndBurn()
				}
				if ov.Button(c, "弹盘", ov.ButtonSecondary).Clicked() {
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
