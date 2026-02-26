package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

// Configuration from environment
var (
	ldrawPath    = getEnv("LDRAW_PATH", "/usr/share/ldraw/ldraw")
	renderScript = "/app/render_part.py"
	port         = getEnv("PORT", "8080")
)

// Metrics
type Metrics struct {
	sync.RWMutex
	RendersTotal       int64
	Errors             int64
	RenderDurationSum  float64
	RenderDurationNano int64
}

var metrics = &Metrics{}

// Request/Response types
type RenderRequest struct {
	PartNumber      string     `json:"partNumber"`
	Thickness       float64    `json:"thickness"`
	FillColor       string     `json:"fillColor"`
	StrokeColor     string     `json:"strokeColor"`
	CameraLatitude  *float64   `json:"cameraLatitude"`
	CameraLongitude *float64   `json:"cameraLongitude"`
	ResolutionX     *int       `json:"resolutionX"`
	ResolutionY     *int       `json:"resolutionY"`
	Padding         *float64   `json:"padding"`
	CreaseAngle     *float64   `json:"creaseAngle"`
	EdgeTypes       *EdgeTypes `json:"edgeTypes"`
}

type EdgeTypes struct {
	Silhouette       *bool `json:"silhouette"`
	Crease           *bool `json:"crease"`
	Border           *bool `json:"border"`
	Contour          *bool `json:"contour"`
	ExternalContour  *bool `json:"externalContour"`
	EdgeMark         *bool `json:"edgeMark"`
	MaterialBoundary *bool `json:"materialBoundary"`
}

type HealthResponse struct {
	Status              string `json:"status"`
	BlenderAvailable    bool   `json:"blender_available"`
	LDrawAvailable      bool   `json:"ldraw_available"`
	TempDirWritable     bool   `json:"temp_dir_writable"`
}

type MetricsResponse struct {
	RendersTotal           int64   `json:"renders_total"`
	Errors                 int64   `json:"errors"`
	AvgRenderDurationSecs  float64 `json:"avg_render_duration_seconds"`
}

type ErrorResponse struct {
	Error  string `json:"error"`
	Detail string `json:"detail,omitempty"`
}

func main() {
	log.Printf("Starting LEGO Part Renderer Service")
	log.Printf("LDraw library: %s", ldrawPath)
	log.Printf("Render script: %s", renderScript)

	http.HandleFunc("/", handleRoot)
	http.HandleFunc("/render", handleRender)
	http.HandleFunc("/health", handleHealth)
	http.HandleFunc("/metrics", handleMetrics)

	addr := ":" + port
	log.Printf("Server listening on %s", addr)
	if err := http.ListenAndServe(addr, logRequest(http.DefaultServeMux)); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}

// Logging middleware
func logRequest(handler http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		handler.ServeHTTP(w, r)
		log.Printf("%s %s %s", r.Method, r.URL.Path, time.Since(start))
	})
}

