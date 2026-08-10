"""
Pretalx API Python Client
A low dependency api-lib to speak to pretalx v1
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error

# --- Exception Classes ---

class PretalxAPIError(Exception):
    """Base exception for Pretalx API errors."""
    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class PretalxAuthError(PretalxAPIError):
    """Raised for authentication or permission errors (HTTP 401, 403)."""
    pass


class PretalxNotFoundError(PretalxAPIError):
    """Raised when a requested resource is not found (HTTP 404)."""
    pass


class PretalxRateLimitError(PretalxAPIError):
    """Raised when the API rate limit is exceeded (HTTP 429)."""
    pass


# --- Helper Functions ---

def load_env(env_path=".env"):
    """
    Manually parses a standard .env file and populates os.environ.
    This guarantees zero external dependencies (no python-dotenv required).
    """
    if not os.path.exists(env_path):
        return False
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    # Remove surrounding single or double quotes
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    os.environ[key] = val
        return True
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to load .env file: {e}\n")
        return False


# --- Core Client Class ---

class PretalxClient:
    """
    The main client class for interacting with the Pretalx REST API.
    """
    def __init__(self, url=None, apikey=None, version=None):
        """
        Initializes the Pretalx API Client.
        
        Args:
            url (str, optional): The base URL of the Pretalx instance (e.g. 'https://cfp.eurofurence.org/').
                                 If omitted, attempts to load from PRETALX_URL environment variable or .env file.
            apikey (str, optional): The API token from Pretalx dashboard.
                                    If omitted, attempts to load from PRETALX_APIKEY environment variable or .env file.
            version (str, optional): The Pretalx-Version override header (e.g. 'v1' or 'v-next').
        """
        # Automatically load .env if credentials are not explicitly provided in python environment
        if not url or not apikey:
            load_env()
            
        raw_url = url or os.environ.get("PRETALX_URL")
        self.apikey = apikey or os.environ.get("PRETALX_APIKEY")
        self.version = version
        
        if not raw_url:
            raise ValueError(
                "Pretalx Base URL is missing. Set PRETALX_URL in your environment/.env or pass it to the constructor."
            )
        if not self.apikey:
            raise ValueError(
                "Pretalx API Key is missing. Set PRETALX_APIKEY in your environment/.env or pass it to the constructor."
            )
            
        # Standardize and save the base website URL (without /api or /api/v1) for link generation
        self.site_url = raw_url.rstrip("/")
        if self.site_url.endswith("/api/v1"):
            self.site_url = self.site_url[:-7]
        elif self.site_url.endswith("/api"):
            self.site_url = self.site_url[:-4]
        self.site_url = self.site_url.rstrip("/")

        # Clean the base URL: ensure it doesn't end with trailing slash and includes /api
        self.base_url = raw_url.rstrip("/")
        if not self.base_url.endswith("/api") and not self.base_url.endswith("/api/v1"):
            # By default, endpoints exist under the /api/ prefix
            self.base_url = f"{self.base_url}/api"

    def _request_raw(self, method, url, params=None, data=None):
        """Internal helper to execute low-level HTTP requests."""
        if params:
            # Clean and translate query parameters
            cleaned_params = {}
            for k, v in params.items():
                if v is not None:
                    if isinstance(v, list):
                        cleaned_params[k] = ",".join(map(str, v))
                    elif isinstance(v, bool):
                        cleaned_params[k] = "true" if v else "false"
                    else:
                        cleaned_params[k] = str(v)
            if cleaned_params:
                url = f"{url}?{urllib.parse.urlencode(cleaned_params)}"
                
        req = urllib.request.Request(url, method=method)
        req.add_header("Authorization", f"Token {self.apikey}")
        req.add_header("Accept", "application/json")
        if self.version:
            req.add_header("Pretalx-Version", self.version)
            
        if data is not None:
            req.add_header("Content-Type", "application/json")
            req.data = json.dumps(data).encode("utf-8")
            
        try:
            with urllib.request.urlopen(req) as response:
                status_code = response.status
                res_data = response.read().decode("utf-8")
                if status_code == 204:
                    return None
                return json.loads(res_data) if res_data else {}
        except urllib.error.HTTPError as e:
            status_code = e.code
            try:
                body = e.read().decode("utf-8")
                err_data = json.loads(body) if body else {}
                detail = err_data.get("detail") or str(err_data) or e.reason
            except Exception:
                body = None
                detail = e.reason
                
            if status_code in (401, 403):
                raise PretalxAuthError(
                    f"Authentication or permission error ({status_code}): {detail}",
                    status_code,
                    body
                )
            elif status_code == 404:
                raise PretalxNotFoundError(
                    f"Requested resource not found (404): {detail}",
                    status_code,
                    body
                )
            elif status_code == 429:
                raise PretalxRateLimitError(
                    f"Rate limit exceeded (429): {detail}",
                    status_code,
                    body
                )
            else:
                raise PretalxAPIError(
                    f"HTTP error occurred ({status_code}): {detail}",
                    status_code,
                    body
                )
        except urllib.error.URLError as e:
            raise PretalxAPIError(f"Connection or URL error occurred: {e.reason}")

    def _request(self, method, path, params=None, data=None):
        """Internal helper to request a relative API path."""
        if not path.startswith("/"):
            path = f"/{path}"
        url = f"{self.base_url}{path}"
        return self._request_raw(method, url, params=params, data=data)

    def _get_paginated(self, path, params=None):
        """
        Internal generator that handles automatic page-by-page traversal 
        for both paginated dictionary and flat array list endpoints.
        """
        response = self._request("GET", path, params=params)
        
        # If response is a paginated dictionary structure
        if isinstance(response, dict) and "results" in response:
            for item in response["results"]:
                yield item
            next_url = response.get("next")
            while next_url:
                response = self._request_raw("GET", next_url)
                for item in response.get("results", []):
                    yield item
                next_url = response.get("next")
        # If response is already a flat list (e.g. /api/events/)
        elif isinstance(response, list):
            for item in response:
                yield item
        # If response is a singular detail object or other structure
        else:
            yield response

    # --- Root Endpoint ---

    def get_root(self):
        """
        Retrieves the REST API root metadata, including the Pretalx and API versions.
        
        Returns:
            dict: The API root metadata.
        """
        return self._request("GET", "/")

    # --- Events Endpoints ---

    def list_events(self, is_public=None, q=None):
        """
        Lists events accessible to the user.
        
        Args:
            is_public (bool, optional): Filter by public events status.
            q (str, optional): Search term matching the event's name.
            
        Returns:
            generator: Yields event dictionaries.
        """
        params = {}
        if is_public is not None:
            params["is_public"] = is_public
        if q is not None:
            params["q"] = q
        return self._get_paginated("/events/", params=params)

    def get_event(self, event_slug):
        """
        Retrieves detailed information for a specific event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            
        Returns:
            dict: Event details dictionary.
        """
        return self._request("GET", f"/events/{event_slug}/")

    # --- Teams Endpoints ---

    def list_teams(self, organiser_slug, expand=None, q=None):
        """
        Lists teams for a specific organiser.
        
        Args:
            organiser_slug (str): The short slug identifying the organiser.
            expand (list, optional): Select fields to expand ('invites', 'limit_tracks', 'members').
            q (str, optional): Search term matching the team name.
            
        Returns:
            generator: Yields team dictionaries.
        """
        params = {}
        if expand is not None:
            params["expand"] = expand
        if q is not None:
            params["q"] = q
        return self._get_paginated(f"/organisers/{organiser_slug}/teams/", params=params)

    def get_team(self, organiser_slug, team_id, expand=None):
        """
        Retrieves detailed information for a specific team.
        
        Args:
            organiser_slug (str): The short slug identifying the organiser.
            team_id (int): The unique integer ID of the team.
            expand (list, optional): Select fields to expand ('invites', 'limit_tracks', 'members').
            
        Returns:
            dict: Team details dictionary.
        """
        params = {}
        if expand is not None:
            params["expand"] = expand
        return self._request("GET", f"/organisers/{organiser_slug}/teams/{team_id}/", params=params)

    # --- Schedules Endpoints ---

    def list_schedules(self, event_slug, q=None):
        """
        Lists all published and unpublished schedules of an event.
        Note: List schedules endpoint only returns metadata due to complex data sizes.
        
        Args:
            event_slug (str): The short slug identifying the event.
            q (str, optional): Search term matching schedule version.
            
        Returns:
            generator: Yields schedule metadata dictionaries.
        """
        params = {}
        if q is not None:
            params["q"] = q
        return self._get_paginated(f"/events/{event_slug}/schedules/", params=params)

    def get_schedule(self, event_slug, schedule_id, expand=None):
        """
        Retrieves detailed information for a specific schedule.
        In addition to standard lookup by ID, you can use the special 'wip' and 'latest'
        path identifiers to access unpublished and latest published schedules respectively.
        
        Args:
            event_slug (str): The short slug identifying the event.
            schedule_id (str/int): Unique identifier, 'wip', or 'latest'.
            expand (list, optional): Select fields to expand (e.g. ['slots', 'slots.room',
                                     'slots.submission', 'slots.submission.speakers']).
                                     Expanding is highly recommended to receive actual schedule data.
                                     
        Returns:
            dict: Detailed schedule dictionary.
        """
        params = {}
        if expand is not None:
            params["expand"] = expand
        return self._request("GET", f"/events/{event_slug}/schedules/{schedule_id}/", params=params)

    # --- Speakers Endpoints ---

    def list_speakers(self, event_slug, q=None, expand=None):
        """
        Lists all speakers of an event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            q (str, optional): Search term matching the speaker's name (and email for organisers).
            expand (list, optional): Select fields to expand ('answers', 'answers.question', 'submissions').
            
        Returns:
            generator: Yields speaker dictionaries.
        """
        params = {}
        if q is not None:
            params["q"] = q
        if expand is not None:
            params["expand"] = expand
        return self._get_paginated(f"/events/{event_slug}/speakers/", params=params)

    def get_speaker(self, event_slug, speaker_code, expand=None):
        """
        Retrieves detailed information for a specific speaker by their unique code.
        
        Args:
            event_slug (str): The short slug identifying the event.
            speaker_code (str): The speaker's alphanumeric code.
            expand (list, optional): Select fields to expand ('answers', 'answers.question', 'submissions').
            
        Returns:
            dict: Detailed speaker dictionary.
        """
        params = {}
        if expand is not None:
            params["expand"] = expand
        return self._request("GET", f"/events/{event_slug}/speakers/{speaker_code}/", params=params)

    # --- Slots Endpoints ---

    def list_slots(self, event_slug, q=None, room=None, schedule=None,
                   schedule_version=None, speaker=None, submission=None, expand=None):
        """
        Lists talk slots of an event. Returns a filtered list. If no filters are provided,
        it defaults to talk slots in the latest published schedule.
        
        Args:
            event_slug (str): The short slug identifying the event.
            q (str, optional): Search term matching 'submission.title' or 'submission.speakers.name'.
            room (int, optional): Filter by room ID.
            schedule (int, optional): Filter by schedule ID.
            schedule_version (str, optional): Filter by schedule version string.
            speaker (str, optional): Filter by speaker alphanumeric code.
            submission (str, optional): Filter by submission alphanumeric code.
            expand (list, optional): Select fields to expand (e.g. ['room', 'schedule', 'submission',
                                     'submission.speakers', 'submission.track', 'submission.submission_type']).
                                     
        Returns:
            generator: Yields talk slot dictionaries.
        """
        params = {}
        if q is not None:
            params["q"] = q
        if room is not None:
            params["room"] = room
        if schedule is not None:
            params["schedule"] = schedule
        if schedule_version is not None:
            params["schedule_version"] = schedule_version
        if speaker is not None:
            params["speaker"] = speaker
        if submission is not None:
            params["submission"] = submission
        if expand is not None:
            params["expand"] = expand
            
        return self._get_paginated(f"/events/{event_slug}/slots/", params=params)

    def get_slot(self, event_slug, slot_id, expand=None):
        """
        Retrieves detailed information for a specific talk slot.
        
        Args:
            event_slug (str): The short slug identifying the event.
            slot_id (int): The unique integer ID of the talk slot.
            expand (list, optional): Select fields to expand (e.g. ['room', 'schedule', 'submission']).
            
        Returns:
            dict: Detailed talk slot dictionary.
        """
        params = {}
        if expand is not None:
            params["expand"] = expand
        return self._request("GET", f"/events/{event_slug}/slots/{slot_id}/", params=params)

    # --- Submissions Endpoints ---

    def list_submissions(self, event_slug, q=None, state=None, expand=None):
        """
        Lists submissions of an event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            q (str, optional): Search term matching submission title or speaker name.
            state (str, optional): Filter by submission state.
            expand (list, optional): Select fields to expand.
            
        Returns:
            generator: Yields submission dictionaries.
        """
        params = {}
        if q is not None:
            params["q"] = q
        if state is not None:
            params["state"] = state
        if expand is not None:
            params["expand"] = expand
            
        return self._get_paginated(f"/events/{event_slug}/submissions/", params=params)

    def get_submission(self, event_slug, code, expand=None):
        """
        Retrieves detailed information for a specific submission by its unique code.
        
        Args:
            event_slug (str): The short slug identifying the event.
            code (str): The unique alphanumeric code of the submission.
            expand (list, optional): Select fields to expand.
            
        Returns:
            dict: Detailed submission dictionary.
        """
        params = {}
        if expand is not None:
            params["expand"] = expand
        return self._request("GET", f"/events/{event_slug}/submissions/{code}/", params=params)

    def create_submission(self, event_slug, data):
        """
        Creates a new submission inside the specified event context.
        
        Args:
            event_slug (str): The short slug identifying the event.
            data (dict): The fields of the submission to create.
            
        Returns:
            dict: The created submission details.
        """
        return self._request("POST", f"/events/{event_slug}/submissions/", data=data)

    def update_submission(self, event_slug, code, data, partial=False):
        """
        Updates a submission.
        
        Args:
            event_slug (str): The short slug identifying the event.
            code (str): The unique alphanumeric code of the submission to update.
            data (dict): The payload containing fields to update.
            partial (bool, optional): If True, performs PATCH (partial update). Else PUT.
            
        Returns:
            dict: The updated submission details.
        """
        method = "PATCH" if partial else "PUT"
        return self._request(method, f"/events/{event_slug}/submissions/{code}/", data=data)

    def copy_submission(self, event_slug, code, title=None, duration=None, slot_count=None):
        """
        Copies a submission by its code.
        Copies the title, submission_type, track, tags, duration, abstract,
        description, notes, internal_notes, and content_locale if they exist.
        Allows optionally overriding title, duration, and slot_count.
        
        Args:
            event_slug (str): The short slug identifying the event.
            code (str): The unique alphanumeric code of the submission to copy.
            title (str, optional): Override the title for the new submission.
            duration (int, optional): Override the duration (in minutes) for the new submission.
            slot_count (int, optional): Override the slot count for the new submission.
            
        Returns:
            tuple: (dict representing new submission, URL string to the created submission in orga view)
        """
        # Fetch the source submission
        source = self.get_submission(event_slug, code)
        
        payload = {}
        
        # Helper to extract ID from potentially expanded dictionary objects
        def _extract_id(val):
            if isinstance(val, dict) and "id" in val:
                return val["id"]
            return val

        # Fields to copy directly if they are not None in the source
        fields_to_copy = [
            "title", "abstract", "description", "notes", "internal_notes", "content_locale"
        ]
        for field in fields_to_copy:
            if field in source and source[field] is not None:
                payload[field] = source[field]
                
        # Copy submission_type (required field)
        if "submission_type" in source:
            payload["submission_type"] = _extract_id(source["submission_type"])
            
        # Copy track
        if "track" in source and source["track"] is not None:
            payload["track"] = _extract_id(source["track"])
            
        # Copy tags
        if "tags" in source and source["tags"] is not None:
            payload["tags"] = [_extract_id(t) for t in source["tags"]]
            
        # Copy duration
        if "duration" in source and source["duration"] is not None:
            payload["duration"] = source["duration"]
            
        # Copy slot_count
        if "slot_count" in source and source["slot_count"] is not None:
            payload["slot_count"] = source["slot_count"]
            
        # Apply overrides
        if title is not None:
            payload["title"] = title
        if duration is not None:
            payload["duration"] = duration
        if slot_count is not None:
            payload["slot_count"] = slot_count
            
        # Create the new submission
        new_sub = self.create_submission(event_slug, payload)
        
        # Reconstruct the orga dashboard URL for this submission
        new_code = new_sub.get("code")
        orga_url = f"{self.site_url}/orga/event/{event_slug}/submissions/{new_code}/"
        
        return new_sub, orga_url

    def update_submission_tags(self, event_slug, code, tags, partial=True):
        """
        Updates the tags list of a submission while leaving all other submission attributes untouched.
        
        Args:
            event_slug (str): Short slug identifying the event.
            code (str): Alphanumeric code of the submission.
            tags (list): List of tag IDs (int) or tag objects to set on the submission.
            partial (bool, optional): If True (default), performs PATCH. Else PUT.
            
        Returns:
            dict: The updated submission details dictionary.
        """
        tag_ids = [t["id"] if isinstance(t, dict) and "id" in t else t for t in tags]
        return self.update_submission(event_slug, code, {"tags": tag_ids}, partial=partial)

    def add_submission_tag(self, event_slug, code, tag_id, current_tags=None):
        """
        Adds a tag to a submission without modifying existing tags.
        
        Args:
            event_slug (str): Short slug identifying the event.
            code (str): Alphanumeric code of the submission.
            tag_id (int/dict): Tag ID or tag object to add.
            current_tags (list, optional): Existing tags list if already fetched.
            
        Returns:
            dict: The updated submission details dictionary.
        """
        tid = tag_id["id"] if isinstance(tag_id, dict) and "id" in tag_id else tag_id
        if current_tags is None:
            sub = self.get_submission(event_slug, code)
            current_tags = sub.get("tags", [])
        existing_ids = [t["id"] if isinstance(t, dict) and "id" in t else t for t in current_tags]
        if tid not in existing_ids:
            existing_ids.append(tid)
            return self.update_submission_tags(event_slug, code, existing_ids)
        return sub if sub is not None else {"code": code, "tags": existing_ids}

    def remove_submission_tag(self, event_slug, code, tag_id, current_tags=None):
        """
        Removes a tag from a submission without modifying other existing tags.
        
        Args:
            event_slug (str): Short slug identifying the event.
            code (str): Alphanumeric code of the submission.
            tag_id (int/dict): Tag ID or tag object to remove.
            current_tags (list, optional): Existing tags list if already fetched.
            
        Returns:
            dict: The updated submission details dictionary.
        """
        tid = tag_id["id"] if isinstance(tag_id, dict) and "id" in tag_id else tag_id
        if current_tags is None:
            sub = self.get_submission(event_slug, code)
            current_tags = sub.get("tags", [])
        existing_ids = [t["id"] if isinstance(t, dict) and "id" in t else t for t in current_tags]
        if tid in existing_ids:
            existing_ids.remove(tid)
            return self.update_submission_tags(event_slug, code, existing_ids)
        return sub if isinstance(current_tags[0] if current_tags else None, dict) else {"code": code, "tags": existing_ids}


    # --- Rooms Endpoints ---

    def list_rooms(self, event_slug, q=None):
        """
        Lists all rooms of an event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            q (str, optional): Search term matching the room's name.
            
        Returns:
            generator: Yields room dictionaries.
        """
        params = {}
        if q is not None:
            params["q"] = q
        return self._get_paginated(f"/events/{event_slug}/rooms/", params=params)

    def create_room(self, event_slug, data):
        """
        Creates a new room inside the specified event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            data (dict): The fields of the room to create.
            
        Returns:
            dict: The created room details.
        """
        return self._request("POST", f"/events/{event_slug}/rooms/", data=data)

    # --- Tags Endpoints ---

    def list_tags(self, event_slug, q=None):
        """
        Lists all tags of an event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            q (str, optional): Search term matching the tag name.
            
        Returns:
            generator: Yields tag dictionaries.
        """
        params = {}
        if q is not None:
            params["q"] = q
        return self._get_paginated(f"/events/{event_slug}/tags/", params=params)

    def create_tag(self, event_slug, data):
        """
        Creates a new tag inside the specified event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            data (dict): The fields of the tag to create.
            
        Returns:
            dict: The created tag details.
        """
        return self._request("POST", f"/events/{event_slug}/tags/", data=data)

    def get_tag(self, event_slug, tag_id):
        """
        Retrieves detailed information for a specific tag by ID.
        
        Args:
            event_slug (str): The short slug identifying the event.
            tag_id (int): Unique integer ID of the tag.
            
        Returns:
            dict: Detailed tag dictionary.
        """
        return self._request("GET", f"/events/{event_slug}/tags/{tag_id}/")

    def find_tag(self, event_slug, name_or_id):
        """
        Finds a tag by integer ID or string name (case-insensitive).
        
        Args:
            event_slug (str): The short slug identifying the event.
            name_or_id (int/str): The tag ID or tag name string to look up.
            
        Returns:
            dict or None: Tag dictionary if found, else None.
        """
        if isinstance(name_or_id, int) or (isinstance(name_or_id, str) and name_or_id.isdigit()):
            tag_id = int(name_or_id)
            try:
                return self.get_tag(event_slug, tag_id)
            except PretalxNotFoundError:
                pass
        target_str = str(name_or_id).strip().lower()
        for tag in self.list_tags(event_slug):
            if tag.get("id") == name_or_id:
                return tag
            tag_text = tag.get("tag")
            if isinstance(tag_text, str) and tag_text.lower() == target_str:
                return tag
            elif isinstance(tag_text, dict):
                for val in tag_text.values():
                    if str(val).lower() == target_str:
                        return tag
        return None

    # --- Tracks Endpoints ---

    def list_tracks(self, event_slug, q=None):
        """
        Lists all tracks of an event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            q (str, optional): Search term matching the track's name.
            
        Returns:
            generator: Yields track dictionaries.
        """
        params = {}
        if q is not None:
            params["q"] = q
        return self._get_paginated(f"/events/{event_slug}/tracks/", params=params)

    def create_track(self, event_slug, data):
        """
        Creates a new track inside the specified event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            data (dict): The fields of the track to create.
            
        Returns:
            dict: The created track details.
        """
        return self._request("POST", f"/events/{event_slug}/tracks/", data=data)

    # --- Mail Templates Endpoints ---

    def list_mail_templates(self, event_slug, q=None):
        """
        Lists all mail templates of an event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            q (str, optional): Search term matching the template's role or subject.
            
        Returns:
            generator: Yields mail template dictionaries.
        """
        params = {}
        if q is not None:
            params["q"] = q
        return self._get_paginated(f"/events/{event_slug}/mail-templates/", params=params)

    def create_mail_template(self, event_slug, data):
        """
        Creates a new mail template inside the specified event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            data (dict): The fields of the mail template to create.
            
        Returns:
            dict: The created mail template details.
        """
        return self._request("POST", f"/events/{event_slug}/mail-templates/", data=data)

    def update_mail_template(self, event_slug, template_id, data, partial=False):
        """
        Updates a mail template.
        
        Args:
            event_slug (str): The short slug identifying the event.
            template_id (int): The unique integer ID of the mail template.
            data (dict): The payload containing fields to update.
            partial (bool, optional): If True, performs PATCH (partial update). Else PUT.
            
        Returns:
            dict: The updated mail template details.
        """
        method = "PATCH" if partial else "PUT"
        return self._request(method, f"/events/{event_slug}/mail-templates/{template_id}/", data=data)

    # --- Submission Types Endpoints ---

    def list_submission_types(self, event_slug, q=None):
        """
        Lists all submission types of an event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            q (str, optional): Search term matching the submission type's name.
            
        Returns:
            generator: Yields submission type dictionaries.
        """
        params = {}
        if q is not None:
            params["q"] = q
        return self._get_paginated(f"/events/{event_slug}/submission-types/", params=params)

    def create_submission_type(self, event_slug, data):
        """
        Creates a new submission type inside the specified event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            data (dict): The fields of the submission type to create.
            
        Returns:
            dict: The created submission type details.
        """
        return self._request("POST", f"/events/{event_slug}/submission-types/", data=data)

    # --- Questions Endpoints ---

    def list_questions(self, event_slug, q=None, expand=None):
        """
        Lists all questions of an event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            q (str, optional): Search term matching the question text.
            expand (list, optional): Select fields to expand ('options', 'submission_types', 'tracks').
            
        Returns:
            generator: Yields question dictionaries.
        """
        params = {}
        if q is not None:
            params["q"] = q
        if expand is not None:
            params["expand"] = expand
        return self._get_paginated(f"/events/{event_slug}/questions/", params=params)

    def create_question(self, event_slug, data):
        """
        Creates a new question inside the specified event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            data (dict): The fields of the question to create.
            
        Returns:
            dict: The created question details.
        """
        return self._request("POST", f"/events/{event_slug}/questions/", data=data)

    def get_question(self, event_slug, question_id, expand=None):
        """
        Retrieves detailed information for a specific question by ID.
        
        Args:
            event_slug (str): The short slug identifying the event.
            question_id (int/str): Unique integer ID or string ID of the question.
            expand (list, optional): Select fields to expand ('options', 'submission_types', 'tracks').
            
        Returns:
            dict: Question details dictionary.
        """
        params = {}
        if expand is not None:
            params["expand"] = expand
        return self._request("GET", f"/events/{event_slug}/questions/{question_id}/", params=params)

    def find_question(self, event_slug, text_or_id):
        """
        Finds a question by integer ID, string identifier, or question text (case-insensitive).
        
        Args:
            event_slug (str): The short slug identifying the event.
            text_or_id (int/str): Question ID, identifier, or question text.
            
        Returns:
            dict or None: Question dictionary if found, else None.
        """
        if isinstance(text_or_id, int) or (isinstance(text_or_id, str) and text_or_id.isdigit()):
            q_id = int(text_or_id)
            try:
                return self.get_question(event_slug, q_id)
            except PretalxNotFoundError:
                pass
        target_str = str(text_or_id).strip().lower()
        for q in self.list_questions(event_slug):
            if q.get("id") == text_or_id or str(q.get("identifier", "")).lower() == target_str:
                return q
            q_text = q.get("question")
            if isinstance(q_text, str) and q_text.lower() == target_str:
                return q
            elif isinstance(q_text, dict):
                for val in q_text.values():
                    if str(val).lower() == target_str:
                        return q
        return None

    # --- Answers Endpoints ---

    def list_answers(self, event_slug, question=None, submission=None, speaker=None, q=None):
        """
        Lists answers to questions of an event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            question (int/str, optional): Filter by question ID.
            submission (str, optional): Filter by submission code.
            speaker (str, optional): Filter by speaker code.
            q (str, optional): Search term matching answer text.
            
        Returns:
            generator: Yields answer dictionaries.
        """
        params = {}
        if question is not None:
            params["question"] = question
        if submission is not None:
            params["submission"] = submission
        if speaker is not None:
            params["speaker"] = speaker
        if q is not None:
            params["q"] = q
        return self._get_paginated(f"/events/{event_slug}/answers/", params=params)

    def get_answer(self, event_slug, answer_id):
        """
        Retrieves detailed information for a specific answer by ID.
        
        Args:
            event_slug (str): The short slug identifying the event.
            answer_id (int): Unique integer ID of the answer.
            
        Returns:
            dict: Answer details dictionary.
        """
        return self._request("GET", f"/events/{event_slug}/answers/{answer_id}/")


    # --- Speaker Information Endpoints ---

    def list_speaker_information(self, event_slug, q=None):
        """
        Lists all speaker information entries of an event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            q (str, optional): Search term matching the title.
            
        Returns:
            generator: Yields speaker information dictionaries.
        """
        params = {}
        if q is not None:
            params["q"] = q
        return self._get_paginated(f"/events/{event_slug}/speaker-information/", params=params)

    def create_speaker_information(self, event_slug, data):
        """
        Creates a new speaker information entry inside the specified event.
        
        Args:
            event_slug (str): The short slug identifying the event.
            data (dict): The fields of the speaker information to create.
            
        Returns:
            dict: The created speaker information details.
        """
        return self._request("POST", f"/events/{event_slug}/speaker-information/", data=data)
