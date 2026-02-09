#!/bin/bash
set -e

echo "======================================"
echo "LEGO Part Renderer - Test Script"
echo "======================================"
echo ""

SERVICE_URL="http://localhost:5346"

# Check if service is running
echo "1. Checking if service is running..."
if ! curl -sf "$SERVICE_URL/" > /dev/null; then
    echo "❌ Service is not running"
    echo ""
    echo "Please start the service first:"
    echo "  docker-compose up -d"
    echo ""
    exit 1
fi
echo "✓ Service is running"
echo ""

# Health check
echo "2. Health check..."
HEALTH=$(curl -s "$SERVICE_URL/health")
echo "$HEALTH" | jq .
STATUS=$(echo "$HEALTH" | jq -r .status)

if [ "$STATUS" != "healthy" ]; then
    echo "❌ Service is unhealthy"
    echo "Check docker-compose logs for details"
    exit 1
fi
echo "✓ Service is healthy"
echo ""

# Test render
echo "3. Testing part render (part 3001)..."
echo "   This will take 5-10 seconds (Blender initialization + rendering)..."
START=$(date +%s)

curl -X POST "$SERVICE_URL/render" \
    -H "Content-Type: application/json" \
    -d '{"partNumber":"3001","thickness":2.0}' \
    -o test-3001.svg \
    -w "\n   HTTP Status: %{http_code}\n   Time: %{time_total}s\n" \
    -s

END=$(date +%s)
DURATION=$((END - START))

if [ ! -f "test-3001.svg" ]; then
    echo "❌ Render failed - no output file"
    exit 1
fi

# Check if it's actually SVG
if ! file test-3001.svg | grep -q "SVG"; then
    echo "❌ Output is not a valid SVG file"
    cat test-3001.svg
    exit 1
fi

SIZE=$(wc -c < test-3001.svg)
echo "✓ Render successful"
echo "   Output: test-3001.svg (${SIZE} bytes, ${DURATION}s total)"
echo ""

# Test metrics
echo "4. Checking metrics..."
METRICS=$(curl -s "$SERVICE_URL/metrics")
echo "$METRICS" | jq .
echo ""

# Test another part
echo "5. Testing another part (part 3002)..."
curl -X POST "$SERVICE_URL/render" \
    -H "Content-Type: application/json" \
    -d '{"partNumber":"3002","thickness":3.0}' \
    -o test-3002.svg \
    -w "   HTTP Status: %{http_code}\n   Time: %{time_total}s\n" \
    -s

if [ ! -f "test-3002.svg" ]; then
    echo "❌ Render failed"
    exit 1
fi
echo "✓ Render successful"
echo ""

# Test invalid part
echo "6. Testing invalid part (should return 404)..."
HTTP_CODE=$(curl -X POST "$SERVICE_URL/render" \
    -H "Content-Type: application/json" \
    -d '{"partNumber":"INVALID99999"}' \
    -w "%{http_code}" \
    -s -o /dev/null)

if [ "$HTTP_CODE" -eq 404 ]; then
    echo "✓ Correctly returned 404 for invalid part"
else
    echo "❌ Expected 404, got $HTTP_CODE"
fi
echo ""

# Final metrics
echo "7. Final metrics..."
curl -s "$SERVICE_URL/metrics" | jq .
echo ""

echo "======================================"
echo "✓ All tests passed!"
echo "======================================"
echo ""
echo "Generated files:"
ls -lh test-*.svg 2>/dev/null || true
echo ""
echo "You can open the SVG files to verify rendering:"
echo "  firefox test-3001.svg"
echo "  # or"
echo "  open test-3001.svg"
echo ""
