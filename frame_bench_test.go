package main

import (
	"os"
	"testing"

	"github.com/egoist/mygo/ui"
)

// Frame-build benchmarks for the scrollable pages: they isolate the
// CPU-side cost of one full view rebuild (build + layout + diff), which
// caps the scroll frame rate when it grows past a few milliseconds.

func benchPage(b *testing.B, page int, withLayer bool) {
	a := newApp()
	a.page = page
	if withLayer {
		if _, err := os.Stat("/tmp/fixtures/canvas_user.png"); err == nil {
			if l, err := LoadLayer("/tmp/fixtures/canvas_user.png"); err == nil {
				a.proj.Layers = append(a.proj.Layers, l)
				a.proj.Sel = 0
			}
		}
	}
	tt := ui.NewTester(a.view, 1320, 860)
	tt.Frame()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		tt.Frame()
	}
}

func BenchmarkHomePageFrame(b *testing.B)   { benchPage(b, 0, false) }
func BenchmarkDesignPageFrame(b *testing.B) { benchPage(b, 1, true) }
func BenchmarkCalibPageFrame(b *testing.B)  { benchPage(b, 2, false) }
func BenchmarkExportPageFrame(b *testing.B) { benchPage(b, 4, true) }
