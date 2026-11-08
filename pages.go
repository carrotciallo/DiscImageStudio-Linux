package main

import (
	"fmt"
	"os"

	"github.com/egoist/mygo"
	"github.com/egoist/mygo/ui"
)

func (a *App) pageHome(c *ui.Context) {
	ui.Column(c).Gap(16).Children(func() {
		ui.Text(c, "把图片刻进 DVD 数据面").FontSize(24).Bold().TextColor(colText)
		ui.Text(c, "设计构图 → 生成 ISO → 读回预览 → 实盘刻录。所有光盘数学由官方 CLI 完成，本应用只做交互与调度。").
			FontSize(13).TextColor(colMuted)
		ui.Row(c).Gap(12).Children(func() {
			homeCard(c, "设计", "摆放图片图层、定构图", 1, a)
			homeCard(c, "导出", "按定版几何与色调生成 ISO", 3, a)
			homeCard(c, "读回预览", "模拟盘面在光下看到的样子", 2, a)
			homeCard(c, "刻录", "8× DAO 刻录并弹盘", 4, a)
		})
		sectionCard(c, "当前定版参数", func() {
			ui.Text(c, fmt.Sprintf("几何预设: %s（总扇区 %d，内径 %.4f mm，外径 %.4f mm）",
				a.geo.Name, a.geo.TotalSectors, a.geo.InnerMM, a.geo.OuterMM)).FontSize(13).TextColor(colText)
			ui.Text(c, fmt.Sprintf("色调: dither %.2f · brightness %.0f · 快速输出 %v · 读兼容 %v · 约束步长 %.0f",
				a.proj.Dither, a.proj.Brightness, a.proj.FastOutput, a.proj.ReadCompat, a.proj.ConstraintStep)).
				FontSize(13).TextColor(colText)
			ui.Text(c, fmt.Sprintf("图层 %d 个 · ISO 输出: %s", len(a.proj.Layers), a.proj.ISOPath)).
				FontSize(13).TextColor(colMuted)
		})
		a.logCard(c, 6)
	})
}

func homeCard(c *ui.Context, title, desc string, page int, a *App) {
	ui.Column(c).Width(220).Background(colPanel).Radius(12).Border(1, colBorder).
		Padding(16).Gap(8).Children(func() {
		ui.Text(c, title).FontSize(16).Bold().TextColor(colText)
		ui.Text(c, desc).FontSize(12).TextColor(colMuted)
		if ui.Button(c.Key("home-go-"+itoa(page)), "打开").Label("打开" + title).Clicked() {
			a.page = page
		}
	})
}

func (a *App) pagePreview(c *ui.Context) {
	job, _, _, _ := a.jobState()
	ui.Column(c).Gap(14).Children(func() {
		ui.Row(c).Gap(10).Children(func() {
			b := ui.PrimaryButton(c.Key("run-sim"), "生成读回预览").Label("生成读回预览")
			if job != "" {
				b.Disabled(true)
			}
			if b.Clicked() {
				go a.runSimulate()
			}
			ui.Text(c, "对当前 ISO 跑官方 simulate，渲染读回效果").FontSize(12).TextColor(colMuted)
		})
		a.progressRow(c, "simulate")
		if a.simBmp != nil {
			ui.Box(c).WidthPercent(100).AspectRatio(1).MaxWidth(560).MaxHeight(560).
				Background(colPanel).Radius(16).Border(1, colBorder).Children(func() {
				ui.Image(c, a.simBmp).Fill().Fit(ui.Contain)
			})
		} else {
			ui.Text(c, "还没有预览。先在导出页生成 ISO，再回来生成读回预览。").FontSize(13).TextColor(colMuted)
		}
		if a.simNote != "" {
			ui.Text(c, a.simNote).FontSize(12).TextColor(colMuted)
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
	ui.Scroll(c).FillHeight().Children(func() {
		ui.Column(c).Gap(12).MaxWidth(720).Children(func() {
			sectionCard(c, "后端", func() {
				fieldText(c, "官方 CLI", &a.set.CLIPath)
				ui.Row(c).Gap(8).Children(func() {
					if ui.Button(c.Key("pick-cli"), "浏览…").Label("选择官方 CLI").Clicked() {
						go a.dialogPickCLI()
					}
					if ui.Button(c.Key("selftest"), "运行自检").Label("运行官方 CLI 自检").Clicked() {
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
			sectionCard(c, "关于", func() {
				ui.Text(c, "Disc Image Studio · Linux 图形前端").FontSize(13).TextColor(colText)
				ui.Text(c, "MyGo（Go 原生 UI）壳 + 官方 disc-image-studio CLI 后端；本地版本，不联网。").
					FontSize(12).TextColor(colMuted)
				if ui.Button(c.Key("save-settings"), "保存设置").Label("保存设置").Clicked() {
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
		ui.Text(c, label).Width(72).FontSize(13).TextColor(colMuted)
		ui.TextInput(c, v).Label(label).Grow(1)
	})
}
