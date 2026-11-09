package main

import (
	"math"

	"github.com/egoist/mygo"
	"github.com/egoist/mygo/ui"
	ov "github.com/oneo-me/onevra/source/components"
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

// layerHalf returns the layer's half width and height in mm; the width
// follows from the height and the source aspect ratio.
func layerHalf(l *Layer) (hw, hh float64) {
	hh = l.HeightMM / 2
	if l.imgH > 0 {
		hw = float64(l.imgW) * (l.HeightMM / float64(l.imgH)) / 2
	}
	return hw, hh
}

// layerCornersMM returns the layer's four corners in disc-centred mm,
// in the same order the outline painter walks them.
func layerCornersMM(l *Layer) [4][2]float64 {
	hw, hh := layerHalf(l)
	th := l.Rotation * math.Pi / 180
	cos, sin := math.Cos(th), math.Sin(th)
	var out [4][2]float64
	for i, pt := range [4][2]float64{{-hw, -hh}, {hw, -hh}, {hw, hh}, {-hw, hh}} {
		out[i] = [2]float64{l.X + pt[0]*cos - pt[1]*sin, l.Y + pt[0]*sin + pt[1]*cos}
	}
	return out
}

// layerHit reports whether disc-centred mm point (mx, my) falls inside
// the layer's rotated rectangle.
func layerHit(l *Layer, mx, my float64) bool {
	th := l.Rotation * math.Pi / 180
	cos, sin := math.Cos(th), math.Sin(th)
	dx, dy := mx-l.X, my-l.Y
	lx, ly := dx*cos+dy*sin, -dx*sin+dy*cos
	hw, hh := layerHalf(l)
	return math.Abs(lx) <= hw && math.Abs(ly) <= hh
}

const (
	dragNone = iota
	dragMove
	dragScale
)

// canvasPad is the fraction of the canvas box the disc diameter spans.
// The margin keeps corner handles of layers that overshoot the rim
// (portrait art taller than the disc is the norm here) inside the box,
// where they stay visible and grabbable.
const canvasPad = 0.88

// canvasK is the canvas scale in DIP per mm.
func (a *App) canvasK() float64 {
	s := a.canvasW
	if a.canvasH < s {
		s = a.canvasH
	}
	return float64(s) * canvasPad / DiscMM
}

// canvasPointerMM converts canvas-element DIP coords to disc-centred mm
// using the geometry the last DrawOver pass recorded.
func (a *App) canvasPointerMM(x, y float32) (mx, my float64) {
	k := a.canvasK()
	if k <= 0 {
		return 0, 0
	}
	return (float64(x) - float64(a.canvasW)/2) / k, (float64(y) - float64(a.canvasH)/2) / k
}

// round2 trims gesture results to 0.01 mm so the number fields do not
// fill with binary float tails.
func round2(v float64) float64 { return math.Round(v*100) / 100 }

// canvasInput drives the design canvas gestures: drag a layer to move
// it, drag a corner of the selected layer to scale it about its centre,
// wheel over the canvas to scale the selected layer finely (hi-res
// sub-steps land as ~1% factors, so the G502 X scales smoothly).
func (a *App) canvasInput(ev ui.InputEvent) bool {
	switch ev.Kind {
	case ui.InputScroll:
		l := a.selectedLayer()
		if l == nil || ev.Mods&ui.Ctrl != 0 || ev.DY == 0 {
			return false
		}
		l.HeightMM = round2(min(240, max(8, l.HeightMM*math.Exp(-float64(ev.DY)*0.002))))
		return true
	case ui.InputPointerDown:
		if ev.Button != 0 || len(a.proj.Layers) == 0 || a.canvasW <= 0 {
			return false
		}
		mx, my := a.canvasPointerMM(ev.X, ev.Y)
		k := a.canvasK()
		if l := a.selectedLayer(); l != nil {
			for _, cmm := range layerCornersMM(l) {
				if math.Hypot((mx-cmm[0])*k, (my-cmm[1])*k) <= 10 {
					a.dragMode = dragScale
					a.dragBaseH = l.HeightMM
					a.dragBaseDist = math.Hypot(mx-l.X, my-l.Y)
					return true
				}
			}
		}
		for i := len(a.proj.Layers) - 1; i >= 0; i-- {
			if layerHit(a.proj.Layers[i], mx, my) {
				a.proj.Sel = i
				a.flatDirty = true
				a.dragMode = dragMove
				a.dragStart = [2]float64{mx, my}
				a.dragBaseX, a.dragBaseY = a.proj.Layers[i].X, a.proj.Layers[i].Y
				return true
			}
		}
		return false
	case ui.InputPointerMove:
		l := a.selectedLayer()
		if l == nil || a.dragMode == dragNone {
			return false
		}
		mx, my := a.canvasPointerMM(ev.X, ev.Y)
		switch a.dragMode {
		case dragMove:
			l.X = round2(min(80, max(-80, a.dragBaseX+mx-a.dragStart[0])))
			l.Y = round2(min(80, max(-80, a.dragBaseY+my-a.dragStart[1])))
		case dragScale:
			if a.dragBaseDist >= 0.5 {
				d := math.Hypot(mx-l.X, my-l.Y)
				l.HeightMM = round2(min(240, max(8, a.dragBaseH*d/a.dragBaseDist)))
			}
		}
		return true
	case ui.InputPointerUp:
		if a.dragMode != dragNone {
			a.dragMode = dragNone
			return true
		}
	}
	return false
}

// discCanvas draws the disc: the flattened composition clipped to the disc
// circle, hub and rim guides, and the selected layer's outline.
func (a *App) discCanvas(c *ui.Context) {
	ui.Column(c).Grow(1).FillHeight().Center().Children(func() {
		box := ui.Box(c).WidthPercent(100).AspectRatio(1).MaxWidth(680).MaxHeight(680).
			Background(colPanel).Radius(16).Border(1, colBorder)
		box.HandleInput(a.canvasInput)
		box.Children(func() {
			if a.flatBmp != nil {
				ui.Image(c, a.flatBmp).Fill().Fit(ui.Contain)
			}
		})
		box.DrawOver(func(p *ui.Painter, r ui.Rect) {
			a.canvasW, a.canvasH = r.W, r.H
			s := r.W
			if r.H < s {
				s = r.H
			}
			s *= canvasPad
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
			// Selected layer outline and corner scale handles.
			if l := a.selectedLayer(); l != nil {
				corners := layerCornersMM(l)
				rect := &ui.Path{}
				for i, cmm := range corners {
					x, y := cx+float32(cmm[0])*k, cy+float32(cmm[1])*k
					if i == 0 {
						rect.MoveTo(x, y)
					} else {
						rect.LineTo(x, y)
					}
				}
				rect.Close()
				p.StrokePath(rect.Dash(0, 6, 4), 1.5, colAccent)
				for _, cmm := range corners {
					x, y := cx+float32(cmm[0])*k, cy+float32(cmm[1])*k
					h := &ui.Path{}
					h.MoveTo(x-4.5, y-4.5).LineTo(x+4.5, y-4.5).LineTo(x+4.5, y+4.5).
						LineTo(x-4.5, y+4.5).Close()
					p.FillPath(h, colAccent)
					p.StrokePath(h, 1.5, colPanel)
				}
			}
		})
		ov.Text(c, "拖动图层移动 · 拖四角或滚轮缩放选中图层 · 导出时应用预处理与全分辨率合成").FontSize(11).TextColor(colMuted)
	})
}

func (a *App) designPanel(c *ui.Context) {
	a.smoothScroll(c, 1).Width(330).FillHeight().Children(func() {
		ui.Column(c).Gap(12).Padding(2).Children(func() {
			sectionCard(c, "图层", func() {
				if ov.Button(c, "＋ 添加图片", ov.ButtonSecondary).Clicked() {
					go a.dialogAddLayer()
				}
				for i, l := range a.proj.Layers {
					name := l.Name
					variant := ov.ButtonGhost
					if i == a.proj.Sel {
						variant = ov.ButtonSecondary
					}
					if ov.Button(c, name, variant).Clicked() {
						a.proj.Sel = i
						a.flatDirty = true
					}
				}
				if len(a.proj.Layers) == 0 {
					ov.Text(c, "还没有图层。添加一张图片开始构图。").FontSize(12).TextColor(colMuted)
				}
				if a.selectedLayer() != nil {
					if ov.Button(c, "删除选中图层", ov.ButtonSecondary).Clicked() {
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
					fieldSlider(c, "高度", &l.HeightMM, 8, 240, 0.1)
					fieldSlider(c, "旋转°", &l.Rotation, -180, 180, 0.5)
					ui.Row(c).Gap(8).Children(func() {
						if ov.Button(c, "居中", ov.ButtonGhost).Clicked() {
							l.X, l.Y = 0, 0
						}
						if ov.Button(c, "适合宽度", ov.ButtonGhost).Clicked() {
							l.HeightMM = DiscMM * float64(l.imgH) / float64(l.imgW)
						}
						if ov.Button(c, "铺满高度", ov.ButtonGhost).Clicked() {
							l.HeightMM = DiscMM
						}
					})
				})
			}
			sectionCard(c, "画布", func() {
				ov.Switch(c, &a.proj.Preproc, "定版预处理（对比度＋锐化）")
				ov.Text(c, "在亮度通道做 autocontrast(cutoff 1%) 与 unsharp(r6/80%)，与定版流程一致；关闭时原图直出。").
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
	a.poke()
}

// fieldNum renders a labelled number input row.
func fieldNum(c *ui.Context, label string, v *float64, lo, hi, step float64) {
	ui.Row(c).Gap(8).Children(func() {
		ov.Text(c, label).Width(52).FontSize(13).TextColor(colMuted)
		ov.NumberInput(c, v, lo, hi, step).Label(label).Grow(1)
	})
}

// fieldSlider renders a labelled slider + number input row. The step
// quantises slider drags, keyboard arrows and the number input's own
// scrub/stepper, so fine values stay reachable from every control.
func fieldSlider(c *ui.Context, label string, v *float64, lo, hi, step float64) {
	ui.Row(c).Gap(8).Children(func() {
		ov.Text(c, label).Width(52).FontSize(13).TextColor(colMuted)
		ov.Slider(c, v, lo, hi, ov.SliderOptions{Step: step}).Label(label).Grow(1)
		ov.NumberInput(c, v, lo, hi, step).Width(104).Label(label + " 数值")
	})
}
