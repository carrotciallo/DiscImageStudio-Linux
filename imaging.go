package main

import (
	"fmt"
	"image"
	"image/color"
	_ "image/jpeg"
	"image/png"
	_ "image/png"
	"math"
	"os"

	"golang.org/x/image/draw"
	"golang.org/x/image/math/f64"
)

// CanvasBG is the flatten base: the part of the disc no layer covers.
// It is white on purpose (2026-11-10): uncovered area must land in the
// sparse "white" pit class, which burns safely at any size, instead of
// the dense dark class, whose large flat fields killed a burn with
// SCSI write errors (see burnsafe.go).
var CanvasBG = color.RGBA{255, 255, 255, 255}

// LoadLayer decodes an image file into a Layer with a fit-to-disc default
// placement: the whole picture visible, centred.
func LoadLayer(path string) (*Layer, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	img, _, err := image.Decode(f)
	if err != nil {
		return nil, fmt.Errorf("解码图片失败: %w", err)
	}
	b := img.Bounds()
	w, h := b.Dx(), b.Dy()
	l := &Layer{Path: path, Name: baseName(path), img: img, imgW: w, imgH: h}
	// Fit inside the disc: the longer side spans the full 116 mm.
	if w >= h {
		l.HeightMM = DiscMM * float64(h) / float64(w)
	} else {
		l.HeightMM = DiscMM
	}
	return l, nil
}

func baseName(p string) string {
	for i := len(p) - 1; i >= 0; i-- {
		if p[i] == '/' {
			return p[i+1:]
		}
	}
	return p
}

// Flatten composites all layers onto a square canvas of the given pixel
// size, full quality: original sources, CatmullRom kernel. It does plain
// 2D picture placement only; all disc mathematics stays in the official
// CLI. The export path uses this; the design preview uses flatten's
// cheaper tiers (see refreshFlatBitmap).
func Flatten(layers []*Layer, size int) *image.RGBA {
	return flatten(layers, size, DiscMM, false, false)
}

// previewMaxEdge bounds the design-preview proxy of a layer source. The
// preview canvas is 1024 px, so a 1536 px proxy keeps sampling
// cache-friendly without visible loss; the full source stays untouched
// for export.
const previewMaxEdge = 1536

// previewSrc returns the layer's preview proxy, building it once. A
// full-size Flatten of a multi-megapixel source costs ~1 s (rotated
// CatmullRom sampling scattered over a ~100 MB image), which made
// canvas drags run at ~1 fps; the proxy bounds that cost.
func (l *Layer) previewSrc() image.Image {
	if l.img == nil {
		return nil
	}
	if max(l.imgW, l.imgH) <= previewMaxEdge {
		return l.img
	}
	if l.proxy == nil {
		s := float64(previewMaxEdge) / float64(max(l.imgW, l.imgH))
		w := max(1, int(float64(l.imgW)*s+0.5))
		h := max(1, int(float64(l.imgH)*s+0.5))
		dst := image.NewRGBA(image.Rect(0, 0, w, h))
		draw.CatmullRom.Scale(dst, dst.Bounds(), l.img, l.img.Bounds(), draw.Src, nil)
		l.proxy = dst
	}
	return l.proxy
}

// flatten is Flatten with a view field and quality tiers: fieldMM is
// how many millimetres span the square (the design preview passes its
// view field so the picture shares one geometry with the overlays;
// export passes DiscMM). preview swaps in each layer's bounded proxy
// source, fast additionally drops to the ApproxBiLinear kernel (the
// caller also drops the canvas size) for gesture-rate rebuilds.
func flatten(layers []*Layer, size int, fieldMM float64, preview, fast bool) *image.RGBA {
	dst := image.NewRGBA(image.Rect(0, 0, size, size))
	draw.Draw(dst, dst.Bounds(), &image.Uniform{CanvasBG}, image.Point{}, draw.Src)
	k := float64(size) / fieldMM // px per mm
	var kern draw.Transformer = draw.CatmullRom
	if fast {
		kern = draw.ApproxBiLinear
	}
	for _, l := range layers {
		src := l.img
		if preview {
			src = l.previewSrc()
		}
		if src == nil {
			continue
		}
		sb := src.Bounds()
		scale := (l.HeightMM * k) / float64(sb.Dy())
		th := l.Rotation * math.Pi / 180
		cos, sin := math.Cos(th), math.Sin(th)
		// x/image/draw's Transform takes the src->dst matrix:
		// dst = C + scale*R*(src - srcCentre), R clockwise in y-down space.
		cx := float64(size)/2 + l.X*k
		cy := float64(size)/2 + l.Y*k
		scx := float64(sb.Dx()) / 2
		scy := float64(sb.Dy()) / 2
		a := scale * cos
		b := -scale * sin
		d := scale * sin
		e := scale * cos
		m := f64.Aff3{
			a, b, cx - (a*scx + b*scy),
			d, e, cy - (d*scx + e*scy),
		}
		kern.Transform(dst, m, src, sb, draw.Over, nil)
	}
	return dst
}

// autocontrastLUT builds Pillow ImageOps.autocontrast's integer LUT: cut
// the given percentage of pixels from both histogram ends, then stretch
// with integer division, (i-lo)*255/(hi-lo). Verified exact against PIL.
func autocontrastLUT(y []uint8, cutoff float64) [256]uint8 {
	var lut [256]uint8
	for i := range lut {
		lut[i] = uint8(i)
	}
	var hist [256]int
	for _, v := range y {
		hist[v]++
	}
	cut := int(float64(len(y)) * cutoff / 100)
	lo, hi := 0, 255
	acc := 0
	for i := 0; i < 256; i++ {
		acc += hist[i]
		if acc > cut {
			lo = i
			break
		}
	}
	acc = 0
	for i := 255; i >= 0; i-- {
		acc += hist[i]
		if acc > cut {
			hi = i
			break
		}
	}
	if hi <= lo {
		return lut
	}
	for i := 0; i < 256; i++ {
		switch {
		case i < lo:
			lut[i] = 0
		case i > hi:
			lut[i] = 255
		default:
			lut[i] = uint8((i - lo) * 255 / (hi - lo))
		}
	}
	return lut
}

