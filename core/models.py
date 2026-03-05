"""All Pydantic v2 models for agent-office."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── CLI adapter ───────────────────────────────────────────────────────────────

class CLIResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    command: list[str]
    duration_ms: float

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    def as_json(self) -> Optional[dict]:
        import json
        try:
            return json.loads(self.stdout)
        except (json.JSONDecodeError, ValueError):
            return None


# ── Action plan ───────────────────────────────────────────────────────────────

class ActionArgs(BaseModel):
    """Flexible args bag for any tool call. Extra fields allowed for extensibility."""
    model_config = ConfigDict(extra="allow")

    # Calendar
    title: Optional[str] = None
    start: Optional[str] = None          # ISO 8601
    end: Optional[str] = None            # ISO 8601
    timezone: Optional[str] = "Europe/Copenhagen"
    attendees: Optional[list[str]] = None
    location: Optional[str] = None
    description: Optional[str] = None
    event_id: Optional[str] = None
    calendar_id: Optional[str] = "primary"
    max_results: Optional[int] = 10
    time_min: Optional[str] = None       # ISO 8601, for list range
    time_max: Optional[str] = None       # ISO 8601, for list range

    # Gmail
    to: Optional[list[str]] = None
    cc: Optional[list[str]] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    query: Optional[str] = None
    message_id: Optional[str] = None
    thread_id: Optional[str] = None
    user_id: Optional[str] = "me"

    # Drive
    file_name: Optional[str] = None
    folder_name: Optional[str] = None
    search_query: Optional[str] = None
    mime_type: Optional[str] = None
    parent_id: Optional[str] = None
    file_content: Optional[str] = None


class Action(BaseModel):
    tool: str = Field(..., description="Dot-namespaced tool: 'calendar.create_event'")
    args: ActionArgs


class ActionPlan(BaseModel):
    intent: str
    requires_confirmation: bool
    actions: list[Action] = Field(..., min_length=1)
    user_message_summary: str
    risk_level: Literal["low", "medium", "high"]
    follow_up_question: Optional[str] = None
    dry_run: bool = False

    def is_valid(self) -> bool:
        """All actions reference a known tool namespace."""
        valid_namespaces = {"calendar", "gmail", "drive"}
        for action in self.actions:
            ns = action.tool.split(".")[0]
            if ns not in valid_namespaces:
                return False
        return True


# ── Tool execution ────────────────────────────────────────────────────────────

class ToolResult(BaseModel):
    success: bool
    tool_name: str
    data: Any = None
    error: Optional[str] = None
    source: Literal["cli", "api", "mock"]
    raw_response: Optional[dict] = None


class ExecutionResult(BaseModel):
    plan: ActionPlan
    results: list[ToolResult]
    summary: str
    citations: list[str]          # human-readable "what was touched"
    errors: list[str]

    @property
    def all_succeeded(self) -> bool:
        return all(r.success for r in self.results)


# ── Confirmation flow ─────────────────────────────────────────────────────────

class PendingConfirmation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    channel_id: str
    thread_ts: str
    plan: ActionPlan
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(
        default_factory=lambda: datetime.utcnow() + timedelta(seconds=300)
    )

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


# ── Audit log ─────────────────────────────────────────────────────────────────

class AuditEntry(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: str
    platform: str
    requested_action: str
    plan: Optional[ActionPlan] = None
    approved: Optional[bool] = None
    executed_tools: list[str] = []
    errors: list[str] = []
    dry_run: bool = False
    duration_ms: Optional[float] = None
