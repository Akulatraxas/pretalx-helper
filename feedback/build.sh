#!/usr/bin/env bash
# build.sh — Build the Feedback Viewer container.
#
# Usage:
#   cd feedback/
#   ./build.sh

set -euo pipefail

IMAGE_TAG="ef-feedback:latest"

# --- Prepare build context ---
echo "→ Copying pretalx_client.py from parent directory…"
cp "$(dirname "$0")/../pretalx_client.py" "$(dirname "$0")/pretalx_client.py"

echo "→ Copying fonts from web/static/fonts/…"
mkdir -p "$(dirname "$0")/fonts"
cp -r "$(dirname "$0")/../web/static/fonts/." "$(dirname "$0")/fonts/"

# --- Build ---
echo "→ Building image '${IMAGE_TAG}'…"
podman build \
    -t "${IMAGE_TAG}" \
    -f "$(dirname "$0")/Dockerfile" \
    "$(dirname "$0")"
