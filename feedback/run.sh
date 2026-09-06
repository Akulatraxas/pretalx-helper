#!/usr/bin/env bash
# run.sh — Build and run the Feedback Viewer container.
#
# Usage:
#   cd feedback/
#   ./run.sh
#
# Access at: http://shell01.nest:8091/ef-feedback/

set -euo pipefail

CONTAINER_NAME="ef-feedback"
PORT="${PORT:-8091}"
IMAGE_TAG="ef-feedback:latest"
DATA_DIR="$HOME/ef-feedback-data"   # SQLite database storage

# --- Load .env from parent directory ---
# The .env uses quoted values, so we source it rather than using --env-file.
ENV_FILE="$(dirname "$0")/../.env"
if [[ -f "$ENV_FILE" ]]; then
    echo "→ Loading environment from $ENV_FILE"
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
else
    echo "⚠  Warning: $ENV_FILE not found. PRETALX_URL, PRETALX_APIKEY must be set manually."
fi

# Required variables
: "${PRETALX_URL:?PRETALX_URL must be set}"
: "${PRETALX_APIKEY:?PRETALX_APIKEY must be set}"
: "${PRETALX_EVENT_SLUG:?PRETALX_EVENT_SLUG must be set}"

# Defaults
SCHEDULE_VERSION="${SCHEDULE_VERSION:-latest}"
BASE_PATH="${BASE_PATH:-/ef-feedback}"
PRETALX_TIMEOUT="${PRETALX_TIMEOUT:-30}"

# ACL group IDs (required unless explicit development auth is enabled)
READ_GROUPS="${READ_GROUPS:-}"
WRITE_GROUPS="${WRITE_GROUPS:-}"
READ_GROUPS_FEEDBACK="${READ_GROUPS_FEEDBACK:-}"
WRITE_GROUPS_FEEDBACK="${WRITE_GROUPS_FEEDBACK:-}"

# Dev auth override (set these for local testing without oauth2-proxy)
DEV_AUTH_ENABLED="${DEV_AUTH_ENABLED:-false}"
DEV_AUTH_EMAIL="${DEV_AUTH_EMAIL:-}"
DEV_AUTH_USER="${DEV_AUTH_USER:-}"
DEV_AUTH_GROUPS="${DEV_AUTH_GROUPS:-}"

# --- Prepare build context ---
echo "→ Copying pretalx_client.py from parent directory…"
cp "$(dirname "$0")/../pretalx_client.py" "$(dirname "$0")/pretalx_client.py"

echo "→ Copying fonts from web/static/fonts/…"
mkdir -p "$(dirname "$0")/fonts"
cp -r "$(dirname "$0")/../web/static/fonts/." "$(dirname "$0")/fonts/"

# --- Stop and remove existing container ---
if podman ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "→ Stopping existing container '${CONTAINER_NAME}'…"
    podman stop "${CONTAINER_NAME}" 2>/dev/null || true
    podman rm   "${CONTAINER_NAME}" 2>/dev/null || true
fi

# --- Build ---
echo "→ Building image '${IMAGE_TAG}'…"
podman build \
    -t "${IMAGE_TAG}" \
    -f "$(dirname "$0")/Dockerfile" \
    "$(dirname "$0")"

# --- Data directory ---
mkdir -p "$DATA_DIR"
if [[ -d "$(dirname "$0")/data" ]] && [[ ! -d "$DATA_DIR/feedback" ]]; then
    echo "→ Populating data from local data directory into $DATA_DIR…"
    cp -rn "$(dirname "$0")/data/." "$DATA_DIR/"
fi
echo "→ Data directory at: $DATA_DIR"

# --- Run ---
echo "→ Starting container '${CONTAINER_NAME}' on port ${PORT}…"
podman run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    --userns=keep-id:uid=10001,gid=10001 \
    -p "${PORT}:8091" \
    -v "${DATA_DIR}:/data:Z" \
    -e "PRETALX_URL=${PRETALX_URL}" \
    -e "PRETALX_APIKEY=${PRETALX_APIKEY}" \
    -e "PRETALX_EVENT_SLUG=${PRETALX_EVENT_SLUG}" \
    -e "PRETALX_TIMEOUT=${PRETALX_TIMEOUT}" \
    -e "SCHEDULE_VERSION=${SCHEDULE_VERSION}" \
    -e "BASE_PATH=${BASE_PATH}" \
    -e "READ_GROUPS=${READ_GROUPS}" \
    -e "WRITE_GROUPS=${WRITE_GROUPS}" \
    -e "READ_GROUPS_FEEDBACK=${READ_GROUPS_FEEDBACK}" \
    -e "WRITE_GROUPS_FEEDBACK=${WRITE_GROUPS_FEEDBACK}" \
    -e "DEV_AUTH_ENABLED=${DEV_AUTH_ENABLED}" \
    -e "DEV_AUTH_EMAIL=${DEV_AUTH_EMAIL}" \
    -e "DEV_AUTH_USER=${DEV_AUTH_USER}" \
    -e "DEV_AUTH_GROUPS=${DEV_AUTH_GROUPS}" \
    "${IMAGE_TAG}"

echo ""
echo "✓ Feedback Viewer is running!"
echo "  URL:  http://shell01.nest:${PORT}${BASE_PATH}/"
echo "  Logs: podman logs -f ${CONTAINER_NAME}"
echo "  Stop: podman stop ${CONTAINER_NAME}"
