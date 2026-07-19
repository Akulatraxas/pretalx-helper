# EF Operations — Resource Manager

A backend service for managing physical resources at (not only Eurofurence) conventions. Built on top of the Pretalx API.

## What it does

Assign resources (projectors, fans, laptops, …) to scheduled events, add per-department notes, detect resource conflicts, and generate output lists and kanban cards.

**Four sections:**

| Section | Purpose |
|---|---|
| **Events** | Browse the schedule, assign resources and comments to talks/events |
| **Resources** | Manage the resource inventory (name, total amount, departments) |
| **Output** | Per-department table of all assignments, filterable and CSV-exportable |
| **Operations** | Live feed of upcoming events with their requirements; printable kanban cards |

## Quick start

```bash
cd operations/
./run.sh
# → http://shell01.nest:8090/ef-operations/
```

`run.sh` reads credentials from `../.env`, copies `pretalx_client.py` and fonts from sibling directories, builds the container image, and starts it on port 8090.

## Configuration

Set these in `../.env` (or export them before running):

```env
PRETALX_URL=https://cfp.example.org
PRETALX_APIKEY=your-api-key
PRETALX_EVENT_SLUG=ef2026
SCHEDULE_VERSION=latest        # "latest" (published, no blockers) or "wip"
BASE_PATH=/ef-operations       # URL prefix
```

### Access control

The app expects an [oauth2-proxy](https://oauth2-proxy.github.io/) in front that injects `X-Auth-Email`, `X-Auth-User`, and `X-Auth-Groups` headers.

```env
READ_GROUPS=group-id-a          # comma-separated group IDs for read access
WRITE_GROUPS=group-id-b         # write implies read; unset = allow all
```

**Local development without a proxy** — inject fake credentials directly:

```env
DEV_AUTH_EMAIL=dev@example.com
DEV_AUTH_USER=Developer
DEV_AUTH_GROUPS=group-id-b
```

### Departments

Fixed list: **Conops**, **FS-Support**, **CCH**. Each resource can be assigned to one or more departments, which controls which output list it appears on.

## Conflict detection

Resources with a quantity > 0 trigger conflict warnings when more slots overlap at the same time than units available. Conflicts are warn-only — they never block saving. Conflicting events are flagged with ⚠ on the Events and Output pages, and the nav badge shows the total count.

## Testing before the con

In the **Operations** tab, enable **🧪 Test mode** and pick any reference date/time. The feed will show events scheduled within the chosen time window from that point — useful for testing the kanban print before the con starts.

You can also query the API directly:

```
GET /ef-operations/api/upcoming?hours=4&at=2026-08-19T10:00&all=1
```

## Container management

```bash
podman logs -f ef-operations    # live logs
podman stop ef-operations       # stop
./run.sh                        # rebuild and restart
```

The SQLite database is persisted in `~/ef-operations-data/operations.db` on the host.

## Stack

- **Backend**: Python 3.12, Flask, Gunicorn, SQLite (WAL mode)
- **Frontend**: Vanilla HTML/CSS/JS, no framework
- **Container**: Podman / Docker, port 8090
