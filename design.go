package main

import (
	"math"

	"github.com/egoist/mygo"
	"github.com/egoist/mygo/ui"
)

// layerSnapshot detects edits to the selected layer so the design preview
// bitmap is only rebuilt when something actually changed.
type layerSnapshot struct {
	n       int
	sel     int
	x, y    float64
	h, rot  float64
	preproc bool
}

var snap layerSnapshot

func (a *App) markDirtyIfChanged() {
	cur := layerSnapshot{n: len(a.proj.Layers), sel: a.proj.Sel, preproc: a.proj.Preproc}
	if l := a.selectedLayer(); l != nil {
		cur.x, cur.y, cur.h, cur.rot = l.X, l.Y, l.HeightMM, l.Rotation
	}
	if cur != snap {
		snap = cur
		a.flatDirty = true
	}
}

func (a *App) selectedLayer() *Layer {
	if a.proj.Sel >= 0 && a.proj.Sel < len(a.proj.Layers) {
		return a.proj.Layers[a.proj.Sel]
	}
	return nil
}

func (a *App) refreshFlatBitmap() {
	if !a.flatDirty {
		return
	}
	a.flatDirty = false
	flat := Flatten(a.proj.Layers, 1024)
	a.flatBmp = ui.NewBitmap(flat)
}

func (a *App) pageDesign(c *ui.Context) {
	a.markDirtyIfChanged()
	a.refreshFlatBitmap()
	ui.Row(c).Grow(1).Gap(16).Children(func() {
		a.discCanvas(c)
		a.designPanel(c)
	})
}

// discCanvas draws the disc: the flattened composition clipped to the disc
// circle, hub and rim guides, and the selected layer's outline.
func (a *App) discCanvas(c *ui.Context) {
	ui.Column(c).Grow(1).FillHeight().Center().Children(func() {
		box := ui.Box(c).Size(620, 620).Background(colPanel).Radius(16).
			Border(1, colBorder)
		box.Children(func() {
			if a.flatBmp != nil {
				ui.Image(c, a.flatBmp).Size(620, 620).Fit(ui.Contain)
			}
		})
		box.DrawOver(func(p *ui.Painter, r ui.Rect) {
			s := r.W
			if r.H < s {
				s = r.H
			}
			cx, cy := r.X+r.W/2, r.Y+r.H/2
			k := s / float32(DiscMM)
			// Mask the corners outside the disc with the panel colour.
			mask := (&ui.Path{}).FillRule(ui.EvenOdd)
			mask.MoveTo(r.X, r.Y).LineTo(r.X+r.W, r.Y).LineTo(r.X+r.W, r.Y+r.H).
				LineTo(r.X, r.Y+r.H).Close()
			mask.Circle(cx, cy, float32(RimR)*k)
			p.FillPath(mask, colPanel)
			// Rim and hub guides.
			rim := (&ui.Path{}).Circle(cx, cy, float32(RimR)*k)
			p.StrokePath(rim, 1.5, colMuted)
			hub := (&ui.Path{}).Circle(cx, cy, float32(HubR)*k)
			p.FillPath(hub, colPanel)
			p.StrokePath(hub, 1.5, colMuted)
			hole := (&ui.Path{}).Circle(cx, cy, 7.5*k)
			p.FillPath(hole, colBg)
			// Selected layer outline.
			if l := a.selectedLayer(); l != nil {
				hw := float64(l.imgW) * (l.HeightMM / float64(l.imgH)) / 2
				hh := l.HeightMM / 2
				th := l.Rotation * math.Pi / 180
				cos, sin := math.Cos(th), math.Sin(th)
				rect := &ui.Path{}
				for i, pt := range [4][2]float64{{-hw, -hh}, {hw, -hh}, {hw, hh}, {-hw, hh}} {
					x := cx + float32((l.X+pt[0]*cos-pt[1]*sin))*k
					y := cy + float32((l.Y+pt[0]*sin+pt[1]*cos))*k
					if i == 0 {
						rect.MoveTo(x, y)
					} else {
						rect.LineTo(x, y)
					}
				}
				rect.Close()
				p.StrokePath(rect.Dash(0, 6, 4), 1.5, colAccent)
			}
		})
		ui.Text(c, "盘面预览（导出时应用预处理与全分辨率合成）").FontSize(11).TextColor(colMuted)
	})
}

