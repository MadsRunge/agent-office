"""Tests for the WorkspaceCLIAdapter (subprocess mocked)."""
from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from core.models import CLIResult
from tools.workspace_cli import (
    CLIExecutionError,
    CLINotAvailableError,
    WorkspaceCLIAdapter,
)


def _mock_result(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = returncode
    return m


@pytest.fixture
def adapter() -> WorkspaceCLIAdapter:
    a = WorkspaceCLIAdapter()
    a._available = True  # Skip actual binary check
    return a


class TestCheckInstallation:
    def test_installed(self):
        adapter = WorkspaceCLIAdapter()
        adapter._available = None
        with (
            patch("shutil.which", return_value="/usr/local/bin/gws"),
            patch("subprocess.run", return_value=_mock_result(returncode=0)),
        ):
            assert adapter.check_installation() is True

    def test_not_installed(self):
        adapter = WorkspaceCLIAdapter()
        adapter._available = None
        with patch("shutil.which", return_value=None):
            assert adapter.check_installation() is False

    def test_cached(self):
        adapter = WorkspaceCLIAdapter()
        adapter._available = True
        # Should not call subprocess at all
        assert adapter.check_installation() is True


class TestRunCommand:
    def test_success(self, adapter):
        payload = {"items": [{"id": "1", "summary": "Test"}]}
        with patch("subprocess.run", return_value=_mock_result(stdout=json.dumps(payload))):
            result = adapter.run(["calendar", "events", "list"])
        assert result.success
        assert result.as_json() == payload

    def test_nonzero_exit_raises(self, adapter):
        with patch("subprocess.run", return_value=_mock_result(returncode=1, stderr="auth error")):
            with pytest.raises(CLIExecutionError) as exc_info:
                adapter.run(["calendar", "events", "list"])
        assert "auth error" in str(exc_info.value)

    def test_timeout_raises(self, adapter):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="gws", timeout=30)):
            with pytest.raises(TimeoutError):
                adapter.run(["calendar", "events", "list"], timeout=30)

    def test_not_available_raises(self):
        adapter = WorkspaceCLIAdapter()
        adapter._available = False
        with pytest.raises(CLINotAvailableError):
            adapter.run(["calendar", "events", "list"])


class TestCalendarCommands:
    def test_list_events(self, adapter):
        payload = {"items": [{"id": "abc", "summary": "Dentist"}]}
        with patch("subprocess.run", return_value=_mock_result(stdout=json.dumps(payload))):
            items = adapter.calendar_list_events(calendar_id="primary", max_results=5)
        assert len(items) == 1
        assert items[0]["summary"] == "Dentist"

    def test_create_event(self, adapter):
        payload = {"id": "xyz", "summary": "Team meeting", "htmlLink": "https://cal.google.com/x"}
        with patch("subprocess.run", return_value=_mock_result(stdout=json.dumps(payload))):
            result = adapter.calendar_create_event(
                summary="Team meeting",
                start_datetime="2024-01-16T10:00:00+01:00",
                end_datetime="2024-01-16T11:00:00+01:00",
            )
        assert result["id"] == "xyz"

    def test_delete_event(self, adapter):
        with patch("subprocess.run", return_value=_mock_result(stdout="")):
            ok = adapter.calendar_delete_event(event_id="xyz")
        assert ok is True


class TestRedactArgs:
    def test_redacts_token(self):
        args = ["--token=secret123", "--calendarId=primary"]
        redacted = WorkspaceCLIAdapter._redact_args(args)
        assert "secret123" not in " ".join(redacted)
        assert "primary" in " ".join(redacted)


class TestCapabilities:
    def test_available_capabilities(self):
        adapter = WorkspaceCLIAdapter()
        adapter._available = True
        caps = adapter.capabilities
        assert caps["calendar.list_events"] is True
        assert caps["gmail.send_message"] is False   # Always API
        assert caps["drive.create_document"] is False  # Always API

    def test_unavailable_all_false(self):
        adapter = WorkspaceCLIAdapter()
        adapter._available = False
        caps = adapter.capabilities
        assert all(not v for v in caps.values())
