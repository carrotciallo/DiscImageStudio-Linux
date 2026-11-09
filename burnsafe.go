package main

import (
	"image"
	"math"
)

// Burn-safety by construction (2026-11-10 design decision).
//
// Root cause this guards: on 2026-11-07 controlled burns, and again on
// 2026-11-09 when the first GUI burn died at 28.7% with SCSI [3 0C 00]
// write errors, large FLAT dark fields killed the writer: after the
// solver's tone stage they become coarse slabs of one pit class,
// coherent over hundreds of tracks. Flat bright fields are innocent
// (the sparse class burns safely at any size).
//
// A probe against the official CLI (2026-11-10, work/probe-dither)
// showed the tone stack's realized dark-class fraction is, within
// ±0.01, a function of the local mean luminance alone, however that
// mean is composed (flat level or dispersed bright inserts):
// R(0)=1.00, R(60)=0.856, R(100)=0.647, R(131)=0.483. The fraction
// crosses the 0.80 danger line at mean ≈ 71.
//
// So this pass walks the export canvas once, in 16 px cells. A cell
// is dangerous when its mean is dark enough to sit over the line AND
// it lacks coarse white-class content (fraction of pixels at or above
// the class threshold < burnMinWhiteFrac): wiggle that never crosses
// the threshold — JPEG grain, sharpening halos, sub-threshold texture
// — is still one coherent slab at class level, whatever its std-dev
// says (the first e2e audits found escapees at std 12–25, all with
// zero above-threshold pixels). Dangerous cells get their mean lifted
// to burnMeanFloor by flipping the exact quota of pixels to white in
// dispersed-dot (Morton) order — the same fine grain the proven
// hand-noised discs had, but placed by quota inside the same single
// pass: nothing is re-checked, re-solved or re-done. R(80) ≈ 0.75
// keeps every treated cell clear of the line. Cells with real detail
// (highlights crossing the threshold, the texture that historically
// burned fine) are never touched, and neither is anything at or above
// the floor.
const (
	burnCellSize = 16
	// Realized dark fraction crosses 0.80 at mean ≈71 (probe); the
	// floor keeps a margin, landing at ≈0.75.
	burnMeanFloor = 80.0
	// Solver's dark/white class boundary (probe-pinned).
	burnClassThresh = 128
	// At or above this fraction of above-threshold pixels, a cell's
	// pattern is genuinely mixed at coarse grain and safe as-is.
	burnMinWhiteFrac = 0.20
)

// mortonRank bit-reverses the Morton interleave of x and y (each
// 0..15) into a rank 0..255: the lowest ranks are the widest lattice
// (rank <64 = every 2nd pixel, <16 = every 4th, <4 = every 8th), so
// the k lowest ranks always form a maximally dispersed set.
func mortonRank(x, y int) int {
	r := 0
	for i := 0; i < 4; i++ {
		r |= ((x >> i) & 1) << (2*(3-i) + 1)
		r |= ((y >> i) & 1) << (2 * (3 - i))
	}
	return r
}

func lumAt(pix []uint8, p int) int {
	return (19595*int(pix[p]) + 38470*int(pix[p+1]) + 7471*int(pix[p+2])) >> 16
}

// BurnSafeCanvas applies the pass in place (img is an origin-based
// RGBA as produced by Flatten/PreprocessImage) and returns the number
// of flipped pixels.
func BurnSafeCanvas(img *image.RGBA) int {
	b := img.Bounds()
	w, h := b.Dx(), b.Dy()
	flips := 0
	var rankLift [256]int
	for cy := 0; cy < h; cy += burnCellSize {
		ch := min(burnCellSize, h-cy)
		for cx := 0; cx < w; cx += burnCellSize {
			cw := min(burnCellSize, w-cx)
			n := cw * ch
			for i := range rankLift {
				rankLift[i] = 0
			}
			sum := 0.0
			above := 0
			for ly := 0; ly < ch; ly++ {
				row := (b.Min.Y+cy+ly)*img.Stride + (b.Min.X+cx)*4
				for lx := 0; lx < cw; lx++ {
					y := lumAt(img.Pix, row+lx*4)
					sum += float64(y)
					if y >= burnClassThresh {
						above++
					}
					if y < 255 {
						rankLift[mortonRank(lx, ly)] += 255 - y
					}
				}
			}
			mean := sum / float64(n)
			if mean >= burnMeanFloor {
				continue
			}
			if float64(above)/float64(n) >= burnMinWhiteFrac {
				continue // genuinely mixed at coarse grain: safe as-is
			}
			// Quota: flip the lowest-rank candidates until their
			// combined lift (255 − value each) raises the cell mean
			// to the floor. Ranks are unique per pixel within a
			// cell, so the quota is exact, not an estimate.
			liftNeed := int(math.Ceil(float64(n) * (burnMeanFloor - mean)))
			rankT := 256 // sentinel: flip every candidate
			cum := 0
			for r := 0; r < 256; r++ {
				cum += rankLift[r]
				if cum >= liftNeed {
					rankT = r
					break
				}
			}
			for ly := 0; ly < ch; ly++ {
				row := (b.Min.Y+cy+ly)*img.Stride + (b.Min.X+cx)*4
				for lx := 0; lx < cw; lx++ {
					p := row + lx*4
					if lumAt(img.Pix, p) >= 255 {
						continue
					}
					if mortonRank(lx, ly) <= rankT {
						img.Pix[p], img.Pix[p+1], img.Pix[p+2] = 255, 255, 255
						flips++
					}
				}
			}
		}
	}
	return flips
}
