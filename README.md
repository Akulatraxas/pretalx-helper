# Pretalx API Python Client

A small library to interact with the pretalx api (v1) as well as a set of helper scripts to make your life with pretalx a bit easier
https://docs.pretalx.org/api/resources/

---

## Getting Started

### 1. Setup Configuration
Make sure your `.env` file exists in the directory where your script runs. It should contain your Pretalx instance URL and API Key:

```ini
PRETALX_URL="https://cfp.eurofurence.org/"
PRETALX_APIKEY="your_api_token_here"
```

### 2. Basic Initialization
The client automatically picks up credentials from your environment or `.env` file when instantiated:

```python
from pretalx_client import PretalxClient

# Automatically loads URL and API Key from environment or .env
client = PretalxClient()

# Or explicitly pass credentials:
# client = PretalxClient(url="https://cfp.eurofurence.org/", apikey="your_token")
```

---

## Usage Examples

### 1. Root & Events
```python
# Get Root API Metadata
root = client.get_root()
print(f"Pretalx Version: {root['version']}")

# List All Events
for event in client.list_events():
    name = event['name']['en']
    print(f"Event: {name} (Slug: {event['slug']})")

# Get Event Detail
event_detail = client.get_event("eurofurence-30-2026")
```

### 2. Schedules
```python
# List Schedule Versions
for schedule in client.list_schedules("eurofurence-30-2026"):
    print(f"Version: {schedule['version']} | ID: {schedule['id']}")

# Get Detailed Schedule (Highly recommended to expand slots, room, and submission)
schedule = client.get_schedule(
    "eurofurence-30-2026", 
    "latest", 
    expand=["slots", "slots.room", "slots.submission"]
)
for slot in schedule["slots"]:
    print(f"Slot: {slot['submission']['title']} in Room {slot['room']['name']['en']}")
```

### 3. Speakers
```python
# List All Speakers
for speaker in client.list_speakers("eurofurence-30-2026"):
    print(f"Speaker: {speaker['name']} (Code: {speaker['code']})")

# Get Detailed Speaker
speaker = client.get_speaker("eurofurence-30-2026", "JHB3YN")
print(f"Bio: {speaker['biography']}")
```

### 4. Talk Slots
```python
# List Talk Slots (returns latest schedule slots by default)
slots = client.list_slots("eurofurence-30-2026", expand=["room", "submission"])
for slot in slots:
    print(f"Talk: {slot['submission']['title']} | Room: {slot['room']['name']['en']}")
```

### 5. Organiser Teams
```python
try:
    # Requires correct organiser slug and scoped token permissions
    teams = client.list_teams("eurofurence")
    for team in teams:
        print(f"Team: {team['name']}")
except Exception as e:
    print(f"Could not load teams: {e}")
```

### 6. Submissions & Copying
```python
# Get detailed submission
submission = client.get_submission("eurofurence-30-2026", "MJRE78")
print(f"Title: {submission['title']}")

# Copy an existing submission with optional overrides
new_sub, orga_url = client.copy_submission(
    event_slug="eurofurence-30-2026",
    code="MJRE78",
    title="New Locker Service Title",  # Override
    duration=45,                      # Override (minutes)
    slot_count=2                      # Override
)
print(f"Cloned Code: {new_sub['code']}")
print(f"Organizer Link: {orga_url}")
```

---

## Command Line Utilities

### 1. General Demo
To see the API client in action immediately and print a beautifully formatted visualization of the Eurofurence Pretalx data, run the included `demo.py` script:
```bash
python3 demo.py
```

### 2. Copy Submission Helper
You can clone/copy an existing submission with overrides directly from the command line using `copy_submission.py`:
```bash
python3 copy_submission.py --event eurofurence-30-2026 --code MJRE78 --title "Cloned Locker Service Test" --duration 45 --slots 2
```
