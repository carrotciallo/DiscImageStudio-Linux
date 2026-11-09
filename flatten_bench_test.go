package main

import (
	"image"
	"image/color"
	"testing"
)

func benchBigLayer() *Layer {
	img := image.NewRGBA(image.Rect(0, 0, 6000, 4000))
	for y := 0; y < 4000; y += 7 {
		for x := 0; x < 6000; x += 7 {
			img.Set(x, y, color.RGBA{uint8(x % 251), uint8(y % 241), 128, 255})
		}
	}
	return &Layer{img: img, imgW: 6000, imgH: 4000, X: 5, Y: -8, HeightMM: 100, Rotation: 25}
}

func BenchmarkFlattenLarge1024(b *testing.B) {
	layers := []*Layer{benchBigLayer()}
	Flatten(layers, 1024)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		Flatten(layers, 1024)
	}
}

func BenchmarkFlattenPreviewCrisp(b *testing.B) {
	layers := []*Layer{benchBigLayer()}
	flatten(layers, 1024, true, false)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		flatten(layers, 1024, true, false)
	}
}

func BenchmarkFlattenPreviewFast(b *testing.B) {
	layers := []*Layer{benchBigLayer()}
	flatten(layers, 512, true, true)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		flatten(layers, 512, true, true)
	}
}

func BenchmarkFlattenPreviewFast384(b *testing.B) {
	layers := []*Layer{benchBigLayer()}
	flatten(layers, 384, true, true)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		flatten(layers, 384, true, true)
	}
}
