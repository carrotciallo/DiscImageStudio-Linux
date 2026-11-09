package main

import (
	"image"
	"image/color"
	"math"
	"testing"
)

func solidCanvas(size int, v uint8) *image.RGBA {
	img := image.NewRGBA(image.Rect(0, 0, size, size))
	for i := 0; i < len(img.Pix); i += 4 {
		img.Pix[i], img.Pix[i+1], img.Pix[i+2], img.Pix[i+3] = v, v, v, 255
	}
	return img
}

// cellMeans audits every burnCellSize cell's mean luminance.
func cellMeans(img *image.RGBA) []float64 {
	b := img.Bounds()
	var out []float64
	for cy := 0; cy < b.Dy(); cy += burnCellSize {
		for cx := 0; cx < b.Dx(); cx += burnCellSize {
			sum, n := 0.0, 0
			for ly := 0; ly < burnCellSize && cy+ly < b.Dy(); ly++ {
				for lx := 0; lx < burnCellSize && cx+lx < b.Dx(); lx++ {
					p := img.PixOffset(b.Min.X+cx+lx, b.Min.Y+cy+ly)
					sum += float64(lumAt(img.Pix, p))
					n++
				}
			}
			out = append(out, sum/float64(n))
		}
	}
	return out
}

func TestBurnSafePureBlackReachesFloor(t *testing.T) {
	img := solidCanvas(256, 0)
	flips := BurnSafeCanvas(img)
	if flips == 0 {
		t.Fatal("pure black canvas: no flips")
	}
	for i, m := range cellMeans(img) {
		if m < burnMeanFloor-0.5 {
			t.Fatalf("cell %d mean %.2f below floor %.1f", i, m, burnMeanFloor)
		}
	}
}

func TestBurnSafePureWhiteUntouched(t *testing.T) {
	img := solidCanvas(256, 255)
	if flips := BurnSafeCanvas(img); flips != 0 {
		t.Fatalf("pure white canvas: %d flips, want 0", flips)
	}
}

func TestBurnSafeBrightFlatUntouched(t *testing.T) {
	img := solidCanvas(256, 100) // realized dark fraction ≈0.65, safe
	if flips := BurnSafeCanvas(img); flips != 0 {
		t.Fatalf("flat 100 canvas: %d flips, want 0", flips)
	}
}

func TestBurnSafeQuotaExact(t *testing.T) {
	img := solidCanvas(256, 60)
	BurnSafeCanvas(img)
	// Per 16x16 cell: ceil(256*(80-60)/(255-60)) = ceil(26.25) = 27.
	for i, m := range cellMeans(img) {
		want := float64(27*255+229*60) / 256
		if math.Abs(m-want) > 0.6 {
			t.Fatalf("cell %d mean %.2f, want ≈%.2f", i, m, want)
		}
	}
}

func TestBurnSafeMicroGrainTreated(t *testing.T) {
	// Checkerboard 18/46: mean 32, std 14 — micro-grain, not detail.
	// Every pixel still lands in the dark class, so the cell is a
	// coherent slab and must be treated (regression: the first e2e
	// audit found escapees at std ≈12–14 under a std≤12 gate).
	img := image.NewRGBA(image.Rect(0, 0, 256, 256))
	for y := 0; y < 256; y++ {
		for x := 0; x < 256; x++ {
			v := uint8(18)
			if (x+y)%2 == 0 {
				v = 46
			}
			img.Set(x, y, color.RGBA{v, v, v, 255})
		}
	}
	if flips := BurnSafeCanvas(img); flips == 0 {
		t.Fatal("micro-grain dark canvas: no flips, want treatment")
	}
	for i, m := range cellMeans(img) {
		if m < burnMeanFloor-1.5 {
			t.Fatalf("cell %d mean %.2f below floor after treatment", i, m)
		}
	}
}

func TestBurnSafeTextureUntouched(t *testing.T) {
	// Dark-leaning but genuinely mixed: ~70% deep shadow (20), ~30%
	// highlights (180). Over a fifth of the cell is white-class
	// content at coarse grain — the mix that historically burns
	// fine — so the pass must not touch a pixel even though the
	// mean (68) is below the floor.
	img := image.NewRGBA(image.Rect(0, 0, 256, 256))
	seed := uint32(12345)
	for y := 0; y < 256; y++ {
		for x := 0; x < 256; x++ {
			seed = seed*1664525 + 1013904223
			v := uint8(20)
			if (seed>>24)%10 < 3 {
				v = 180
			}
			img.Set(x, y, color.RGBA{v, v, v, 255})
		}
	}
	before := append([]uint8(nil), img.Pix...)
	if flips := BurnSafeCanvas(img); flips != 0 {
		t.Fatalf("threshold-crossing texture: %d flips, want 0", flips)
	}
	for i := range before {
		if before[i] != img.Pix[i] {
			t.Fatalf("threshold-crossing texture modified at byte %d", i)
		}
	}
}

