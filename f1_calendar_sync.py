# flake8: noqa: E501
"""
F1 Calendar Sync Service
Automatically adds Formula 1 races, qualifying, and sprint sessions to Google Calendar
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Google Calendar API scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# F1 API endpoint
F1_API_BASE = "https://f1api.dev/api/current"

# Calendar configuration
CALENDAR_TIMEZONE = "UTC"
CALENDAR_DESCRIPTION = (
    "Formula 1 races, qualifying, and sprint sessions automatically synced"
)

# Configuration
CALENDAR_NAME = os.getenv("CALENDAR_NAME", "")
if not CALENDAR_NAME:
    raise ValueError("CALENDAR_NAME environment variable is required.")
USER_EMAIL = os.getenv("USER_EMAIL", "")


class F1APIClient:
    """Client for fetching F1 race data"""

    def __init__(self, api_base: str = F1_API_BASE):
        self.api_base = api_base

    def get_f1_schedule(self) -> List[Dict]:
        """Fetch F1 schedule from the API"""
        try:
            response = requests.get(self.api_base, timeout=10)

            if response.status_code == 200:
                data = response.json()
                races = data.get("races", [])
                logger.info(f"Successfully fetched {len(races)} races")
                return races
            else:
                logger.error(
                    f"API request failed with status {response.status_code}: {response.text[:500]}"
                )
                return []

        except Exception as e:
            logger.error(f"Error fetching F1 schedule: {str(e)}", exc_info=True)
            return []


class GoogleCalendarService:
    """Service for managing Google Calendar events"""

    def __init__(
        self,
        credentials_file: str = "credentials.json",
        token_file: str = "token.json",
        service_account_file: Optional[str] = None,
    ):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service_account_file = service_account_file or os.getenv(
            "GOOGLE_SERVICE_ACCOUNT_FILE"
        )
        self.service_account_email = None
        self.service = None
        self._authenticate()
        self._load_service_account_email()

    def _authenticate(self):
        """Authenticate with Google Calendar API"""
        creds = None

        # Try service account authentication first (for CI/CD)
        if self.service_account_file and os.path.exists(self.service_account_file):
            try:
                creds = service_account.Credentials.from_service_account_file(
                    self.service_account_file, scopes=SCOPES
                )
                logger.info("Using service account authentication")
            except Exception as e:
                logger.warning(f"Failed to load service account: {e}")

        # If no service account, try OAuth (for local use)
        if not creds:
            # Load existing token
            if os.path.exists(self.token_file):
                creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)

            # If there are no (valid) credentials, request authorization
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(self.credentials_file):
                        raise FileNotFoundError(
                            f"Credentials file '{self.credentials_file}' not found. "
                            "Please download it from Google Cloud Console. "
                            "For GitHub Actions, use GOOGLE_SERVICE_ACCOUNT_FILE environment variable."
                        )
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_file, SCOPES
                    )
                    creds = flow.run_local_server(port=0)

                # Save credentials for next run (only for OAuth, not service account)
                if self.token_file:
                    with open(self.token_file, "w") as token:
                        token.write(creds.to_json())

        self.service = build("calendar", "v3", credentials=creds)
        logger.info("Successfully authenticated with Google Calendar API")

    def _load_service_account_email(self):
        """Load service account email from credentials file"""
        self.service_account_email = None
        if not (
            self.service_account_file and os.path.exists(self.service_account_file)
        ):
            return

        try:
            with open(self.service_account_file, "r") as f:
                creds_data = json.load(f)
                self.service_account_email = creds_data.get("client_email", "")
                if self.service_account_email:
                    logger.info(f"Service account email: {self.service_account_email}")
        except Exception as e:
            logger.debug(f"Could not load service account email: {e}")

    def _share_calendar_with_user(self, calendar_id: str, user_email: str) -> None:
        """Share calendar with user email if not already shared"""
        if not user_email:
            return

        try:
            acl_list = self.service.acl().list(calendarId=calendar_id).execute()
            shared_with_user = any(
                entry.get("scope", {}).get("value") == user_email
                for entry in acl_list.get("items", [])
            )
            if not shared_with_user:
                acl_rule = {
                    "scope": {"type": "user", "value": user_email},
                    "role": "owner",
                }
                self.service.acl().insert(
                    calendarId=calendar_id, body=acl_rule
                ).execute()
                logger.info(f"Shared calendar with: {user_email}")
        except Exception as e:
            logger.warning(f"Could not share calendar: {e}")

    def get_or_create_calendar(self, calendar_name: str) -> str:
        """Get existing calendar ID or create a new calendar"""
        try:
            # List existing calendars
            calendar_list = self.service.calendarList().list().execute()
            calendars = calendar_list.get("items", [])

            logger.info(f"Searching for calendar: '{calendar_name}'")
            matching_calendars = [
                cal for cal in calendars if cal.get("summary") == calendar_name
            ]

            if matching_calendars:
                shared_calendars = [
                    cal
                    for cal in matching_calendars
                    if cal.get("accessRole") != "owner"
                ]
                calendar_entry = (
                    shared_calendars[0] if shared_calendars else matching_calendars[0]
                )
                calendar_id = calendar_entry["id"]
                logger.info(f"Found calendar: '{calendar_name}'")
                self._share_calendar_with_user(calendar_id, USER_EMAIL)
                return calendar_id

            # Calendar not found - create it with service account and share with user
            logger.info(
                f"Calendar '{calendar_name}' not found. Creating new calendar..."
            )
            calendar = {
                "summary": calendar_name,
                "description": CALENDAR_DESCRIPTION,
                "timeZone": CALENDAR_TIMEZONE,
            }
            created_calendar = self.service.calendars().insert(body=calendar).execute()
            calendar_id = created_calendar["id"]
            logger.info(f"Created calendar: '{calendar_name}'")
            self._share_calendar_with_user(calendar_id, USER_EMAIL)
            return calendar_id

        except HttpError as error:
            logger.error(f"Error managing calendar: {error}")
            raise

    def find_existing_event(
        self, calendar_id: str, event_title: str, event_start: datetime
    ) -> Optional[Dict]:
        """Find existing event by title on the same date. Returns event dict or None."""
        try:
            time_min = event_start.replace(hour=0, minute=0, second=0).isoformat()
            time_max = event_start.replace(hour=23, minute=59, second=59).isoformat()

            events_result = (
                self.service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = events_result.get("items", [])
            for event in events:
                if event.get("summary") == event_title:
                    return event
            return None
        except HttpError as error:
            logger.error(f"Error checking existing events: {error}")
            return None

    def add_or_update_event(
        self,
        calendar_id: str,
        title: str,
        start_time: datetime,
        description: str = "",
        location: str = "",
    ) -> Optional[str]:
        """Add or update (replace) an event in the calendar"""
        try:
            # Check if event already exists
            existing_event = self.find_existing_event(calendar_id, title, start_time)

            # Prepare event data
            end_time = start_time.replace(hour=start_time.hour + 2)
            event = {
                "summary": title,
                "description": description,
                "location": location,
                "start": {
                    "dateTime": start_time.isoformat(),
                    "timeZone": CALENDAR_TIMEZONE,
                },
                "end": {
                    "dateTime": end_time.isoformat(),
                    "timeZone": CALENDAR_TIMEZONE,
                },
            }

            if existing_event:
                # Update existing event (replace with new data)
                event_id = existing_event.get("id")
                updated_event = (
                    self.service.events()
                    .update(calendarId=calendar_id, eventId=event_id, body=event)
                    .execute()
                )
                logger.info(
                    f"✓ Updated event: {title} on {start_time.strftime('%Y-%m-%d %H:%M')} UTC"
                )
                return updated_event.get("id")
            else:
                # Create new event
                new_event = (
                    self.service.events()
                    .insert(calendarId=calendar_id, body=event)
                    .execute()
                )
                logger.info(
                    f"✓ Added event: {title} on {start_time.strftime('%Y-%m-%d %H:%M')} UTC"
                )
                return new_event.get("id")

        except HttpError as error:
            logger.error(f"Error adding/updating event: {error}")
            return None


def parse_f1_datetime(date_str: str, time_str: str) -> Optional[datetime]:
    """Parse F1 datetime from date and time strings"""
    if not date_str or not time_str:
        return None

    try:
        # Combine date and time: "2025-03-16" + "04:00:00Z" -> "2025-03-16T04:00:00Z"
        dt_str = f"{date_str}T{time_str}"
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, TypeError) as e:
        logger.warning(f"Could not parse datetime: {date_str} {time_str} - {e}")
        return None


def format_session_title(race: Dict, session_type: str) -> str:
    """Format session title for calendar event"""
    race_name = race.get("raceName", "F1 Race")
    circuit = race.get("circuit", {})
    circuit_name = circuit.get("circuitName", "")
    country = circuit.get("country", "")

    # Remove year from race name if present (e.g., "Australian Grand Prix 2025" -> "Australian Grand Prix")
    race_name = race_name.rsplit(" ", 1)[0] if race_name else "F1 Race"

    session_labels = {
        "race": "Race",
        "qualy": "Qualifying",
        "sprintRace": "Sprint Race",
        "sprintQualy": "Sprint Qualifying",
    }
    session_label = session_labels.get(session_type, session_type.title())

    if circuit_name:
        return f"F1 {race_name} - {session_label} ({circuit_name})"
    elif country:
        return f"F1 {race_name} - {session_label} ({country})"
    else:
        return f"F1 {race_name} - {session_label}"


def format_session_description(race: Dict, session_type: str) -> str:
    """Format session description for calendar event"""
    circuit = race.get("circuit", {})
    circuit_name = circuit.get("circuitName", "")
    country = circuit.get("country", "")
    city = circuit.get("city", "")
    round_num = race.get("round", "")

    parts = []
    if round_num:
        parts.append(f"Round {round_num}")
    if circuit_name:
        parts.append(f"Circuit: {circuit_name}")
    if city and country:
        parts.append(f"Location: {city}, {country}")
    elif country:
        parts.append(f"Location: {country}")

    session_labels = {
        "race": "Race",
        "qualy": "Qualifying",
        "sprintRace": "Sprint Race",
        "sprintQualy": "Sprint Qualifying",
    }
    session_label = session_labels.get(session_type, session_type.title())
    return f"Formula 1 {session_label}\n" + "\n".join(parts)


def sync_f1_schedule():
    """Main function to sync F1 schedule to Google Calendar"""
    logger.info("Starting F1 calendar sync...")

    # Initialize services
    f1_client = F1APIClient()

    # Get service account file from environment if available (for GitHub Actions)
    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    calendar_service = GoogleCalendarService(service_account_file=service_account_file)

    # Get or create calendar
    calendar_id = calendar_service.get_or_create_calendar(CALENDAR_NAME)

    races = f1_client.get_f1_schedule()

    if not races:
        logger.warning("No races found. Check API connection.")
        return

    logger.info(f"Processing {len(races)} race(s)...")

    added_count = 0
    updated_count = 0
    past_count = 0
    invalid_date_count = 0
    current_time = datetime.now(timezone.utc)

    # Session types to sync
    session_types = ["race", "qualy", "sprintRace", "sprintQualy"]

    for race in races:
        schedule = race.get("schedule", {})
        circuit = race.get("circuit", {})
        location = f"{circuit.get('city', '')}, {circuit.get('country', '')}".strip(
            ", "
        )

        for session_type in session_types:
            session = schedule.get(session_type, {})
            if not session or not session.get("date") or not session.get("time"):
                continue

            session_date = session.get("date")
            session_time = session.get("time")

            match_datetime = parse_f1_datetime(session_date, session_time)
            if not match_datetime:
                invalid_date_count += 1
                continue

            if match_datetime < current_time:
                past_count += 1
                continue

            title = format_session_title(race, session_type)
            description = format_session_description(race, session_type)

            # Check if event exists before calling add_or_update_event
            existing_event = calendar_service.find_existing_event(
                calendar_id, title, match_datetime
            )
            was_existing = existing_event is not None

            event_id = calendar_service.add_or_update_event(
                calendar_id=calendar_id,
                title=title,
                start_time=match_datetime,
                description=description,
                location=location,
            )

            if event_id:
                if was_existing:
                    updated_count += 1
                else:
                    added_count += 1

    logger.info("=" * 60)
    logger.info("Sync Summary:")
    logger.info(f"  - Total races fetched: {len(races)}")
    logger.info(f"  - Events added: {added_count}")
    logger.info(f"  - Events updated/replaced: {updated_count}")
    logger.info(f"  - Past sessions skipped: {past_count}")
    logger.info(f"  - Invalid date skipped: {invalid_date_count}")
    logger.info("=" * 60)

    if added_count == 0 and updated_count == 0 and past_count > 0:
        logger.warning(
            "⚠ No events added or updated because all sessions are in the past!"
        )
        logger.info(
            "This is normal if the F1 season has ended. New sessions will appear when the next season schedule is announced."
        )
    elif added_count == 0 and updated_count == 0:
        logger.warning(
            "⚠ No events were added or updated. Check the logs above for details."
        )


if __name__ == "__main__":
    sync_f1_schedule()