// Root endpoint
func handleRoot(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}

	response := map[string]interface{}{
		"service": "LEGO Part Renderer",
		"version": "1.0.0",
		"endpoints": map[string]string{
			"POST /render":  "Render a part as SVG",
			"GET /health":   "Health check",
			"GET /metrics":  "Service metrics",
		},
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// Render endpoint
func handleRender(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		sendError(w, http.StatusMethodNotAllowed, "Method not allowed", "")
		return
	}

	// Parse request
	var req RenderRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		sendError(w, http.StatusBadRequest, "Invalid JSON", err.Error())
		return
	}

	// Validate
	if req.PartNumber == "" {
		sendError(w, http.StatusBadRequest, "partNumber is required", "")
		return
	}

	if req.Thickness == 0 {
		req.Thickness = 2.0
	}
	if req.Thickness < 0.5 || req.Thickness > 20.0 {
		sendError(w, http.StatusBadRequest, "thickness must be between 0.5 and 20.0", "")
		return
	}

	if req.FillColor == "" {
		req.FillColor = "white"
	}

	if req.StrokeColor == "" {
		req.StrokeColor = "currentColor"
	}

	// Apply defaults for optional fields
	cameraLat := 30.0
	if req.CameraLatitude != nil {
		cameraLat = *req.CameraLatitude
	}
	cameraLon := 45.0
	if req.CameraLongitude != nil {
		cameraLon = *req.CameraLongitude
	}
	resX := 1024
	if req.ResolutionX != nil {
		resX = *req.ResolutionX
	}
	resY := 1024
	if req.ResolutionY != nil {
		resY = *req.ResolutionY
	}
	padding := 0.03
	if req.Padding != nil {
		padding = *req.Padding
	}
	creaseAngle := 135.0
	if req.CreaseAngle != nil {
		creaseAngle = *req.CreaseAngle
	}

	// Validate ranges
	if cameraLat < -90 || cameraLat > 90 {
		sendError(w, http.StatusBadRequest, "cameraLatitude must be between -90 and 90", "")
		return
	}
	if cameraLon < -360 || cameraLon > 360 {
		sendError(w, http.StatusBadRequest, "cameraLongitude must be between -360 and 360", "")
		return
	}
	if resX < 64 || resX > 4096 {
		sendError(w, http.StatusBadRequest, "resolutionX must be between 64 and 4096", "")
		return
	}
	if resY < 64 || resY > 4096 {
		sendError(w, http.StatusBadRequest, "resolutionY must be between 64 and 4096", "")
		return
	}
	if padding < 0 || padding > 0.5 {
		sendError(w, http.StatusBadRequest, "padding must be between 0 and 0.5", "")
		return
	}
	if creaseAngle < 0 || creaseAngle > 180 {
		sendError(w, http.StatusBadRequest, "creaseAngle must be between 0 and 180", "")
		return
	}

	// Build edge types string
	edgeTypes := buildEdgeTypes(req.EdgeTypes)


	start := time.Now()

	// Find part file
	partFile := findPartFile(req.PartNumber)
	if partFile == "" {
		log.Printf("Part not found: %s", req.PartNumber)
		metrics.Lock()
		metrics.Errors++
		metrics.Unlock()
		sendError(w, http.StatusNotFound, "Part not found", fmt.Sprintf("Part %s not found in LDraw library", req.PartNumber))
		return
	}

	// Create temp file for output
	tmpFile, err := os.CreateTemp("", "render-*.svg")
	if err != nil {
		log.Printf("Failed to create temp file: %v", err)
		metrics.Lock()
		metrics.Errors++
		metrics.Unlock()
		sendError(w, http.StatusInternalServerError, "Failed to create temp file", err.Error())
		return
	}
	outputPath := tmpFile.Name()
	tmpFile.Close()
	defer os.Remove(outputPath)

	// Render with Blender
	log.Printf("Rendering %s (thickness=%.1f, camera=%.1f/%.1f, res=%dx%d, padding=%.3f, crease=%.1f, edges=%s, fill=%s, stroke=%s)",
		req.PartNumber, req.Thickness, cameraLat, cameraLon, resX, resY, padding, creaseAngle, edgeTypes, req.FillColor, req.StrokeColor)
	renderStart := time.Now()

	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx,
		"blender",
		"--background",
		"--python", renderScript,
		"--",
		partFile,
		outputPath,
		ldrawPath,
		fmt.Sprintf("%.1f", req.Thickness),
		req.FillColor,
		fmt.Sprintf("%f", cameraLat),
		fmt.Sprintf("%f", cameraLon),
		strconv.Itoa(resX),
		strconv.Itoa(resY),
		fmt.Sprintf("%f", padding),
		fmt.Sprintf("%f", creaseAngle),
		edgeTypes,
		req.StrokeColor,
	)

	var stderr bytes.Buffer
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		errMsg := stderr.String()
		if ctx.Err() == context.DeadlineExceeded {
			log.Printf("Render timeout for %s", req.PartNumber)
			metrics.Lock()
			metrics.Errors++
			metrics.Unlock()
			sendError(w, http.StatusInternalServerError, "Rendering timed out", fmt.Sprintf("Part %s", req.PartNumber))
			return
		}

		log.Printf("Render failed for %s: %s", req.PartNumber, errMsg)
		metrics.Lock()
		metrics.Errors++
		metrics.Unlock()
		sendError(w, http.StatusInternalServerError, "Rendering failed", errMsg)
		return
	}

	renderDuration := time.Since(renderStart)
	log.Printf("Rendered %s in %.2fs", req.PartNumber, renderDuration.Seconds())

	// Update metrics
	metrics.Lock()
	metrics.RendersTotal++
	metrics.RenderDurationSum += renderDuration.Seconds()
	metrics.RenderDurationNano += renderDuration.Nanoseconds()
	metrics.Unlock()

	// Read SVG content
	svgContent, err := os.ReadFile(outputPath)
	if err != nil {
		log.Printf("Failed to read rendered SVG: %v", err)
		metrics.Lock()
		metrics.Errors++
		metrics.Unlock()
		sendError(w, http.StatusInternalServerError, "Failed to read output", err.Error())
		return
	}

	totalDuration := time.Since(start)
	log.Printf("Total request duration: %.2fs", totalDuration.Seconds())

	// Return SVG
	w.Header().Set("Content-Type", "image/svg+xml")
	w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
	w.Header().Set("X-Render-Duration", fmt.Sprintf("%.2fs", renderDuration.Seconds()))
	w.Write(svgContent)
}