func TestBurnSafeSubThresholdNoiseTreated(t *testing.T) {
	// Noise entirely below the class threshold (0..89, mean ≈45) is
	// textured in RGB but flat at class level: every sample renders
	// dark, so it is a slab like any other and must be treated.
	img := image.NewRGBA(image.Rect(0, 0, 256, 256))
	seed := uint32(12345)
	for i := 0; i < len(img.Pix); i += 4 {
		seed = seed*1664525 + 1013904223
		v := uint8((seed >> 24) % 90)
		img.Pix[i], img.Pix[i+1], img.Pix[i+2], img.Pix[i+3] = v, v, v, 255
	}
	if flips := BurnSafeCanvas(img); flips == 0 {
		t.Fatal("sub-threshold noise: no flips, want treatment")
	}
	for i, m := range cellMeans(img) {
		if m < burnMeanFloor-0.5 {
			t.Fatalf("cell %d mean %.2f below floor after treatment", i, m)
		}
	}
}

func TestBurnSafeDeterministic(t *testing.T) {
	a := solidCanvas(256, 30)
	b := solidCanvas(256, 30)
	BurnSafeCanvas(a)
	BurnSafeCanvas(b)
	for i := range a.Pix {
		if a.Pix[i] != b.Pix[i] {
			t.Fatalf("nondeterministic at byte %d", i)
		}
	}
}

func TestBurnSafeFlipsDispersed(t *testing.T) {
	img := solidCanvas(256, 0)
	BurnSafeCanvas(img)
	// Largest 4-connected cluster of flipped (white) pixels in the
	// first cell must stay tiny: fine grain, never a blob.
	seen := make([]bool, 256*256)
	maxCluster := 0
	for y := 0; y < 256; y++ {
		for x := 0; x < 256; x++ {
			p := img.PixOffset(x, y)
			if img.Pix[p] != 255 || seen[y*256+x] {
				continue
			}
			size := 0
			stack := [][2]int{{x, y}}
			seen[y*256+x] = true
			for len(stack) > 0 {
				c := stack[len(stack)-1]
				stack = stack[:len(stack)-1]
				size++
				for _, d := range [][2]int{{1, 0}, {-1, 0}, {0, 1}, {0, -1}} {
					nx, ny := c[0]+d[0], c[1]+d[1]
					if nx < 0 || ny < 0 || nx >= 256 || ny >= 256 || seen[ny*256+nx] {
						continue
					}
					if img.Pix[img.PixOffset(nx, ny)] == 255 {
						seen[ny*256+nx] = true
						stack = append(stack, [2]int{nx, ny})
					}
				}
			}
			if size > maxCluster {
				maxCluster = size
			}
		}
	}
	if maxCluster > 8 {
		t.Fatalf("largest flipped cluster %d px, want ≤8 (fine grain)", maxCluster)
	}
}

func TestFlattenDefaultWhite(t *testing.T) {
	img := Flatten(nil, 64)
	for i := 0; i < len(img.Pix); i += 4 {
		if img.Pix[i] != 255 || img.Pix[i+1] != 255 || img.Pix[i+2] != 255 {
			t.Fatalf("uncovered canvas not white at byte %d: %v", i, img.Pix[i:i+3])
		}
	}
}

func TestComposeCanvasBlackLayerBurnSafe(t *testing.T) {
	src := solidCanvas(512, 0)
	l := &Layer{Path: "black.png", Name: "black.png", img: src, imgW: 512, imgH: 512,
		HeightMM: DiscMM}
	p := &Project{Layers: []*Layer{l}, Preproc: false}
	out := ComposeCanvas(p)
	for i, m := range cellMeans(out) {
		if m < burnMeanFloor-0.5 {
			t.Fatalf("composed cell %d mean %.2f below floor", i, m)
		}
	}
}

func BenchmarkBurnSafeCanvas(b *testing.B) {
	img := solidCanvas(CanvasPx, 0)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		BurnSafeCanvas(img)
	}
}
