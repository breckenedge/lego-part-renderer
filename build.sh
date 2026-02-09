#!/bin/bash
set -e

echo "======================================"
echo "LEGO Part Renderer - Build Script"
echo "======================================"
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Check for render script
if [ ! -f "../scripts/render_part.py" ]; then
    echo "❌ render_part.py not found at ../scripts/render_part.py"
    exit 1
fi
echo "✓ render_part.py found"

# Create symlink if needed
mkdir -p scripts
if [ ! -f "scripts/render_part.py" ]; then
    ln -s ../../scripts/render_part.py scripts/render_part.py
    echo "✓ Created symlink to render_part.py"
fi

echo ""
echo "Building Docker image..."
echo "This will:"
echo "  1. Clone ImportLDraw addon from GitHub"
echo "  2. Download LDraw library (~40MB download, ~700MB extracted)"
echo "  3. Build Go server binary"
echo "  4. Install Blender and dependencies"
echo "  5. Create final image (~1.1GB)"
echo ""
echo "This may take 5-10 minutes on first build..."
echo ""

# Build with docker-compose
docker-compose build

echo ""
echo "======================================"
echo "✓ Build complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "  1. Start service:    docker-compose up -d"
echo "  2. Check health:     curl http://localhost:8080/health"
echo "  3. Test render:      curl -X POST http://localhost:8080/render -H 'Content-Type: application/json' -d '{\"partNumber\":\"3001\"}' -o test.svg"
echo "  4. View logs:        docker-compose logs -f"
echo "  5. Stop service:     docker-compose down"
echo ""
