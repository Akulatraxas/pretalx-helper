#!/usr/bin/env bash
# build.sh — Build the Operations Resource Manager container.
#
# Usage:
#   cd operations/
#   ./run.sh
#
# Access at: http://shell01.nest:8090/ef-operations/

set -euo pipefail

CONTAINER_NAME="ef-operations"
IMAGE_TAG="ef-operations:latest"

# --- Prepare build context ---
echo "→ Copying pretalx_client.py from parent directory…"
cp "$(dirname "$0")/../pretalx_client.py" "$(dirname "$0")/pretalx_client.py"

# --- Build ---
echo "→ Building image '${IMAGE_TAG}'…"
podman build \
    -t "${IMAGE_TAG}" \
    -f "$(dirname "$0")/Dockerfile" \
    "$(dirname "$0")"

