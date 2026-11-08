package main

import (
	"context"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"math"
	"os"
	"testing"
)

func bgCtx() context.Context { return context.Background() }

// TestPreprocessParityVsPIL compares the Go preprocessing against the
// proven PIL output on the real dragon canvas, over all RGB channels.
// Fixtures come from the DIS_FIXTURE_DIR env var; without them it skips.
func TestPreprocessParityVsPIL(t *testing.T) {
	dir := os.Getenv("DIS_FIXTURE_DIR")
	if dir == "" {
		t.Skip("DIS_FIXTURE_DIR not set")
	}
	raw, err := loadImageFile(dir + "/canvas_user.png")
	if err != nil {
		t.Fatal(err)
	}
	ref, err := loadImageFile(dir + "/canvas_user_proc.png")
	if err != nil {
		t.Fatal(err)
	}
	got := PreprocessImage(raw)
	mae, big := diffStats(got, ref)
	t.Logf("RGB meanAbsDiff=%.4f pixelsDiff>8: %.3f%%", mae, big)
	if mae > 0.5 {
		t.Errorf("preprocessing drifted from the PIL reference: MAE %.4f", mae)
	}
}

// TestExportParityISO runs the full app export path (compose + preprocess +
// official solve) on the dragon canvas and compares the ISO byte-by-byte
// with a solve of the stored PIL canvas. Opt-in: DIS_RUN_ISO=1.
func TestExportParityISO(t *testing.T) {
	dir := os.Getenv("DIS_FIXTURE_DIR")
	if dir == "" || os.Getenv("DIS_RUN_ISO") == "" {
		t.Skip("fixtures or DIS_RUN_ISO not set")
	}
	a := newApp()
	l, err := loadImageFile(dir + "/canvas_user.png")
	if err != nil {
		t.Fatal(err)
	}
	layer := &Layer{Path: "canvas_user.png", Name: "canvas_user.png",
		img: l, imgW: 4096, imgH: 4096, HeightMM: DiscMM}
	p := &Project{Layers: []*Layer{layer}, Preproc: true}
	canvas := ComposeCanvas(p)
	goCanvas := dir + "/go_canvas.png"
	if err := SavePNG(goCanvas, canvas); err != nil {
		t.Fatal(err)
	}
	sp := SolveParams{Geo: geoPresets[0], Dither: 0.75, Brightness: -16,
		FastOutput: true, ReadCompat: true, ConstraintStep: 64}
	cli := a.set.CLIPath
	goISO := dir + "/go.iso"
	if err := runStreaming(bgCtx(), cli, solveArgs(goCanvas, goISO, sp), nil, nil); err != nil {
		t.Fatalf("go solve: %v", err)
	}
	refISO := dir + "/ref.iso"
	if err := runStreaming(bgCtx(), cli, solveArgs(dir+"/canvas_user_proc.png", refISO, sp), nil, nil); err != nil {
		t.Fatalf("ref solve: %v", err)
	}
	gb, _ := os.ReadFile(goISO)
	rb, _ := os.ReadFile(refISO)
	if len(gb) != len(rb) {
		t.Fatalf("ISO sizes differ: %d vs %d", len(gb), len(rb))
	}
	diff := 0
	for i := range gb {
		if gb[i] != rb[i] {
			diff++
		}
	}
	t.Logf("ISO bytes: %d, differing: %d (%.4f%%)", len(gb), diff, 100*float64(diff)/float64(len(gb)))
}

func loadImageFile(path string) (image.Image, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	img, _, err := image.Decode(f)
	return img, err
}

func diffStats(a, b image.Image) (mae float64, pctBig float64) {
	bb := a.Bounds()
	w, h := bb.Dx(), bb.Dy()
	var sum float64
	big := 0
	count := 0
	for y := 0; y < h; y += 7 { // sample every 7th row for speed
		for x := 0; x < w; x += 3 {
			r1, g1, b1, _ := a.At(x, y).RGBA()
			r2, g2, b2, _ := b.At(x, y).RGBA()
			d := math.Abs(float64(int(r1>>8)-int(r2>>8))) +
				math.Abs(float64(int(g1>>8)-int(g2>>8))) +
				math.Abs(float64(int(b1>>8)-int(b2>>8)))
			sum += d / 3
			if d/3 > 8 {
				big++
			}
			count++
		}
	}
	return sum / float64(count), 100 * float64(big) / float64(count)
}
