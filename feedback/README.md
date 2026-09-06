# EF Feedback Viewer

A web service for viewing attendee feedback collected during convention events. Built on top of the Pretalx API.

## What it does

Displays and organizes feedback submitted by convention attendees for talks, panels, and events.

## Quick start

```bash
cd feedback/
./run.sh
# → http://shell01.nest:8091/ef-feedback/
```

`run.sh` reads credentials from `../.env`, copies `pretalx_client.py` and fonts, builds the container image, and starts it on port 8091.

## Configuration

Set these in `../.env` (or export them before running):

```env
PRETALX_URL=https://cfp.example.org
PRETALX_APIKEY=your-api-key
PRETALX_EVENT_SLUG=ef2026
SCHEDULE_VERSION=latest        # "latest" (published, no blockers) or "wip"
PRETALX_TIMEOUT=30             # API request timeout in seconds
BASE_PATH=/ef-feedback         # URL prefix
```

### Access control

The app expects an [oauth2-proxy](https://oauth2-proxy.github.io/) in front that injects `X-Auth-Email`, `X-Auth-User`, and `X-Auth-Groups` headers.

```env
READ_GROUPS=group-id-a          # comma-separated group IDs for global read access
WRITE_GROUPS=group-id-b         # write implies read; unset = allow all
READ_GROUPS_FEEDBACK=group-id-c # feedback-specific read
WRITE_GROUPS_FEEDBACK=group-id-d # feedback-specific write
```

**Local development without a proxy** — inject fake credentials directly:

```env
DEV_AUTH_ENABLED=true
DEV_AUTH_EMAIL=dev@example.com
DEV_AUTH_USER=Developer
DEV_AUTH_GROUPS=group-id-b
```

The service refuses to start without ACL groups unless this explicit development
mode is enabled with a development email.

## Container management

```bash
podman logs -f ef-feedback    # live logs
podman stop ef-feedback       # stop
./run.sh                      # rebuild and restart
```

The SQLite database is persisted in `~/ef-feedback-data/feedback.db` on the host.
The container runs as UID/GID 10001. `run.sh` maps the invoking user to that
identity so the bind-mounted data directory remains writable. For other Docker
launchers, ensure the host directory is writable by UID/GID 10001.

## Stack

- **Backend**: Python 3.12, Flask, Gunicorn, SQLite (WAL mode)
- **Frontend**: Vanilla HTML/CSS/JS, no framework
- **Container**: Podman / Docker, port 8091
