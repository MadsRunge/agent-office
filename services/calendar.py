"""
CalendarService — business logic layer.

Tries gws CLI first; if unavailable or the specific operation isn't supported
by the CLI, falls back to the Google Calendar API adapter transparently.
"""
from __future__ import annotations

from core.models import ActionArgs, ToolResult
from tools.google_api.calendar import calendar_api
from tools.workspace_cli import CLINotAvailableError, CLIExecutionError, workspace_cli


def _cli_available(tool: str) -> bool:
    return workspace_cli.can_handle(tool)


class CalendarService:

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_events(self, args: ActionArgs) -> ToolResult:
        tool = "calendar.list_events"
        try:
            if _cli_available(tool):
                items = workspace_cli.calendar_list_events(
                    calendar_id=args.calendar_id or "primary",
                    time_min=args.time_min,
                    time_max=args.time_max,
                    max_results=args.max_results or 10,
                )
                return ToolResult(success=True, tool_name=tool, data=items, source="cli")
        except (CLINotAvailableError, CLIExecutionError):
            pass

        # API fallback
        try:
            items = calendar_api.list_events(
                calendar_id=args.calendar_id or "primary",
                time_min=args.time_min,
                time_max=args.time_max,
                max_results=args.max_results or 10,
            )
            return ToolResult(success=True, tool_name=tool, data=items, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_event(self, args: ActionArgs) -> ToolResult:
        tool = "calendar.create_event"
        if not args.title or not args.start or not args.end:
            return ToolResult(
                success=False, tool_name=tool,
                error="Missing required fields: title, start, end",
                source="mock",
            )
        try:
            if _cli_available(tool):
                data = workspace_cli.calendar_create_event(
                    calendar_id=args.calendar_id or "primary",
                    summary=args.title,
                    start_datetime=args.start,
                    end_datetime=args.end,
                    timezone=args.timezone or "Europe/Copenhagen",
                    attendees=args.attendees,
                    location=args.location,
                    description=args.description,
                )
                return ToolResult(success=True, tool_name=tool, data=data, source="cli")
        except (CLINotAvailableError, CLIExecutionError):
            pass

        try:
            data = calendar_api.create_event(
                calendar_id=args.calendar_id or "primary",
                summary=args.title,
                start_datetime=args.start,
                end_datetime=args.end,
                timezone=args.timezone or "Europe/Copenhagen",
                attendees=args.attendees,
                location=args.location,
                description=args.description,
            )
            return ToolResult(success=True, tool_name=tool, data=data, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_event(self, args: ActionArgs) -> ToolResult:
        tool = "calendar.update_event"
        if not args.event_id:
            return ToolResult(
                success=False, tool_name=tool, error="event_id is required", source="mock"
            )
        fields = {}
        for attr in ("title", "location", "description", "start", "end"):
            val = getattr(args, attr, None)
            if val:
                key = "summary" if attr == "title" else attr
                fields[key] = val

        try:
            if _cli_available(tool):
                data = workspace_cli.calendar_update_event(
                    event_id=args.event_id,
                    calendar_id=args.calendar_id or "primary",
                    **fields,
                )
                return ToolResult(success=True, tool_name=tool, data=data, source="cli")
        except (CLINotAvailableError, CLIExecutionError):
            pass

        try:
            data = calendar_api.update_event(
                event_id=args.event_id,
                calendar_id=args.calendar_id or "primary",
                **fields,
            )
            return ToolResult(success=True, tool_name=tool, data=data, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_event(self, args: ActionArgs) -> ToolResult:
        tool = "calendar.delete_event"
        if not args.event_id:
            return ToolResult(
                success=False, tool_name=tool, error="event_id is required", source="mock"
            )
        try:
            if _cli_available(tool):
                workspace_cli.calendar_delete_event(
                    event_id=args.event_id,
                    calendar_id=args.calendar_id or "primary",
                )
                return ToolResult(success=True, tool_name=tool, data={"deleted": True}, source="cli")
        except (CLINotAvailableError, CLIExecutionError):
            pass

        try:
            calendar_api.delete_event(
                event_id=args.event_id,
                calendar_id=args.calendar_id or "primary",
            )
            return ToolResult(success=True, tool_name=tool, data={"deleted": True}, source="api")
        except Exception as exc:
            return ToolResult(success=False, tool_name=tool, error=str(exc), source="api")


calendar_service = CalendarService()
