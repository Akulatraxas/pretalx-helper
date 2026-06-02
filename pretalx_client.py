"""
Pretalx API Python Client
A clean, robust, and zero-dependency library for interacting with the Pretalx REST API.
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
            
        self.base_url = url or os.environ.get("PRETALX_URL")
        self.apikey = apikey or os.environ.get("PRETALX_APIKEY")
        self.version = version
        
        if not self.base_url:
            raise ValueError(
                "Pretalx Base URL is missing. Set PRETALX_URL in your environment/.env or pass it to the constructor."
            )
        if not self.apikey:
            raise ValueError(
                "Pretalx API Key is missing. Set PRETALX_APIKEY in your environment/.env or pass it to the constructor."
            )
            
        # Clean the base URL: ensure it doesn't end with trailing slash and includes /api
        self.base_url = self.base_url.rstrip("/")
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
