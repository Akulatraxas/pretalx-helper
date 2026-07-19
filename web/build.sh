#!/bin/bash
# Build and run the Pretalx Schedule Preview container
# Usage: ./run.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE_NAME="ef-schedule-preview"

# Copy pretalx_client.py into web/ for the Docker build context
cp "$PROJECT_DIR/pretalx_client.py" "$SCRIPT_DIR/pretalx_client.py"

# Build the image
echo "Building container image..."
podman build -t "$IMAGE_NAME" "$SCRIPT_DIR"
