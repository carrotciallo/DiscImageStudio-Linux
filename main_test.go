package main

import (
	"image"
	"image/color"
	"strings"
	"testing"

	"github.com/egoist/mygo/ui"
)

func TestSolveArgsParity(t *testing.T) {
	p := SolveParams{
		Geo: geoPresets[0], Dither: 0.75, Brightness: -16,
		FastOutput: true, ReadCompat: true, ConstraintStep: 64,
	}
	args := solveArgs("canvas.png", "out.iso", p)
	joined := strings.Join(args, " ")
	for _, want := range []string{
		"solve", "--image canvas.png", "--iso-output out.iso",
		"--total-sectors 2298336", "--fill-sectors 2298336",
		"--inner-radius-mm 24.173269389549194",
		"--tone-dither 0.75", "--tone-brightness -16",
		"--fast-output true", "--read-compatibility true",
		"--constraint-step 64",
	} {
		if !strings.Contains(joined, want) {
			t.Errorf("args %q missing %q", joined, want)
		}
	}
}

// markerImage is a 100x100 black image with a white block at its top-left.
func markerImage() *image.RGBA {
	img := image.NewRGBA(image.Rect(0, 0, 100, 100))
	for y := 0; y < 100; y++ {
		for x := 0; x < 100; x++ {
			img.Set(x, y, color.RGBA{0, 0, 0, 255})
		}
	}
	for y := 0; y < 20; y++ {
		for x := 0; x < 20; x++ {
			img.Set(x, y, color.RGBA{255, 255, 255, 255})
		}
	}
	return img
}

func brightAt(img *image.RGBA, x, y int) bool {
	r, _, _, _ := img.At(x, y).RGBA()
	return r > 0x8000
}

func TestFlattenPlacement(t *testing.T) {
	// Layer height 58mm on a 232px canvas (2px/mm): scale = 58*2/100 = 1.16.
	// The 20px marker becomes ~23px at the layer's top-left, which sits at
	// canvas (58,58) when centred: layer spans (58,58)..(174,174).
	l := &Layer{img: markerImage(), imgW: 100, imgH: 100, HeightMM: 58}
	out := Flatten([]*Layer{l}, 232)
	if !brightAt(out, 64, 64) {
		t.Error("marker should be visible near (64,64)")
	}
	if brightAt(out, 170, 64) {
		t.Error("marker should not reach (170,64)")
	}
}

func TestFlattenRotationClockwise(t *testing.T) {
	// Rotating +90 (clockwise on screen) moves the top-left marker to the
	// top-right of the layer box: layer spans (58,58)..(174,174), so the
	// marker should appear near (160,64) and not near (64,64).
	l := &Layer{img: markerImage(), imgW: 100, imgH: 100, HeightMM: 58, Rotation: 90}
	out := Flatten([]*Layer{l}, 232)
	if !brightAt(out, 160, 64) {
		t.Error("clockwise rotation should put the marker near (160,64)")
	}
	if brightAt(out, 64, 64) {
		t.Error("marker should have left (64,64) after rotation")
	}
}

func TestPreprocessStepEdge(t *testing.T) {
	img := image.NewRGBA(image.Rect(0, 0, 64, 64))
	for y := 0; y < 64; y++ {
		for x := 0; x < 64; x++ {
			v := uint8(100)
			if x >= 32 {
				v = 160
			}
			img.Set(x, y, color.RGBA{v, v, v, 255})
		}
	}
	out := PreprocessImage(img)
	// Autocontrast stretches 100..160 towards the ends; the step must stay a
	// step and the dark side must get darker than the input.
	r0, _, _, _ := out.At(4, 32).RGBA()
	r1, _, _, _ := out.At(59, 32).RGBA()
	if !(r0 < 100<<8 && r1 > 160<<8) {
		t.Errorf("autocontrast did not stretch: left=%d right=%d", r0>>8, r1>>8)
	}
}

func TestShellNavigation(t *testing.T) {
	a := newApp()
	tt := ui.NewTester(a.view, 1320, 860)
	if !tt.HasText("Disc Image Studio") {
		t.Fatalf("home missing title, texts: %v", tt.Texts())
	}
	if err := tt.Click("设计"); err != nil {
		t.Fatal(err)
	}
	if !tt.HasText("还没有图层") {
		t.Errorf("design page should show the empty state, texts: %v", tt.Texts())
	}
	if err := tt.Click("导出"); err != nil {
		t.Fatal(err)
	}
	if !tt.HasText("生成 ISO") {
		t.Errorf("export page should show the solve button, texts: %v", tt.Texts())
	}
	if err := tt.Click("设置"); err != nil {
		t.Fatal(err)
	}
	if !tt.HasText("保存设置") {
		t.Errorf("settings page missing save, texts: %v", tt.Texts())
	}
}