func (a *App) designPanel(c *ui.Context) {
	ui.Scroll(c).Width(330).FillHeight().Children(func() {
		ui.Column(c).Gap(12).Padding(2).Children(func() {
			sectionCard(c, "图层", func() {
				if ui.Button(c.Key("add-layer"), "＋ 添加图片").Label("添加图片").Clicked() {
					go a.dialogAddLayer()
				}
				for i, l := range a.proj.Layers {
					name := l.Name
					b := ui.Button(c.Key("layer-"+itoa(i)), name).Label("图层 " + name)
					if i == a.proj.Sel {
						b.Background(colAccentBg)
					}
					if b.Clicked() {
						a.proj.Sel = i
						a.flatDirty = true
					}
				}
				if len(a.proj.Layers) == 0 {
					ui.Text(c, "还没有图层。添加一张图片开始构图。").FontSize(12).TextColor(colMuted)
				}
				if a.selectedLayer() != nil {
					if ui.Button(c.Key("del-layer"), "删除选中图层").Label("删除选中图层").Clicked() {
						a.proj.Layers = append(a.proj.Layers[:a.proj.Sel], a.proj.Layers[a.proj.Sel+1:]...)
						if a.proj.Sel >= len(a.proj.Layers) {
							a.proj.Sel = len(a.proj.Layers) - 1
						}
						a.flatDirty = true
					}
				}
			})
			if l := a.selectedLayer(); l != nil {
				sectionCard(c, "图层属性（毫米）", func() {
					fieldNum(c, "X", &l.X, -80, 80, 0.1)
					fieldNum(c, "Y", &l.Y, -80, 80, 0.1)
					fieldSlider(c, "高度", &l.HeightMM, 8, 240, "%.1f")
					fieldSlider(c, "旋转°", &l.Rotation, -180, 180, "%.0f")
					ui.Row(c).Gap(8).Children(func() {
						if ui.Button(c.Key("ly-center"), "居中").Label("图层居中").Clicked() {
							l.X, l.Y = 0, 0
						}
						if ui.Button(c.Key("ly-fit"), "适合宽度").Label("适合宽度").Clicked() {
							l.HeightMM = DiscMM * float64(l.imgH) / float64(l.imgW)
						}
						if ui.Button(c.Key("ly-full"), "铺满高度").Label("铺满高度").Clicked() {
							l.HeightMM = DiscMM
						}
					})
				})
			}
			sectionCard(c, "画布", func() {
				ui.Row(c).Gap(8).Children(func() {
					ui.Switch(c, &a.proj.Preproc).Label("画布预处理")
					ui.Text(c, "定版预处理（对比度＋锐化）").FontSize(13).TextColor(colText)
				})
				ui.Text(c, "在亮度通道做 autocontrast(cutoff 1%) 与 unsharp(r6/80%)，与定版流程一致；关闭时原图直出。").
					FontSize(12).TextColor(colMuted)
			})
		})
	})
}

func (a *App) dialogAddLayer() {
	paths, err := mygo.Dialog.Open(mygo.OpenDialogOptions{
		Title:   "选择图片",
		Filters: []mygo.FileFilter{{Name: "图片", Extensions: []string{"png", "jpg", "jpeg", "webp", "bmp"}}},
	})
	if err != nil || len(paths) == 0 {
		return
	}
	l, err := LoadLayer(paths[0])
	if err != nil {
		a.logf("添加图层失败: %v", err)
		return
	}
	a.proj.Layers = append(a.proj.Layers, l)
	a.proj.Sel = len(a.proj.Layers) - 1
	a.flatDirty = true
	a.logf("已添加图层 %s (%dx%d)", l.Name, l.imgW, l.imgH)
}

// fieldNum renders a labelled number input row.
func fieldNum(c *ui.Context, label string, v *float64, lo, hi, step float64) {
	ui.Row(c).Gap(8).Children(func() {
		ui.Text(c, label).Width(52).FontSize(13).TextColor(colMuted)
		ui.NumberInput(c, v, lo, hi, step).Label(label).Grow(1)
	})
}

// fieldSlider renders a labelled slider + number input row.
func fieldSlider(c *ui.Context, label string, v *float64, lo, hi float64, _ string) {
	ui.Row(c).Gap(8).Children(func() {
		ui.Text(c, label).Width(52).FontSize(13).TextColor(colMuted)
		ui.Slider(c, v, lo, hi).Label(label).Grow(1)
		ui.NumberInput(c, v, lo, hi, (hi-lo)/100).Width(76).Label(label + " 数值")
	})
}
