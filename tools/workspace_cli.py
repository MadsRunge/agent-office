"""
WorkspaceCLIAdapter — subprocess wrapper for the googleworkspace/cli (gws).

The `gws` CLI dynamically generates commands from Google Discovery API.
Command patterns:
  gws calendar events list   --calendarId=primary
  gws calendar events insert --calendarId=primary --summary=X --start.dateTime=ISO --end.dateTime=ISO
  gws calendar events patch  --calendarId=primary --eventId=X [--summary=Y ...]
  gws calendar events delete --calendarId=primary --eventId=X
  gws gmail users messages list --userId=me --q="from:x@y.com"
  gws gmail users messages get  --userId=me --id=MSG_ID
  gws drive files list --q="name contains 'contract'"
  gws drive files create --name=X --mimeType=Y

When CLI is unavailable, callers catch CLINotAvailableError and fall back to
the google_api adapters.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from typing import Any

import structlog

from core.models import CLIResult
from core.security import redact_tokens

logger = structlog.get_logger()

CLI_NAME = "gws"


class CLINotAvailableError(RuntimeError):
    """Raised when the gws CLI is not installed or not on PATH."""


class CLIExecutionError(RuntimeError):
    """Raised when a CLI command returns a non-zero exit code."""

    def __init__(self, result: CLIResult) -> None:
        super().__init__(f"CLI error (exit {result.exit_code}): {result.stderr[:200]}")
        self.result = result


class WorkspaceCLIAdapter:
    """Thin subprocess wrapper around the `gws` CLI."""

    _available: bool | None = None

    # ── Health ────────────────────────────────────────────────────────────────

    def check_installation(self) -> bool:
        """Return True if gws is on PATH and responds to --version."""
        if self._available is not None:
            return self._available
        if shutil.which(CLI_NAME) is None:
            self._available = False
            return False
        try:
            r = subprocess.run(
                [CLI_NAME, "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self._available = r.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            self._available = False
        return self._available  # type: ignore[return-value]

    def get_version(self) -> str:
        result = self.run(["version"], timeout=10)
        return result.stdout.strip()

    def assert_available(self) -> None:
        if not self.check_installation():
            raise CLINotAvailableError(
                f"'{CLI_NAME}' is not installed or not on PATH. "
                "Install it from https://github.com/googleworkspace/cli"
            )

    # ── Core runner ───────────────────────────────────────────────────────────

    def run(self, args: list[str], timeout: int = 30) -> CLIResult:
        """Execute `gws <args>` and return a CLIResult.

        Args are passed as a list — never via shell=True — to prevent injection.
        """
        self.assert_available()
        cmd = [CLI_NAME] + args
        redacted_cmd = [CLI_NAME] + self._redact_args(args)

        logger.debug("cli_run", command=redacted_cmd)
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"CLI command timed out after {timeout}s: {redacted_cmd}") from exc
        except FileNotFoundError as exc:
            raise CLINotAvailableError(f"'{CLI_NAME}' not found") from exc

        duration_ms = (time.monotonic() - t0) * 1000
        result = CLIResult(
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            command=redacted_cmd,
            duration_ms=duration_ms,
        )
        logger.debug(
            "cli_result",
            exit_code=result.exit_code,
            duration_ms=round(duration_ms, 1),
            stderr=result.stderr[:200] if result.stderr else "",
        )
        if not result.success:
            raise CLIExecutionError(result)
        return result

    # ── Capabilities ──────────────────────────────────────────────────────────

    @property
    def capabilities(self) -> dict[str, bool]:
        """Report which tool families are available via CLI."""
        avail = self.check_installation()
        return {
            "calendar.list_events": avail,
            "calendar.create_event": avail,
            "calendar.update_event": avail,
            "calendar.delete_event": avail,
            "gmail.search_messages": avail,
            "gmail.get_message": avail,
            # Send/draft require MIME construction → prefer API
            "gmail.draft_message": False,
            "gmail.send_message": False,
            "gmail.reply_message": False,
            "drive.list_files": avail,
            "drive.search_files": avail,
            # Binary upload / Doc creation → prefer API
            "drive.create_document": False,
            "drive.create_folder": avail,
        }

    def can_handle(self, tool_name: str) -> bool:
        return self.capabilities.get(tool_name, False)

    # ── Calendar commands ─────────────────────────────────────────────────────

    def calendar_list_events(
        self,
        calendar_id: str = "primary",
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 10,
    ) -> list[dict]:
        args = [
            "calendar", "events", "list",
            f"--calendarId={calendar_id}",
            f"--maxResults={max_results}",
            "--singleEvents=true",
            "--orderBy=startTime",
        ]
        if time_min:
            args.append(f"--timeMin={time_min}")
        if time_max:
            args.append(f"--timeMax={time_max}")
        result = self.run(args)
        data = result.as_json() or {}
        return data.get("items", [])

    def calendar_create_event(
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
        args = [
            "calendar", "events", "insert",
            f"--calendarId={calendar_id}",
            f"--summary={summary}",
            f"--start.dateTime={start_datetime}",
            f"--start.timeZone={timezone}",
            f"--end.dateTime={end_datetime}",
            f"--end.timeZone={timezone}",
        ]
        if location:
            args.append(f"--location={location}")
        if description:
            args.append(f"--description={description}")
        if attendees:
            # gws expects repeated --attendees.email flags
            for email in attendees:
                args.append(f"--attendees.email={email}")
        result = self.run(args)
        return result.as_json() or {}

    def calendar_update_event(
        self,
        *,
        event_id: str,
        calendar_id: str = "primary",
        **fields: Any,
    ) -> dict:
        args = [
            "calendar", "events", "patch",
            f"--calendarId={calendar_id}",
            f"--eventId={event_id}",
        ]
        # Map common fields to CLI flags
        flag_map = {
            "summary": "--summary",
            "location": "--location",
            "description": "--description",
            "start_datetime": "--start.dateTime",
            "end_datetime": "--end.dateTime",
        }
        for key, value in fields.items():
            flag = flag_map.get(key)
            if flag and value:
                args.append(f"{flag}={value}")
        result = self.run(args)
        return result.as_json() or {}

    def calendar_delete_event(
        self,
        *,
        event_id: str,
        calendar_id: str = "primary",
    ) -> bool:
        self.run([
            "calendar", "events", "delete",
            f"--calendarId={calendar_id}",
            f"--eventId={event_id}",
        ])
        return True  # 204 no content on success

    # ── Gmail commands ────────────────────────────────────────────────────────

    def gmail_search_messages(
        self,
        query: str,
        max_results: int = 10,
        user_id: str = "me",
    ) -> list[dict]:
        args = [
            "gmail", "users", "messages", "list",
            f"--userId={user_id}",
            f"--q={query}",
            f"--maxResults={max_results}",
        ]
        result = self.run(args)
        data = result.as_json() or {}
        return data.get("messages", [])

    def gmail_get_message(
        self,
        message_id: str,
        user_id: str = "me",
    ) -> dict:
        args = [
            "gmail", "users", "messages", "get",
            f"--userId={user_id}",
            f"--id={message_id}",
            "--format=full",
        ]
        result = self.run(args)
        return result.as_json() or {}

    # ── Drive commands ────────────────────────────────────────────────────────

    def drive_list_files(
        self,
        query: str | None = None,
        max_results: int = 10,
    ) -> list[dict]:
        args = [
            "drive", "files", "list",
            f"--pageSize={max_results}",
            "--fields=files(id,name,mimeType,modifiedTime,webViewLink)",
        ]
        if query:
            args.append(f"--q={query}")
        result = self.run(args)
        data = result.as_json() or {}
        return data.get("files", [])

    def drive_create_folder(
        self,
        name: str,
        parent_id: str | None = None,
    ) -> dict:
        args = [
            "drive", "files", "create",
            f"--name={name}",
            "--mimeType=application/vnd.google-apps.folder",
            "--fields=id,name,webViewLink",
        ]
        if parent_id:
            args.append(f"--parents={parent_id}")
        result = self.run(args)
        return result.as_json() or {}

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _redact_args(args: list[str]) -> list[str]:
        """Return a copy of args with sensitive values redacted for logging."""
        redacted = []
        for arg in args:
            redacted.append(redact_tokens(arg))
        return redacted


# Singleton
workspace_cli = WorkspaceCLIAdapter()
