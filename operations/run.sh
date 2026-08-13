#!/usr/bin/env bash
# run.sh — Build and run the Operations Resource Manager container.
# Mirrors the pattern from web/run.sh.
#
# Usage:
#   cd operations/
#   ./run.sh
#
# Access at: http://shell01.nest:8090/ef-operations/

set -euo pipefail

CONTAINER_NAME="ef-operations"
PORT=8090
IMAGE_TAG="ef-operations:latest"
DATA_DIR="$HOME/ef-operations-data"   # SQLite database storage

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
BASE_PATH="${BASE_PATH:-/ef-operations}"

# ACL group IDs (optional — if unset, all access is allowed)
READ_GROUPS="${READ_GROUPS:-}"
WRITE_GROUPS="${WRITE_GROUPS:-}"

# Dev auth override (set these for local testing without oauth2-proxy)
DEV_AUTH_EMAIL="${DEV_AUTH_EMAIL:-}"
DEV_AUTH_USER="${DEV_AUTH_USER:-}"
DEV_AUTH_GROUPS="${DEV_AUTH_GROUPS:-}"

# APP Data and Credentials
EF_APP_API="${EF_APP_API:-}"
EF_APP_ANNOUNCE_TOKEN="${EF_APP_ANNOUNCE_TOKEN:-}"

# EFSCHED Bot Data and Credentials
EF_EFSCHED_BOT="${EF_EFSCHED_BOT:-}"
EF_EFSCHED_BOT_TOKEN="${EF_EFSCHED_BOT_TOKEN:-}"

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
echo "→ SQLite data at: $DATA_DIR"

# --- Run ---
echo "→ Starting container '${CONTAINER_NAME}' on port ${PORT}…"
podman run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    -p "${PORT}:8090" \
    -v "${DATA_DIR}:/data:Z" \
    -e "PRETALX_URL=${PRETALX_URL}" \
    -e "PRETALX_APIKEY=${PRETALX_APIKEY}" \
    -e "PRETALX_EVENT_SLUG=${PRETALX_EVENT_SLUG}" \
    -e "SCHEDULE_VERSION=${SCHEDULE_VERSION}" \
    -e "BASE_PATH=${BASE_PATH}" \
    -e "READ_GROUPS=${READ_GROUPS}" \
    -e "WRITE_GROUPS=${WRITE_GROUPS}" \
    -e "DEV_AUTH_EMAIL=${DEV_AUTH_EMAIL}" \
    -e "DEV_AUTH_USER=${DEV_AUTH_USER}" \
    -e "DEV_AUTH_GROUPS=${DEV_AUTH_GROUPS}" \
    -e "EF_APP_API=${EF_APP_API}" \
    -e "EF_APP_ANNOUNCE_TOKEN=${EF_APP_ANNOUNCE_TOKEN}" \
    -e "EF_EFSCHED_BOT=${EF_EFSCHED_BOT}" \
    -e "EF_EFSCHED_BOT_TOKEN=${EF_EFSCHED_BOT_TOKEN}" \
    "${IMAGE_TAG}"

echo ""
echo "✓ Operations is running!"
echo "  URL:  http://shell01.nest:${PORT}${BASE_PATH}/"
echo "  Logs: podman logs -f ${CONTAINER_NAME}"
echo "  Stop: podman stop ${CONTAINER_NAME}"
