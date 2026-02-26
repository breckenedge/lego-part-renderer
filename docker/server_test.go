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
		strokeColor string
	}

	params := map[string]partParams{
		"3001":  {3.0, "white", ""},
		"3003":  {2.5, "#e0e0e0", ""},
		"3020":  {1.5, "red", ""},
		"3022":  {1.0, "#4a90d9", ""},
		"3024":  {2.0, "currentColor", "cyan"},
		"3039":  {2.0, "white", ""},
		"3045":  {3.5, "#2ecc71", ""},
		"3062b": {1.5, "orange", ""},
		"4286":  {2.5, "white", ""},
		"4740":  {1.0, "#9b59b6", ""},
		"6133":  {4.0, "#e74c3c", ""},
		"6141":  {0.5, "yellow", ""},
	}

	for _, entry := range entries {
		name := entry.Name()
		if !strings.HasSuffix(name, ".svg") {
			continue
		}

		partNumber := strings.SplitN(strings.TrimSuffix(name, ".svg"), "-", 2)[0]
		p := params[partNumber]
		if p.thickness == 0 {
			p.thickness = 2.0
		}
		if p.fillColor == "" {
			p.fillColor = "white"
		}

		t.Run(partNumber, func(t *testing.T) {
			golden, err := os.ReadFile(filepath.Join(examplesDir, name))
			if err != nil {
				t.Fatalf("reading golden file %s: %v", name, err)
			}

			body, _ := json.Marshal(RenderRequest{PartNumber: partNumber, Thickness: p.thickness, FillColor: p.fillColor, StrokeColor: p.strokeColor})
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
