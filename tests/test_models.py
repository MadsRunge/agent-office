"""Tests for Pydantic models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models import Action, ActionArgs, ActionPlan, CLIResult, ToolResult


class TestActionArgs:
    def test_defaults(self):
        args = ActionArgs()
        assert args.timezone == "Europe/Copenhagen"
        assert args.calendar_id == "primary"
        assert args.max_results == 10

    def test_extra_fields_allowed(self):
        args = ActionArgs(custom_field="hello")
        assert args.model_extra["custom_field"] == "hello"

    def test_iso_start_end(self):
        args = ActionArgs(start="2024-01-16T10:00:00+01:00", end="2024-01-16T11:00:00+01:00")
        assert "2024" in args.start


class TestActionPlan:
    def _make_plan(self, **kwargs) -> ActionPlan:
        defaults = {
            "intent": "list_events",
            "requires_confirmation": False,
            "actions": [Action(tool="calendar.list_events", args=ActionArgs())],
            "user_message_summary": "List today's events",
            "risk_level": "low",
        }
        defaults.update(kwargs)
        return ActionPlan(**defaults)

    def test_valid_plan(self):
        plan = self._make_plan()
        assert plan.is_valid()

    def test_invalid_namespace(self):
        plan = self._make_plan(
            actions=[Action(tool="unknown.do_thing", args=ActionArgs())]
        )
        assert not plan.is_valid()

    def test_requires_at_least_one_action(self):
        with pytest.raises(ValidationError):
            ActionPlan(
                intent="x",
                requires_confirmation=False,
                actions=[],
                user_message_summary="",
                risk_level="low",
            )

    def test_risk_level_enum(self):
        with pytest.raises(ValidationError):
            self._make_plan(risk_level="extreme")


class TestCLIResult:
    def test_success(self):
        r = CLIResult(stdout='{"items":[]}', stderr="", exit_code=0, command=["gws", "cal"], duration_ms=50)
        assert r.success is True

    def test_failure(self):
        r = CLIResult(stdout="", stderr="error", exit_code=1, command=["gws"], duration_ms=10)
        assert r.success is False

    def test_as_json(self):
        r = CLIResult(stdout='{"key": "value"}', stderr="", exit_code=0, command=[], duration_ms=0)
        assert r.as_json() == {"key": "value"}

    def test_as_json_invalid(self):
        r = CLIResult(stdout="not json", stderr="", exit_code=0, command=[], duration_ms=0)
        assert r.as_json() is None


class TestToolResult:
    def test_success_result(self):
        r = ToolResult(success=True, tool_name="calendar.list_events", data=[], source="cli")
        assert r.success
        assert r.error is None

    def test_error_result(self):
        r = ToolResult(success=False, tool_name="gmail.send_message", error="auth failed", source="api")
        assert not r.success
        assert "auth" in r.error
