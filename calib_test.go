package main

import (
	"math"
	"os"
	"testing"
)

// The fixtures under testdata/ are trimmed copies of the real disc-probe
// outputs from the 2026-11-09 GX40N calibration run.

func TestParseTimingSummary(t *testing.T) {
	b, err := os.ReadFile("testdata/timing-summary.json")
	if err != nil {
		t.Fatal(err)
	}
	r, err := parseTimingSummary(b)
	if err != nil {
		t.Fatal(err)
	}
	if r.Mode != "CAV" {
		t.Errorf("mode = %q, want CAV", r.Mode)
	}
	if len(r.Zones) != 3 {
		t.Fatalf("zones = %d, want 3", len(r.Zones))
	}
	if math.Abs(r.Zones[0].RPM-4750.48) > 0.01 {
		t.Errorf("zone0 rpm = %v, want 4750.48", r.Zones[0].RPM)
	}
	if r.Drive != "HL-DT-ST DVDRW  GX40N" {
		t.Errorf("drive = %q", r.Drive)
	}
}

func TestParseGeoSummary(t *testing.T) {
	b, err := os.ReadFile("testdata/geo-summary.json")
	if err != nil {
		t.Fatal(err)
	}
	g, err := parseGeoSummary(b)
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(g.R0MM-24.17331443619965) > 1e-9 {
		t.Errorf("r0 = %v", g.R0MM)
	}
	if math.Abs(g.PitchUm-0.7340611201663617) > 1e-9 {
		t.Errorf("pitch = %v", g.PitchUm)
	}
	if math.Abs(g.Chi2-2.6828496540097455) > 1e-9 {
		t.Errorf("chi2 = %v", g.Chi2)
	}
	if g.SpanMM != [2]float64{25.833, 54.178} {
		t.Errorf("span = %v", g.SpanMM)
	}
}

func TestParsePresetFile(t *testing.T) {
	b, err := os.ReadFile("testdata/preset.json")
	if err != nil {
		t.Fatal(err)
	}
	p, err := parsePresetFile(b)
	if err != nil {
		t.Fatal(err)
	}
	if p.TotalSectors != 2298336 {
		t.Errorf("sectors = %d", p.TotalSectors)
	}
	if math.Abs(p.InnerMM-24.17331445423364) > 1e-9 {
		t.Errorf("inner = %v", p.InnerMM)
	}
	if math.Abs(p.OuterMM-57.912477520380705) > 1e-9 {
		t.Errorf("outer = %v", p.OuterMM)
	}
	if p.Name == "" {
		t.Error("preset name empty")
	}
}

func TestGeoVerdict(t *testing.T) {
	// Tonight's fit: sigma 0.214 is within the clean band, chi2 2.68 is
	// above 2, so the verdict must carry the chi2 note.
	g := &GeoResult{SigmaDeg: 0.214, Chi2: 2.68}
	v := geoVerdict(g)
	if v == "" || v[:len("测量精度达标，可用")] != "测量精度达标，可用" {
		t.Errorf("verdict = %q", v)
	}
	if got := geoVerdict(&GeoResult{SigmaDeg: 0.8, Chi2: 1.0}); got != "噪声太大，建议换速度或换盘重测" {
		t.Errorf("noisy verdict = %q", got)
	}
	if got := geoVerdict(&GeoResult{SigmaDeg: 0.4, Chi2: 1.0}); got != "能用，但噪声偏大" {
		t.Errorf("mid verdict = %q", got)
	}
}
