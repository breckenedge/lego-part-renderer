package main

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func blenderAvailable() bool {
	err := exec.Command("blender", "--version").Run()
	return err == nil
}

func TestRenderGoldenFiles(t *testing.T) {
	if !blenderAvailable() {
		t.Skip("blender not available")
	}

	examplesDir := filepath.Join("..", "examples")
	entries, err := os.ReadDir(examplesDir)
	if err != nil {
		t.Fatalf("reading examples dir: %v", err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/render", handleRender)
	srv := httptest.NewServer(mux)
	defer srv.Close()

	type partParams struct {
		thickness   float64
		fillColor   string
		fillOpacity float64 // 0 uses server default (1.0)
	}

	// Map of filename (without .svg) to render params.
	params := map[string]partParams{
		"3001-brick-2x4":                    {3.0, "white", 0},
		"3003-brick-2x2":                    {2.5, "#e0e0e0", 0},
		"3020-plate-2x4":                    {1.5, "red", 0},
		"3022-plate-2x2":                    {1.0, "#4a90d9", 0},
		"3024-plate-1x1":                    {0.5, "currentColor", 0},
		"3039-slope-2x2-45":                 {2.0, "white", 0},
		"3045-slope-2x2-double":             {3.5, "#2ecc71", 0},
		"3062b-round-brick-1x1":             {1.5, "orange", 0},
		"4286-slope-1x3-33":                 {2.5, "white", 0},
		"4740-dish-2x2-inverted":            {1.0, "#9b59b6", 0},
		"4740-dish-2x2-inverted-translucent": {1.0, "#9b59b6", 0.5},
		"6133-dragon-wing":                  {4.0, "#e74c3c", 0},
		"6141-round-plate-1x1":              {0.5, "yellow", 0},
	}

	for _, entry := range entries {
		name := entry.Name()
		if !strings.HasSuffix(name, ".svg") {
			continue
		}

		fileKey := strings.TrimSuffix(name, ".svg")
		p, ok := params[fileKey]
		if !ok {
			t.Logf("Skipping %s: not in golden file test params", name)
			continue
		}

		partNumber := strings.SplitN(fileKey, "-", 2)[0]

		if p.thickness == 0 {
			p.thickness = 2.0
		}
		if p.fillColor == "" {
			p.fillColor = "white"
		}
		fillOpacity := p.fillOpacity
		if fillOpacity == 0 {
			fillOpacity = 1.0
		}

		t.Run(fileKey, func(t *testing.T) {
			golden, err := os.ReadFile(filepath.Join(examplesDir, name))
			if err != nil {
				t.Fatalf("reading golden file %s: %v", name, err)
			}

			body, _ := json.Marshal(RenderRequest{PartNumber: partNumber, Thickness: p.thickness, FillColor: p.fillColor, FillOpacity: &fillOpacity})
			resp, err := http.Post(srv.URL+"/render", "application/json", bytes.NewReader(body))
			if err != nil {
				t.Fatalf("POST /render: %v", err)
			}
			defer resp.Body.Close()

			if resp.StatusCode != http.StatusOK {
				t.Fatalf("expected 200, got %d", resp.StatusCode)
			}

			got, err := io.ReadAll(resp.Body)
			if err != nil {
				t.Fatalf("reading response body: %v", err)
			}

			if !bytes.Equal(got, golden) {
				t.Fatalf("output for part %s does not match golden file %s\ngot %d bytes, want %d bytes", partNumber, name, len(got), len(golden))
			}
		})
	}
}
