package main

import (
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
	a.canvasW, a.canvasH = 580, 580 // k = 580*0.88/116 = 4.4 DIP per mm

	// Press at the layer centre: (10,-5)mm -> DIP (290+44, 290-22).
	if !a.canvasInput(ui.InputEvent{Kind: ui.InputPointerDown, Button: 0, X: 334, Y: 268}) {
		t.Fatal("press on layer not taken")
	}
	// Drag by (+44, +22) DIP = (+10, +5) mm.
	if !a.canvasInput(ui.InputEvent{Kind: ui.InputPointerMove, X: 378, Y: 290}) {
		t.Fatal("drag move not taken")
	}
	if l.X != 20 || l.Y != 0 {
		t.Errorf("after drag layer at %v,%v want 20,0", l.X, l.Y)
	}
	a.canvasInput(ui.InputEvent{Kind: ui.InputPointerUp, Button: 0})

	// Press the bottom-right corner handle, then scale x1.5.
	cx, cy := 290+20*4.4, 290.0 // layer centre in DIP after the move
	corner := [2]float32{float32(cx + 40*4.4), float32(cy + 20*4.4)}
	if !a.canvasInput(ui.InputEvent{Kind: ui.InputPointerDown, Button: 0, X: corner[0], Y: corner[1]}) {
		t.Fatal("press on corner handle not taken")
	}
	// Move the corner 1.5x farther from the centre.
	nx := float32(cx) + (corner[0]-float32(cx))*1.5
	ny := float32(cy) + (corner[1]-float32(cy))*1.5
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