// boxBlurU8 blurs a uint8 plane with a box kernel of the given radius,
// sliding-window, edge pixels extended, each pass rounded to uint8 — the
// way Pillow's BoxBlur quantises between passes.
func boxBlurU8(y []uint8, w, h, radius int) []uint8 {
	win := 2*radius + 1
	half := win / 2
	tmp := make([]uint8, w*h)
	out := make([]uint8, w*h)
	for row := 0; row < h; row++ {
		base := row * w
		acc := 0
		for t := -radius; t <= radius; t++ {
			c := t
			if c < 0 {
				c = 0
			}
			acc += int(y[base+c])
		}
		for col := 0; col < w; col++ {
			tmp[base+col] = uint8((acc + half) / win)
			co := col - radius
			if co < 0 {
				co = 0
			}
			ci := col + radius + 1
			if ci >= w {
				ci = w - 1
			}
			acc += int(y[base+ci]) - int(y[base+co])
		}
	}
	for col := 0; col < w; col++ {
		acc := 0
		for t := -radius; t <= radius; t++ {
			r := t
			if r < 0 {
				r = 0
			}
			acc += int(tmp[r*w+col])
		}
		for row := 0; row < h; row++ {
			out[row*w+col] = uint8((acc + half) / win)
			ro := row - radius
			if ro < 0 {
				ro = 0
			}
			ri := row + radius + 1
			if ri >= h {
				ri = h - 1
			}
			acc += int(tmp[ri*w+col]) - int(tmp[ro*w+col])
		}
	}
	return out
}

// pillowGaussian blurs like Pillow's GaussianBlur: three box blurs whose
// sizes come from Pillow's box-size derivation for the given radius
// (radius 6 -> box sizes 11, 11, 13).
func pillowGaussian(y []uint8, w, h int, radius float64) []uint8 {
	const n = 3
	wIdeal := math.Sqrt(12*radius*radius/n + 1)
	wl := int(math.Floor(wIdeal))
	if wl%2 == 0 {
		wl--
	}
	wu := wl + 2
	mIdeal := (12*radius*radius - float64(n*wl*wl) - float64(4*n*wl) - float64(3*n)) / float64(-4*wl-4)
	m := int(mIdeal + 0.5)
	out := y
	for i := 0; i < n; i++ {
		size := wu
		if i < m {
			size = wl
		}
		out = boxBlurU8(out, w, h, (size-1)/2)
	}
	return out
}

func clip255(v int) uint8 {
	if v < 0 {
		return 0
	}
	if v > 255 {
		return 255
	}
	return uint8(v)
}

// PreprocessImage runs the proven PIL pipeline exactly as the定版 disc was
// made: split to YCbCr (Pillow's fixed-point JPEG conversion), autocontrast
// (cutoff 1%) and UnsharpMask (radius 6, 80%, threshold 2) on the Y channel
// only, keep chroma untouched, convert back to RGB. Verified byte-close
// against the stored PIL output in the parity test.
func PreprocessImage(src image.Image) *image.RGBA {
	b := src.Bounds()
	w, h := b.Dx(), b.Dy()
	n := w * h
	yp := make([]uint8, n)
	cb := make([]uint8, n)
	cr := make([]uint8, n)
	for row := 0; row < h; row++ {
		for col := 0; col < w; col++ {
			r, g, bl, _ := src.At(b.Min.X+col, b.Min.Y+row).RGBA()
			R, G, B := int(r>>8), int(g>>8), int(bl>>8)
			i := row*w + col
			// Pillow's conversion truncates (no rounding offset).
			yp[i] = uint8((19595*R + 38470*G + 7471*B) >> 16)
			cb[i] = clip255((8388608 - 11056*R - 21712*G + 32768*B) >> 16)
			cr[i] = clip255((8388608 + 32768*R - 27440*G - 5328*B) >> 16)
		}
	}
	lut := autocontrastLUT(yp, 1)
	for i, v := range yp {
		yp[i] = lut[v]
	}
	blur := pillowGaussian(yp, w, h, 6)
	for i, v := range yp {
		diff := int(v) - int(blur[i])
		if diff > 2 || diff < -2 {
			yp[i] = clip255(int(math.Round(float64(v) + float64(diff)*0.8)))
		}
	}
	out := image.NewRGBA(image.Rect(0, 0, w, h))
	for i := 0; i < n; i++ {
		Y := int(yp[i])
		cbD := int(cb[i]) - 128
		crD := int(cr[i]) - 128
		out.Pix[i*4+0] = clip255(Y + ((91881 * crD) >> 16))
		out.Pix[i*4+1] = clip255(Y + ((-22554*cbD - 46802*crD) >> 16))
		out.Pix[i*4+2] = clip255(Y + ((116130 * cbD) >> 16))
		out.Pix[i*4+3] = 255
	}
	return out
}

// ComposeCanvas flattens the project at full export size, applies the
// preprocessing when enabled, and always finishes with the burn-safety
// pass (burnsafe.go): a fixed single sweep after which any image is
// burnable by construction.
func ComposeCanvas(p *Project) *image.RGBA {
	flat := Flatten(p.Layers, CanvasPx)
	out := flat
	if p.Preproc {
		out = PreprocessImage(flat)
	}
	BurnSafeCanvas(out)
	return out
}

func SavePNG(path string, img image.Image) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return png.Encode(f, img)
}
