"""Confirmation policies — which tools require user approval and what risk level."""
from __future__ import annotations

from typing import Literal

# Tools that MUST have explicit confirmation before execution
CONFIRMATION_REQUIRED: set[str] = {
    "calendar.create_event",   # May send invites to attendees
    "calendar.delete_event",   # Irreversible
    "gmail.send_message",      # Sends real email — HIGH risk
    "gmail.reply_message",     # Sends real email
    "drive.delete_file",       # Irreversible
}

# Risk levels per tool
TOOL_RISK: dict[str, Literal["low", "medium", "high"]] = {
    # Read-only → low
    "calendar.list_events": "low",
    "gmail.search_messages": "low",
    "gmail.get_message": "low",
    "drive.list_files": "low",
    "drive.search_files": "low",
    # Write, reversible → medium
    "calendar.update_event": "medium",
    "calendar.create_event": "medium",
    "gmail.draft_message": "low",
    "drive.create_folder": "low",
    "drive.create_document": "low",
    # Write, irreversible / sends external comms → high
    "calendar.delete_event": "high",
    "gmail.send_message": "high",
    "gmail.reply_message": "high",
    "drive.delete_file": "high",
}

# Tools that prefer the API backend regardless of CLI availability
API_PREFERRED_TOOLS: set[str] = {
    "gmail.send_message",
    "gmail.reply_message",
    "gmail.draft_message",
    "drive.create_document",
}


def requires_confirmation(tool_name: str) -> bool:
    return tool_name in CONFIRMATION_REQUIRED


def risk_for_plan(tool_names: list[str]) -> Literal["low", "medium", "high"]:
    """Return the highest risk level across all tools in a plan."""
    levels = {"low": 0, "medium": 1, "high": 2}
    max_level = 0
    for tool in tool_names:
        level = levels.get(TOOL_RISK.get(tool, "low"), 0)
        max_level = max(max_level, level)
    return {0: "low", 1: "medium", 2: "high"}[max_level]


def plan_requires_confirmation(tool_names: list[str]) -> bool:
    return any(requires_confirmation(t) for t in tool_names)
