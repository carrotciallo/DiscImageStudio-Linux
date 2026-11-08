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

// CanvasBG is the design canvas background (#181b22), the same base the
// proven pipeline used.
var CanvasBG = color.RGBA{24, 27, 34, 255}

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
// size. It does plain 2D picture placement only; all disc mathematics stays
// in the official CLI.
func Flatten(layers []*Layer, size int) *image.RGBA {
	dst := image.NewRGBA(image.Rect(0, 0, size, size))
	draw.Draw(dst, dst.Bounds(), &image.Uniform{CanvasBG}, image.Point{}, draw.Src)
	k := float64(size) / DiscMM // px per mm
	for _, l := range layers {
		if l.img == nil {
			continue
		}
		scale := (l.HeightMM * k) / float64(l.imgH)
		th := l.Rotation * math.Pi / 180
		cos, sin := math.Cos(th), math.Sin(th)
		// x/image/draw's Transform takes the src->dst matrix:
		// dst = C + scale*R*(src - srcCentre), R clockwise in y-down space.
		cx := float64(size)/2 + l.X*k
		cy := float64(size)/2 + l.Y*k
		scx := float64(l.imgW) / 2
		scy := float64(l.imgH) / 2
		a := scale * cos
		b := -scale * sin
		d := scale * sin
		e := scale * cos
		m := f64.Aff3{
			a, b, cx - (a*scx + b*scy),
			d, e, cy - (d*scx + e*scy),
		}
		draw.CatmullRom.Transform(dst, m, l.img, l.img.Bounds(), draw.Over, nil)
	}
	return dst
}

// luminance extracts the ITU-R 601 luma plane with Pillow's integer
// coefficients, so the Go preprocessing tracks the proven PIL pipeline.
func luminance(img image.Image) ([]float32, int, int) {
	b := img.Bounds()
	w, h := b.Dx(), b.Dy()
	y := make([]float32, w*h)
	for row := 0; row < h; row++ {
		for col := 0; col < w; col++ {
			r, g, bl, _ := img.At(b.Min.X+col, b.Min.Y+row).RGBA()
			y[row*w+col] = float32((19595*(r>>8) + 38470*(g>>8) + 7471*(bl>>8) + 0x8000) >> 16)
		}
	}
	return y, w, h
}

// autocontrast applies Pillow ImageOps.autocontrast semantics: cut the
// given percentage of pixels from both histogram ends, then stretch.
func autocontrast(y []float32, cutoff float64) {
	var hist [256]int
	for _, v := range y {
		hist[int(v+0.5)]++
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
		return
	}
	scale := 255 / float64(hi-lo)
	for i, v := range y {
		nv := (float64(v) - float64(lo)) * scale
		if nv < 0 {
			nv = 0
		}
		if nv > 255 {
			nv = 255
		}
		y[i] = float32(nv)
	}
}

// gaussianBlur is a separable Gaussian blur over a luma plane.
func gaussianBlur(y []float32, w, h int, sigma float64) []float32 {
	radius := int(math.Ceil(sigma * 3))
	kern := make([]float64, 2*radius+1)
	sum := 0.0
	for i := range kern {
		x := float64(i - radius)
		kern[i] = math.Exp(-(x * x) / (2 * sigma * sigma))
		sum += kern[i]
	}
	for i := range kern {
		kern[i] /= sum
	}
	tmp := make([]float32, w*h)
	out := make([]float32, w*h)
	for row := 0; row < h; row++ {
		for col := 0; col < w; col++ {
			acc := 0.0
			for t := -radius; t <= radius; t++ {
				c := col + t
				if c < 0 {
					c = 0
				}
				if c >= w {
					c = w - 1
				}
				acc += float64(y[row*w+c]) * kern[t+radius]
			}
			tmp[row*w+col] = float32(acc)
		}
	}
	for row := 0; row < h; row++ {
		for col := 0; col < w; col++ {
			acc := 0.0
			for t := -radius; t <= radius; t++ {
				r := row + t
				if r < 0 {
					r = 0
				}
				if r >= h {
					r = h - 1
				}
				acc += float64(tmp[r*w+col]) * kern[t+radius]
			}
			out[row*w+col] = float32(acc)
		}
	}
	return out
}

// unsharpSigma is the Gaussian sigma standing in for Pillow's
// UnsharpMask radius=6; fitted against PIL output in the parity checks.
var unsharpSigma = 3.0

// PreprocessImage runs the 定版 pipeline on the luma channel:
// autocontrast (cutoff 1%) then unsharp mask (80%, threshold 2). The disc
// only carries luminance, so the result is a grayscale image.
func PreprocessImage(src image.Image) *image.RGBA {
	y, w, h := luminance(src)
	autocontrast(y, 1)
	blur := gaussianBlur(y, w, h, unsharpSigma)
	out := image.NewRGBA(image.Rect(0, 0, w, h))
	for i, v := range y {
		diff := float64(v - blur[i])
		nv := float64(v)
		if math.Abs(diff) > 2 {
			nv = float64(v) + diff*0.8
		}
		if nv < 0 {
			nv = 0
		}
		if nv > 255 {
			nv = 255
		}
		g := uint8(nv + 0.5)
		out.Pix[i*4+0] = g
		out.Pix[i*4+1] = g
		out.Pix[i*4+2] = g
		out.Pix[i*4+3] = 255
	}
	return out
}

// ComposeCanvas flattens the project at full export size and applies the
// preprocessing when enabled.
func ComposeCanvas(p *Project) *image.RGBA {
	flat := Flatten(p.Layers, CanvasPx)
	if p.Preproc {
		return PreprocessImage(flat)
	}
	return flat
}

func SavePNG(path string, img image.Image) error {
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	return png.Encode(f, img)
}
