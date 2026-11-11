package main

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

// The bundled-pin guard: an external CLI that differs from the
// vendored official release must surface a note; the bundled copy
// itself and a byte-identical external copy must not.
func TestCLIPinWarning(t *testing.T) {
	bundled := t.TempDir()
	off := filepath.Join(bundled, "official")
	if err := os.MkdirAll(off, 0o755); err != nil {
		t.Fatal(err)
	}
	bundledCLI := filepath.Join(off, "disc-image-studio")
	if err := os.WriteFile(bundledCLI, []byte("bundled"), 0o755); err != nil {
		t.Fatal(err)
	}
	ext := filepath.Join(t.TempDir(), "disc-image-studio")
	if err := os.WriteFile(ext, []byte("bundled"), 0o755); err != nil {
		t.Fatal(err)
	}
	sum, err := sha256File(ext)
	if err != nil {
		t.Fatal(err)
	}
	ver := fmt.Sprintf(`{"version":"v-test","binarySha256":%q}`, sum)
	if err := os.WriteFile(filepath.Join(off, "VERSION.json"), []byte(ver), 0o644); err != nil {
		t.Fatal(err)
	}

	if w := cliPinWarning(bundled, bundledCLI); w != "" {
		t.Errorf("bundled copy: got warning %q, want none", w)
	}
	if w := cliPinWarning(bundled, ext); w != "" {
		t.Errorf("identical external copy: got warning %q, want none", w)
	}
	if err := os.WriteFile(ext, []byte("different build"), 0o755); err != nil {
		t.Fatal(err)
	}
	if w := cliPinWarning(bundled, ext); w == "" {
		t.Error("diverged external copy: got no warning, want one")
	}
	if w := cliPinWarning("", ext); w != "" {
		t.Errorf("no bundle: got warning %q, want none", w)
	}
}

func TestFirstExisting(t *testing.T) {
	hit := filepath.Join(t.TempDir(), "here")
	if err := os.WriteFile(hit, nil, 0o644); err != nil {
		t.Fatal(err)
	}
	miss := filepath.Join(t.TempDir(), "missing")
	if got := firstExisting(miss, hit); got != hit {
		t.Errorf("got %q, want the existing path %q", got, hit)
	}
	if got := firstExisting(miss, miss); got != miss {
		t.Errorf("got %q, want the fallback %q", got, miss)
	}
}
