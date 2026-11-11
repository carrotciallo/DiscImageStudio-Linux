package main

import (
	"fmt"
	"os"

	"github.com/egoist/mygo"
	"github.com/egoist/mygo/ui"
	ov "github.com/oneo-me/onevra/source/components"
)

func (a *App) pageHome(c *ui.Context) {
	centerWrap(c, 1120, 16, func() {
		ov.Text(c, "把图片刻进 DVD 数据面").FontSize(24).Bold().TextColor(colText)
		ov.Text(c, "设计构图 → 生成 ISO → 读回预览 → 实盘刻录。所有光盘数学由官方 CLI 完成，本应用只做交互与调度。").
			FontSize(13).TextColor(colMuted)
		// Pipeline status: where the current project stands, with the
		// jump to whichever step is next.
		mi := a.mediaInfo()
		ui.Row(c).Gap(12).Children(func() {
			layerStatus, layerOK := "还没有图层", false
			if len(a.proj.Layers) > 0 {
				layerStatus, layerOK = fmt.Sprintf("%d 个图层", len(a.proj.Layers)), true
			}
			a.statusCard(c, "① 设计构图", layerStatus, layerOK, "去设计", 1)
			isoStatus, isoOK := "尚未生成", false
			if st, err := os.Stat(a.proj.ISOPath); err == nil {
				isoStatus, isoOK = fmt.Sprintf("已生成 · %.0f MiB", float64(st.Size())/1048576), true
			}
			a.statusCard(c, "② 生成 ISO", isoStatus, isoOK, "去导出", 3)
			discStatus, discOK := "未检测到盘片", false
			if mi.Loaded {
				discStatus = mi.Status
				if mi.Blank {
					discStatus, discOK = "空白盘已就绪", true
				}
			}
			a.statusCard(c, "③ 刻录", discStatus, discOK, "去刻录", 4)
			if a.cliWarn != "" {
				a.statusCard(c, "CLI 版本", a.cliWarn, false, "去设置", 5)
			}
		})
		// Geometry preset tiles, the local counterpart of the official
		// GUI's home template tiles: one click applies the preset and
		// lands on the design page.
		sectionCard(c, "几何预设", func() {
			ov.Text(c, "点击应用该几何并进入设计页；校准导出的预设也会出现在这里。").
				FontSize(12).TextColor(colMuted)
			for _, g := range a.allPresets() {
				preset := g
				ui.Row(c).Gap(8).Children(func() {
					ov.Text(c, preset.Name).Grow(1).FontSize(13).TextColor(colText)
					ov.Text(c, fmt.Sprintf("%d 扇区 · 内径 %.3f · 外径 %.3f mm",
						preset.TotalSectors, preset.InnerMM, preset.OuterMM)).
						FontSize(12).TextColor(colMuted)
					label, variant := "应用", ov.ButtonSecondary
					if preset.Name == a.geo.Name {
						label, variant = "使用中", ov.ButtonGhost
					}
					if ov.Button(c, label, variant).Clicked() {
						a.geo = preset
						a.geoTotalF = float64(preset.TotalSectors)
						a.geoName = preset.Name
						a.fillF = float64(a.proj.FillSectors)
						a.page = 1
					}
				})
			}
		})
		sectionCard(c, "当前参数", func() {
			ov.Text(c, fmt.Sprintf("几何预设: %s（总扇区 %d，内径 %.4f mm，外径 %.4f mm）",
				a.geo.Name, a.geo.TotalSectors, a.geo.InnerMM, a.geo.OuterMM)).FontSize(13).TextColor(colText)
			ov.Text(c, fmt.Sprintf("色调: dither %.2f · brightness %.0f · 快速输出 %v · 读兼容 %v · 约束步长 %.0f",
				a.proj.Dither, a.proj.Brightness, a.proj.FastOutput, a.proj.ReadCompat, a.proj.ConstraintStep)).
				FontSize(13).TextColor(colText)
			ov.Text(c, fmt.Sprintf("图层 %d 个 · ISO 输出: %s", len(a.proj.Layers), a.proj.ISOPath)).
				FontSize(13).TextColor(colMuted)
		})
		a.logCard(c, 6)
	})
}

