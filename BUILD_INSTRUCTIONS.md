# Build Instructions - Go Version

## What's Different

This service is now built with **Go** instead of Python:

### Why Go?

- **10-100x faster** HTTP serving compared to Python/Node.js
- **Lower memory**: ~20MB baseline vs ~50MB (Node.js) or ~80MB (Python)
- **Better concurrency**: Goroutines handle multiple simultaneous renders efficiently
- **Single static binary**: No runtime dependencies, easier deployment
- **Fast startup**: No interpreter initialization

### Performance Comparison

| Metric | Python (FastAPI) | Node.js (Express) | Go (stdlib) |
|--------|------------------|-------------------|-------------|
| Baseline memory | ~80MB | ~50MB | ~20MB |
| Request/sec | ~5,000 | ~15,000 | ~50,000 |
| Latency (p99) | ~50ms | ~20ms | ~5ms |
| Startup time | ~2s | ~1s | ~100ms |

*Note: These numbers are for the HTTP server only. Blender rendering (5-10s) dominates total request time.*

## Prerequisites

**None!** Everything is downloaded automatically during build.

### What Gets Auto-Downloaded

✅ **ImportLDraw addon** - Cloned from GitHub during build
✅ **LDraw library** - Downloaded from ldraw.org during build

The multi-stage build:
1. Clones ImportLDraw addon from GitHub
2. Downloads `complete.zip` (~40MB compressed, ~700MB uncompressed)
3. Extracts to `/usr/share/ldraw/ldraw`
4. Copies everything into final image

**Zero manual steps required!**

## Building

### Quick Start

```bash
cd docker-service-poc

# Build image (downloads LDraw automatically)
docker-compose build

# Start service
docker-compose up -d

# Check health
curl http://localhost:8080/health

# Render a part
curl -X POST http://localhost:8080/render \
  -H "Content-Type: application/json" \
  -d '{"partNumber":"3001","thickness":2.0}' \
  --output part-3001.svg

# View metrics
curl http://localhost:8080/metrics

# Stop service
docker-compose down
```

### Manual Build

```bash
# Build only (downloads ImportLDraw and LDraw automatically)
docker build -t lego-renderer .

# Run container
docker run -d \
  --name lego-renderer \
  -p 8080:8080 \
  -e PORT=8080 \
  lego-renderer

# Check logs
docker logs -f lego-renderer

# Stop
docker stop lego-renderer
docker rm lego-renderer
```

## Multi-Stage Build Explained

The Dockerfile uses a **multi-stage build** for efficiency:

### Stage 1: Builder (golang:1.22-alpine)
- Downloads LDraw library from ldraw.org
- Builds Go server as static binary
- Small intermediate layer

### Stage 2: Runtime (ubuntu:22.04)
- Installs Blender (only runtime needed)
- Copies LDraw library from builder
- Copies Go binary from builder
- No build tools in final image

**Result:** Optimized image with only runtime dependencies.

## Image Size

```
REPOSITORY       TAG       SIZE
lego-renderer    latest    ~1.1GB
  ├─ Blender             ~450MB
  ├─ LDraw library       ~700MB
  ├─ Ubuntu base         ~80MB
  ├─ Python3 (for Blender) ~50MB
  └─ Go binary           ~8MB
```

The Go binary is tiny compared to the overall image!

## Directory Structure

```
docker-service-poc/
├── Dockerfile              # Multi-stage build
├── docker-compose.yml      # Orchestration
├── go.mod                  # Go module file (minimal)
├── .dockerignore           # Build context exclusions
├── docker/
│   └── server.go           # Go HTTP server
├── scripts/
│   └── render_part.py      # Blender rendering script (symlink to ../scripts/)
├── ImportLDraw/            # Git clone from GitHub
└── BUILD_INSTRUCTIONS.md   # This file
```

## Testing the Build

After building, test each component:

### 1. Health Check
```bash
curl http://localhost:8080/health

# Expected response:
# {
#   "status": "healthy",
#   "blender_available": true,
#   "ldraw_available": true,
#   "temp_dir_writable": true
# }
```

### 2. Render a Part
```bash
curl -X POST http://localhost:8080/render \
  -H "Content-Type: application/json" \
  -d '{"partNumber":"3001","thickness":2.0}' \
  -o test.svg

# Check output
file test.svg  # Should be: SVG Scalable Vector Graphics image
```

### 3. Check Metrics
```bash
curl http://localhost:8080/metrics

# Expected response:
# {
#   "renders_total": 1,
#   "errors": 0,
#   "avg_render_duration_seconds": 6.23
# }
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LDRAW_PATH` | `/usr/share/ldraw/ldraw` | LDraw library location |
| `PORT` | `8080` | HTTP server port |

## Troubleshooting

### Build fails downloading LDraw library

**Problem:** `wget` times out or fails

**Solution:** Check internet connectivity or use a mirror:
```dockerfile
# In Dockerfile, replace:
wget https://library.ldraw.org/library/updates/complete.zip

# With mirror:
wget https://www.ldraw.org/library/updates/complete.zip
```

### ImportLDraw addon clone fails

**Problem:** Build fails with "fatal: unable to access 'https://github.com/...'"

**Solution:** Check internet connectivity or use a specific commit:
```dockerfile
# In Dockerfile, replace:
RUN git clone --depth 1 https://github.com/TobyLobster/ImportLDraw.git /tmp/ImportLDraw

# With a specific commit/tag:
RUN git clone --depth 1 --branch v1.2.3 https://github.com/TobyLobster/ImportLDraw.git /tmp/ImportLDraw
```

### Blender addon not enabled

**Problem:** Rendering fails with "No module named 'ImportLDraw'"

**Solution:** The `render_part.py` script enables addons at runtime. Check that:
- ImportLDraw is in `/root/.config/blender/3.0/scripts/addons/ImportLDraw/`
- The script has these lines:
  ```python
  addon_utils.enable("ImportLDraw")
  addon_utils.enable("render_freestyle_svg", default_set=True, persistent=True)
  ```

### Health check fails

**Problem:** Container marked unhealthy

**Solution:** Check logs:
```bash
docker logs lego-renderer

# Common issues:
# - Blender not in PATH
# - LDraw library missing
# - Temp directory not writable
```

## Next Steps

1. ✅ Build and test locally
2. Integrate with main app using `scripts/http-client.js`
3. Deploy to cloud (AWS ECS, GCP Cloud Run, etc.)
4. Set up monitoring (Prometheus metrics)
5. Configure auto-scaling based on queue depth

## Performance Tips

### Increase Workers

Go's concurrency model handles multiple requests automatically. No need for worker processes like Python.

### Resource Limits

The bottleneck is **Blender rendering**, not the Go server. Set resources based on concurrent renders:

```yaml
# docker-compose.yml
deploy:
  resources:
    limits:
      cpus: '4'      # 2 concurrent renders (2 cores each)
      memory: 2G     # ~500MB per render + overhead
```

### Pre-warming

Pre-render common parts to populate nginx cache:

```bash
# prewarm.sh
PARTS="3001 3002 3003 3004 3005"
for PART in $PARTS; do
  curl -X POST http://localhost:8080/render \
    -H "Content-Type: application/json" \
    -d "{\"partNumber\":\"$PART\",\"thickness\":2.0}" \
    -o /dev/null -s
done
```

## License

Same as main project (MIT).
