# LEGO Part Renderer

High-performance HTTP API for rendering LDraw LEGO parts as SVG line drawings.

**Built with Go + Blender Freestyle**

## Example Renders

<table>
  <tr>
    <td align="center"><img src="examples/3001-brick-2x4.svg" width="200"><br><b>3001</b><br>Brick 2x4</td>
    <td align="center"><img src="examples/3003-brick-2x2.svg" width="200"><br><b>3003</b><br>Brick 2x2</td>
    <td align="center"><img src="examples/3024-plate-1x1.svg" width="200"><br><b>3024</b><br>Plate 1x1</td>
  </tr>
  <tr>
    <td align="center"><img src="examples/3022-plate-2x2.svg" width="200"><br><b>3022</b><br>Plate 2x2</td>
    <td align="center"><img src="examples/3020-plate-2x4.svg" width="200"><br><b>3020</b><br>Plate 2x4</td>
    <td align="center"><img src="examples/3039-slope-2x2-45.svg" width="200"><br><b>3039</b><br>Slope 45° 2x2</td>
  </tr>
  <tr>
    <td align="center"><img src="examples/4286-slope-1x3-33.svg" width="200"><br><b>4286</b><br>Slope 33° 1x3</td>
    <td align="center"><img src="examples/3062b-round-brick-1x1.svg" width="200"><br><b>3062b</b><br>Round Brick 1x1</td>
    <td align="center"><img src="examples/6141-round-plate-1x1.svg" width="200"><br><b>6141</b><br>Round Plate 1x1</td>
  </tr>
  <tr>
    <td align="center"><img src="examples/3045-slope-2x2-double.svg" width="200"><br><b>3045</b><br>Double Slope 2x2</td>
    <td></td>
    <td></td>
  </tr>
</table>

## Quick Start

```bash
docker run -d -p 5346:5346 ghcr.io/breckenedge/lego-part-renderer:latest

# Render a part
curl -X POST http://localhost:5346/render \
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
  -p 5346:5346 \
  --restart unless-stopped \
  ghcr.io/breckenedge/lego-part-renderer:latest
```

### Docker Compose

```yaml
services:
  lego-renderer:
    image: ghcr.io/breckenedge/lego-part-renderer:latest
    ports:
      - "5346:5346"
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
| `PORT` | `5346` | HTTP port (5346 = LEGO on phone keypad) |
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