// Health check endpoint
func handleHealth(w http.ResponseWriter, r *http.Request) {
	// Check Blender
	blenderAvailable := false
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, "blender", "--version")
	if err := cmd.Run(); err == nil {
		blenderAvailable = true
	}

	// Check LDraw library
	ldrawAvailable := false
	partsDir := filepath.Join(ldrawPath, "parts")
	if _, err := os.Stat(partsDir); err == nil {
		ldrawAvailable = true
	}

	// Check temp directory
	tempDirWritable := false
	tmpFile, err := os.CreateTemp("", "healthcheck-*")
	if err == nil {
		tmpFile.Close()
		os.Remove(tmpFile.Name())
		tempDirWritable = true
	}

	allHealthy := blenderAvailable && ldrawAvailable && tempDirWritable
	status := "unhealthy"
	if allHealthy {
		status = "healthy"
	}

	response := HealthResponse{
		Status:           status,
		BlenderAvailable: blenderAvailable,
		LDrawAvailable:   ldrawAvailable,
		TempDirWritable:  tempDirWritable,
	}

	w.Header().Set("Content-Type", "application/json")
	if !allHealthy {
		w.WriteHeader(http.StatusServiceUnavailable)
	}
	json.NewEncoder(w).Encode(response)
}

// Metrics endpoint
func handleMetrics(w http.ResponseWriter, r *http.Request) {
	metrics.RLock()
	defer metrics.RUnlock()

	avgDuration := 0.0
	if metrics.RendersTotal > 0 {
		avgDuration = metrics.RenderDurationSum / float64(metrics.RendersTotal)
	}

	response := MetricsResponse{
		RendersTotal:          metrics.RendersTotal,
		Errors:                metrics.Errors,
		AvgRenderDurationSecs: avgDuration,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// Build comma-separated edge types string from request
func buildEdgeTypes(et *EdgeTypes) string {
	// Defaults: silhouette, crease, border enabled; rest disabled
	silhouette := true
	crease := true
	border := true
	contour := false
	externalContour := false
	edgeMark := false
	materialBoundary := false

	if et != nil {
		if et.Silhouette != nil {
			silhouette = *et.Silhouette
		}
		if et.Crease != nil {
			crease = *et.Crease
		}
		if et.Border != nil {
			border = *et.Border
		}
		if et.Contour != nil {
			contour = *et.Contour
		}
		if et.ExternalContour != nil {
			externalContour = *et.ExternalContour
		}
		if et.EdgeMark != nil {
			edgeMark = *et.EdgeMark
		}
		if et.MaterialBoundary != nil {
			materialBoundary = *et.MaterialBoundary
		}
	}

	var types []string
	if silhouette {
		types = append(types, "silhouette")
	}
	if crease {
		types = append(types, "crease")
	}
	if border {
		types = append(types, "border")
	}
	if contour {
		types = append(types, "contour")
	}
	if externalContour {
		types = append(types, "external_contour")
	}
	if edgeMark {
		types = append(types, "edge_mark")
	}
	if materialBoundary {
		types = append(types, "material_boundary")
	}

	if len(types) == 0 {
		return "none"
	}
	return strings.Join(types, ",")
}

// Find part file in LDraw library
func findPartFile(partNumber string) string {
	variations := []string{
		partNumber + ".dat",
		strings.ToLower(partNumber) + ".dat",
		strings.ToUpper(partNumber) + ".dat",
	}

	// Check parts/ directory
	partsDir := filepath.Join(ldrawPath, "parts")
	for _, variant := range variations {
		path := filepath.Join(partsDir, variant)
		if _, err := os.Stat(path); err == nil {
			return path
		}
	}

	// Check p/ directory (primitives)
	pDir := filepath.Join(ldrawPath, "p")
	for _, variant := range variations {
		path := filepath.Join(pDir, variant)
		if _, err := os.Stat(path); err == nil {
			return path
		}
	}

	return ""
}

// Helper: send JSON error response
func sendError(w http.ResponseWriter, statusCode int, message, detail string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(statusCode)

	response := ErrorResponse{
		Error:  message,
		Detail: detail,
	}
	json.NewEncoder(w).Encode(response)
}

// Helper: get environment variable with default
func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}