// statusCard is one pipeline-step card on the home page: the step's
// name, its live status, and the button that jumps to it.
func (a *App) statusCard(c *ui.Context, title, status string, ok bool, btnLabel string, page int) {
	ui.Column(c).Grow(1).Background(colPanel).Radius(12).Border(1, colBorder).
		Padding(14).Gap(8).Children(func() {
		ov.Text(c, title).FontSize(14).Bold().TextColor(colText)
		col := colMuted
		if ok {
			col = colOK
		}
		ov.Text(c, status).FontSize(12).TextColor(col)
		if ov.Button(c, btnLabel, ov.ButtonSecondary).Clicked() {
			a.page = page
		}
	})
}

// loadSimBitmap reads the simulate PNG into a display bitmap.
func (a *App) loadSimBitmap() {
	b, err := os.ReadFile(a.proj.SimPath)
	if err != nil {
		a.logf("读取预览图失败: %v", err)
		return
	}
	bmp, err := ui.DecodeBitmap(b)
	if err != nil {
		a.logf("解码预览图失败: %v", err)
		return
	}
	a.simBmp = bmp
	a.simNote = "预览图: " + a.proj.SimPath
}

func (a *App) pageSettings(c *ui.Context) {
	a.smoothScroll(c, 5).FillHeight().Children(func() {
		centerWrap(c, 720, 12, func() {
			sectionCard(c, "后端", func() {
				fieldText(c, "官方 CLI", &a.set.CLIPath)
				ui.Row(c).Gap(8).Children(func() {
					if ov.Button(c, "浏览…", ov.ButtonSecondary).Clicked() {
						go a.dialogPickCLI()
					}
					if ov.Button(c, "运行自检", ov.ButtonSecondary).Clicked() {
						go a.runSelftest()
					}
				})
				a.progressRow(c, "selftest")
			})
			sectionCard(c, "路径与设备", func() {
				fieldText(c, "工作目录", &a.set.WorkDir)
				fieldText(c, "刻录设备", &a.set.Device)
				fieldNum(c, "默认速度", &a.burnSpeedF, 1, 48, 1)
			})
			sectionCard(c, "校准后端", func() {
				fieldText(c, "disc-probe", &a.set.ProbeDir)
				fieldText(c, "Python", &a.set.Python)
			})
			sectionCard(c, "关于", func() {
				ov.Text(c, "Disc Image Studio · Linux 图形前端").FontSize(13).TextColor(colText)
				ov.Text(c, "MyGo（Go 原生 UI）壳 + 官方 disc-image-studio CLI 后端；本地版本，不联网。").
					FontSize(12).TextColor(colMuted)
				if ov.Button(c, "保存设置", ov.ButtonSecondary).Clicked() {
					a.set.BurnSpeed = int(a.burnSpeedF)
					a.set.save()
					a.logf("设置已保存")
				}
			})
			a.logCard(c, 8)
		})
	})
}

func (a *App) dialogPickCLI() {
	paths, err := mygo.Dialog.Open(mygo.OpenDialogOptions{Title: "选择 disc-image-studio 可执行文件"})
	if err != nil || len(paths) == 0 {
		return
	}
	a.set.CLIPath = paths[0]
	a.set.save()
	a.logf("CLI 路径: %s", paths[0])
}

// fieldText renders a labelled text input row.
func fieldText(c *ui.Context, label string, v *string) {
	ui.Row(c).Gap(8).Children(func() {
		ov.Text(c, label).Width(72).FontSize(13).TextColor(colMuted)
		ov.TextBox(c, v, ov.TextBoxOptions{}).Label(label).Grow(1)
	})
}
