#!/bin/bash
# Build and run the Pretalx Schedule Preview container
# Usage: ./run.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
IMAGE_NAME="ef-schedule-preview"
CONTAINER_NAME="ef-schedule-preview"

# Copy pretalx_client.py into web/ for the Docker build context
cp "$PROJECT_DIR/pretalx_client.py" "$SCRIPT_DIR/pretalx_client.py"

# Load .env file if it exists and let bash evaluate it (to strip quotes)
if [ -f "$PROJECT_DIR/.env" ]; then
    echo "Sourcing environment from .env"
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# Stop existing container if running
podman rm -f "$CONTAINER_NAME" 2>/dev/null || true

# Build the image
echo "Building container image..."
podman build -t "$IMAGE_NAME" "$SCRIPT_DIR"

# Run the container
echo "Starting container on port 8089..."
podman run --rm -d \
    --name "$CONTAINER_NAME" \
    -p 8089:8089 \
    -e PRETALX_URL="$PRETALX_URL" \
    -e PRETALX_APIKEY="$PRETALX_APIKEY" \
    -e PRETALX_EVENT_SLUG="${PRETALX_EVENT_SLUG:-eurofurence-30-2026}" \
    -e SCHEDULE_VERSION="${SCHEDULE_VERSION:-wip}" \
    -e BASE_PATH="${BASE_PATH:-/ef-schedule-preview}" \
    -e EF_SCHEDULE_IMPRINT="${EF_SCHEDULE_IMPRINT}" \
    -e EF_SCHEDULE_PRIVACY="${EF_SCHEDULE_PRIVACY}" \
    "$IMAGE_NAME"

echo ""
echo "Container '$CONTAINER_NAME' started."
echo "Access at: http://shell01.nest:8089/ef-schedule-preview/"
echo ""
echo "Logs: podman logs -f $CONTAINER_NAME"
echo "Stop: podman stop $CONTAINER_NAME"
