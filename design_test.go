package main

import (
	"image"
	"image/color"
	"math"
	"testing"

	"github.com/egoist/mygo/ui"
)

func testLayer() *Layer {
	// 200x100 px source at 40 mm height -> 80 mm wide, centred at (10, -5), rotated 30°.
	return &Layer{X: 10, Y: -5, HeightMM: 40, Rotation: 30, imgW: 200, imgH: 100}
}

func TestLayerCornersAndHit(t *testing.T) {
	l := testLayer()
	hw, hh := layerHalf(l)
	if hw != 40 || hh != 20 {
		t.Fatalf("half extents = %v,%v want 40,20", hw, hh)
	}
	if !layerHit(l, 10, -5) {
		t.Error("centre should hit")
	}
	if layerHit(l, 100, 80) {
		t.Error("far point should miss")
	}
	// A corner itself must hit (boundary is inclusive).
	c := layerCornersMM(l)[2]
	if !layerHit(l, c[0], c[1]) {
		t.Errorf("corner %v should hit", c)
	}
	// Unrotated layer: corner math is plain offsets.
	l.Rotation = 0
	c = layerCornersMM(l)[1]
	if c[0] != 50 || c[1] != -25 {
		t.Errorf("unrotated corner = %v want [50 -25]", c)
	}
}

func TestCanvasDragMoveAndScale(t *testing.T) {
	a := newApp()
	l := testLayer()
	l.Rotation = 0
	a.proj.Layers = []*Layer{l}
	a.proj.Sel = 0
	a.canvasW, a.canvasH = 580, 580
	k := float32(a.canvasK()) // DIP per mm at the current view field

	// Press at the layer centre: (10,-5)mm -> DIP (290+10k, 290-5k).
	if !a.canvasInput(ui.InputEvent{Kind: ui.InputPointerDown, Button: 0, X: 290 + 10*k, Y: 290 - 5*k}) {
		t.Fatal("press on layer not taken")
	}
	// Drag by (+10k, +5k) DIP = (+10, +5) mm.
	if !a.canvasInput(ui.InputEvent{Kind: ui.InputPointerMove, X: 290 + 20*k, Y: 290}) {
		t.Fatal("drag move not taken")
	}
	if l.X != 20 || l.Y != 0 {
		t.Errorf("after drag layer at %v,%v want 20,0", l.X, l.Y)
	}
	a.canvasInput(ui.InputEvent{Kind: ui.InputPointerUp, Button: 0})

	// Press the bottom-right corner handle, then scale x1.5.
	cx, cy := 290+20*k, float32(290.0) // layer centre in DIP after the move
	corner := [2]float32{cx + 40*k, cy + 20*k}
	if !a.canvasInput(ui.InputEvent{Kind: ui.InputPointerDown, Button: 0, X: corner[0], Y: corner[1]}) {
		t.Fatal("press on corner handle not taken")
	}
	// Move the corner 1.5x farther from the centre.
	nx := cx + (corner[0]-cx)*1.5
	ny := cy + (corner[1]-cy)*1.5
	a.canvasInput(ui.InputEvent{Kind: ui.InputPointerMove, X: nx, Y: ny})
	if math.Abs(l.HeightMM-60) > 0.011 {
		t.Errorf("after corner drag height = %v want 60", l.HeightMM)
	}
	a.canvasInput(ui.InputEvent{Kind: ui.InputPointerUp, Button: 0})

	// Wheel up one notch (DY=-50) grows height by e^0.1.
	before := l.HeightMM
	if !a.canvasInput(ui.InputEvent{Kind: ui.InputScroll, DY: -50}) {
		t.Fatal("canvas wheel not taken")
	}
	if math.Abs(l.HeightMM-before*math.Exp(0.1)) > 0.01 {
		t.Errorf("wheel scale: height = %v want %v", l.HeightMM, before*math.Exp(0.1))
	}
	// Press on empty canvas is left alone.
	if a.canvasInput(ui.InputEvent{Kind: ui.InputPointerDown, Button: 0, X: 20, Y: 20}) {
		t.Error("press on empty canvas should not be taken")
	}
}

func TestViewFieldFixedDefault(t *testing.T) {
	a := newApp()
	if f := a.viewFieldMM(); math.Abs(f-DiscMM/canvasPad) > 0.01 {
		t.Errorf("empty project field = %.2f, want %.2f", f, DiscMM/canvasPad)
	}
	// An oversized, off-centre layer must NOT move the view: the field
	// is the user's zoom choice, never fitted to the layers (auto-fit
	// shrank the disc in use and made wheel-scaling zoom the scene).
	big := &Layer{X: 40, imgW: 100, imgH: 100, HeightMM: 200}
	a.proj.Layers = []*Layer{big}
	if f := a.viewFieldMM(); math.Abs(f-DiscMM/canvasPad) > 0.01 {
		t.Errorf("oversized layer field = %.2f, want fixed %.2f", f, DiscMM/canvasPad)
	}
	a.zoomField = 100
	if f := a.viewFieldMM(); f != 100 {
		t.Errorf("manual zoom field = %.2f, want 100", f)
	}
}

// TestPreviewFieldAlignment pins the design-preview invariant: the
// composed bitmap is rendered at the view field, so a layer's picture
// lands at the same normalised position the overlays (drawn from the
// same field) promise. Regression guard for the unpadded-bitmap bug,
// where the picture rendered 13.6% larger than its outline.
func TestPreviewFieldAlignment(t *testing.T) {
	black := image.NewRGBA(image.Rect(0, 0, 100, 100))
	for y := 0; y < 100; y++ {
		for x := 0; x < 100; x++ {
			black.Set(x, y, color.RGBA{0, 0, 0, 255})
		}
	}
	l := &Layer{img: black, imgW: 100, imgH: 100, X: 29, HeightMM: 13}
	centroidX := func(img *image.RGBA) float64 {
		sum, n := 0.0, 0.0
		b := img.Bounds()
		for y := b.Min.Y; y < b.Max.Y; y++ {
			for x := b.Min.X; x < b.Max.X; x++ {
				if r, _, _, _ := img.At(x, y).RGBA(); r < 0x8000 {
					sum += float64(x)
					n++
				}
			}
		}
		return sum / n / float64(b.Dx())
	}
	preview := flatten([]*Layer{l}, 1024, DiscMM/canvasPad, true, false)
	if got, want := centroidX(preview), 0.5+29/(DiscMM/canvasPad); math.Abs(got-want) > 0.01 {
		t.Errorf("preview centroid fraction = %.3f, want %.3f", got, want)
	}
	full := Flatten([]*Layer{l}, 1024)
	if got, want := centroidX(full), 0.5+29/DiscMM; math.Abs(got-want) > 0.01 {
		t.Errorf("export centroid fraction = %.3f, want %.3f", got, want)
	}
}
