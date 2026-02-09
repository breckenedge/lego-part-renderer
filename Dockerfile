# Multi-stage build for LEGO Part Renderer Service
# Stage 1: Download LDraw library, clone ImportLDraw addon, and build Go binary
FROM golang:1.22-alpine AS builder

# Install dependencies for downloading
RUN apk add --no-cache wget unzip git

# Download and extract LDraw library
RUN mkdir -p /tmp/ldraw && \
    cd /tmp/ldraw && \
    echo "Downloading LDraw library (complete.zip ~40MB)..." && \
    wget -q --show-progress https://library.ldraw.org/library/updates/complete.zip && \
    echo "Extracting LDraw library..." && \
    unzip -q complete.zip && \
    rm complete.zip

# Clone ImportLDraw addon
RUN git clone --depth 1 https://github.com/TobyLobster/ImportLDraw.git /tmp/ImportLDraw

# Build Go server
WORKDIR /build
COPY docker/server.go .

# Download dependencies and build static binary
RUN go mod init lego-renderer && \
    CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -ldflags '-s -w' -o server server.go

# Stage 2: Runtime image
FROM ubuntu:22.04

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install Blender and minimal dependencies
RUN apt-get update && apt-get install -y \
    blender \
    python3-pip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy LDraw library from builder stage
COPY --from=builder /tmp/ldraw/ldraw /usr/share/ldraw/ldraw

# Copy ImportLDraw addon from builder stage
RUN mkdir -p /root/.config/blender/3.0/scripts/addons
COPY --from=builder /tmp/ImportLDraw /root/.config/blender/3.0/scripts/addons/ImportLDraw/

# Install Freestyle SVG addon (should be bundled with Blender, but ensure it's enabled)
# The Python script will enable it at runtime

# Create application directory
WORKDIR /app

# Copy rendering script (from main project)
COPY scripts/render_part.py /app/render_part.py

# Copy Go server binary from builder
COPY --from=builder /build/server /app/server

# Set environment variables
ENV LDRAW_PATH=/usr/share/ldraw/ldraw
ENV PORT=5346

# Expose HTTP port (5346 = LEGO on phone keypad: L=5, E=3, G=4, O=6)
EXPOSE 5346

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5346/health || exit 1

# Run Go server
CMD ["/app/server"]
