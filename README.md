# LEGO Part Renderer

High-performance HTTP API for rendering LDraw LEGO parts as SVG line drawings.

**Built with Go + Blender Freestyle**

## Quick Start

```bash
docker run -d -p 8080:8080 ghcr.io/breckenedge/lego-part-renderer:latest

# Render a part
curl -X POST http://localhost:8080/render \
  -H "Content-Type: application/json" \
  -d '{"partNumber":"3001","thickness":2.0}' \
  --output part.svg
```

## Features

- ✅ **Fast Go server** - <5ms HTTP overhead, ~20MB memory
- ✅ **Professional rendering** - Blender Freestyle SVG output
- ✅ **12,000+ LEGO parts** - Complete LDraw library included
- ✅ **Zero config** - Auto-downloads dependencies during build
- ✅ **Production ready** - Health checks, metrics, Docker/K8s support
- ✅ **Stateless** - Easy to scale horizontally

## API

### POST /render

```json
{
  "partNumber": "3001",
  "thickness": 2.0
}
```

Returns SVG image with `Cache-Control: public, max-age=31536000, immutable`

### GET /health

```json
{
  "status": "healthy",
  "blender_available": true,
  "ldraw_available": true
}
```

### GET /metrics

```json
{
  "renders_total": 142,
  "errors": 3,
  "avg_render_duration_seconds": 6.45
}
```

## Architecture

```
Go HTTP Server ──▶ Blender subprocess ──▶ SVG output
  (8MB binary)      (Freestyle renderer)     (~50KB)
```

- **Go**: Handles HTTP, spawns Blender, returns SVG
- **Blender**: Imports LDraw part, renders with Freestyle
- **LDraw**: 12,000+ official LEGO part definitions

## Performance

- HTTP overhead: <5ms
- Render time: 5-10s (Blender)
- Memory: ~100MB idle, ~500MB per render
- Concurrent: Limited by CPU (1-2 cores per render)

## Deployment

### Docker

```bash
docker run -d \
  --name lego-renderer \
  -p 8080:8080 \
  --restart unless-stopped \
  ghcr.io/breckenedge/lego-part-renderer:latest
```

### Docker Compose

```yaml
services:
  lego-renderer:
    image: ghcr.io/breckenedge/lego-part-renderer:latest
    ports:
      - "8080:8080"
    restart: unless-stopped
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lego-renderer
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: lego-renderer
        image: ghcr.io/breckenedge/lego-part-renderer:latest
        resources:
          limits: { cpu: "2", memory: "768Mi" }
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | HTTP port |
| `LDRAW_PATH` | `/usr/share/ldraw/ldraw` | LDraw library path |

## Caching

Service is stateless. Cache at:
- **Nginx** (recommended) - HTTP proxy cache
- **CDN** - CloudFlare, Fastly, etc.
- **Client** - Application-level cache

## Building

```bash
git clone https://github.com/breckenedge/lego-part-renderer.git
cd lego-part-renderer
docker build -t lego-renderer .
```

Auto-downloads during build:
- ImportLDraw addon (GitHub)
- LDraw library (ldraw.org, ~700MB)

## License

MIT

## Credits

- LDraw: https://www.ldraw.org/
- ImportLDraw: https://github.com/TobyLobster/ImportLDraw  
- Blender: https://www.blender.org/
