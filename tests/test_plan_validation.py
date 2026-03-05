"""Tests for plan validation and policy enforcement."""
from __future__ import annotations

import pytest

from core.models import Action, ActionArgs, ActionPlan
from core.policies import (
    plan_requires_confirmation,
    requires_confirmation,
    risk_for_plan,
)


def make_plan(tools: list[str], **kwargs) -> ActionPlan:
    return ActionPlan(
        intent="test",
        requires_confirmation=plan_requires_confirmation(tools),
        actions=[Action(tool=t, args=ActionArgs()) for t in tools],
        user_message_summary="test",
        risk_level=risk_for_plan(tools),
        **kwargs,
    )


class TestConfirmationPolicy:
    def test_send_email_requires_confirmation(self):
        assert requires_confirmation("gmail.send_message") is True

    def test_delete_event_requires_confirmation(self):
        assert requires_confirmation("calendar.delete_event") is True

    def test_list_events_no_confirmation(self):
        assert requires_confirmation("calendar.list_events") is False

    def test_search_drive_no_confirmation(self):
        assert requires_confirmation("drive.search_files") is False

    def test_plan_with_send_requires_confirmation(self):
        assert plan_requires_confirmation(["gmail.search_messages", "gmail.send_message"]) is True

    def test_plan_all_read_no_confirmation(self):
        assert plan_requires_confirmation(["calendar.list_events", "drive.list_files"]) is False


class TestRiskLevels:
    def test_read_only_is_low(self):
        assert risk_for_plan(["calendar.list_events", "gmail.search_messages"]) == "low"

    def test_create_event_is_medium(self):
        assert risk_for_plan(["calendar.create_event"]) == "medium"

    def test_send_email_is_high(self):
        assert risk_for_plan(["gmail.send_message"]) == "high"

    def test_mixed_takes_highest(self):
        # low + high = high
        assert risk_for_plan(["drive.list_files", "gmail.send_message"]) == "high"

    def test_unknown_tool_defaults_low(self):
        assert risk_for_plan(["unknown.tool"]) == "low"


class TestPlanValidity:
    def test_valid_calendar_namespace(self):
        plan = make_plan(["calendar.list_events"])
        assert plan.is_valid()

    def test_valid_gmail_namespace(self):
        plan = make_plan(["gmail.search_messages"])
        assert plan.is_valid()

    def test_valid_drive_namespace(self):
        plan = make_plan(["drive.search_files"])
        assert plan.is_valid()

    def test_invalid_namespace_rejected(self):
        plan = make_plan(["shell.exec"])
        assert not plan.is_valid()

    def test_mixed_valid_invalid(self):
        plan = make_plan(["calendar.list_events", "hack.inject"])
        assert not plan.is_valid()

    def test_dry_run_flag(self):
        plan = make_plan(["gmail.send_message"], dry_run=True)
        assert plan.dry_run is True
        assert plan.requires_confirmation is True  # policy still applies


class TestActionArgs:
    def test_calendar_args(self):
        args = ActionArgs(
            title="Team meeting",
            start="2024-01-16T10:00:00+01:00",
            end="2024-01-16T11:00:00+01:00",
            attendees=["alice@example.com"],
        )
        assert args.attendees == ["alice@example.com"]

    def test_gmail_args(self):
        args = ActionArgs(
            to=["bob@example.com"],
            subject="Hello",
            body="Hi there",
        )
        assert args.to[0] == "bob@example.com"

    def test_drive_args(self):
        args = ActionArgs(search_query="contract", max_results=5)
        assert args.max_results == 5
