"""Google Calendar API adapter (fallback when gws CLI is unavailable)."""
from __future__ import annotations

from typing import Any

from googleapiclient.discovery import build

from core.context import current_user_id
from tools.google_api.auth import google_auth


def _service():
    creds = google_auth.get_credentials(current_user_id.get())
    if not creds:
        raise RuntimeError("Google account not authenticated. Visit /auth/google")
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


class CalendarAPIAdapter:
    """Direct Google Calendar API calls."""

    def list_events(
        self,
        calendar_id: str = "primary",
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 10,
    ) -> list[dict]:
        svc = _service()
        kwargs: dict[str, Any] = {
            "calendarId": calendar_id,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_min:
            kwargs["timeMin"] = time_min
        if time_max:
            kwargs["timeMax"] = time_max
        resp = svc.events().list(**kwargs).execute()
        return resp.get("items", [])

    def create_event(
        self,
        *,
        calendar_id: str = "primary",
        summary: str,
        start_datetime: str,
        end_datetime: str,
        timezone: str = "Europe/Copenhagen",
        attendees: list[str] | None = None,
        location: str | None = None,
        description: str | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start_datetime, "timeZone": timezone},
            "end": {"dateTime": end_datetime, "timeZone": timezone},
        }
        if location:
            body["location"] = location
        if description:
            body["description"] = description
        if attendees:
            body["attendees"] = [{"email": e} for e in attendees]
        svc = _service()
        return svc.events().insert(calendarId=calendar_id, body=body).execute()

    def update_event(
        self,
        *,
        event_id: str,
        calendar_id: str = "primary",
        **fields: Any,
    ) -> dict:
        svc = _service()
        event = svc.events().get(calendarId=calendar_id, eventId=event_id).execute()
        # Apply only provided fields
        field_map = {
            "summary": "summary",
            "location": "location",
            "description": "description",
        }
        for key, value in fields.items():
            if key in field_map and value:
                event[field_map[key]] = value
        if "start_datetime" in fields and fields["start_datetime"]:
            event["start"]["dateTime"] = fields["start_datetime"]
        if "end_datetime" in fields and fields["end_datetime"]:
            event["end"]["dateTime"] = fields["end_datetime"]
        return svc.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()

    def delete_event(self, *, event_id: str, calendar_id: str = "primary") -> bool:
        svc = _service()
        svc.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return True


calendar_api = CalendarAPIAdapter()
