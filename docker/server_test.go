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

	for _, entry := range entries {
		name := entry.Name()
		if !strings.HasSuffix(name, ".svg") {
			continue
		}

		partNumber := strings.SplitN(strings.TrimSuffix(name, ".svg"), "-", 2)[0]

		t.Run(partNumber, func(t *testing.T) {
			golden, err := os.ReadFile(filepath.Join(examplesDir, name))
			if err != nil {
				t.Fatalf("reading golden file %s: %v", name, err)
			}

			body, _ := json.Marshal(RenderRequest{PartNumber: partNumber})
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
				t.Errorf("output for part %s does not match golden file %s\ngot %d bytes, want %d bytes", partNumber, name, len(got), len(golden))
			}
		})
	}
}
