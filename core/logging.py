"""Structured audit logging via structlog → audit.jsonl."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import structlog

from core.models import AuditEntry

# ── structlog configuration ───────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

AUDIT_LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", "audit.jsonl"))


def _write_audit(entry: AuditEntry) -> None:
    """Append a single audit entry as a JSON line."""
    try:
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")
    except OSError as exc:
        logger.error("audit_write_failed", error=str(exc))


def audit_action(
    *,
    user_id: str,
    platform: str,
    requested_action: str,
    plan=None,
    approved: bool | None = None,
    executed_tools: list[str] | None = None,
    errors: list[str] | None = None,
    dry_run: bool = False,
    duration_ms: float | None = None,
) -> None:
    entry = AuditEntry(
        user_id=user_id,
        platform=platform,
        requested_action=requested_action,
        plan=plan,
        approved=approved,
        executed_tools=executed_tools or [],
        errors=errors or [],
        dry_run=dry_run,
        duration_ms=duration_ms,
    )
    _write_audit(entry)
    logger.info(
        "audit",
        user_id=user_id,
        platform=platform,
        action=requested_action,
        approved=approved,
        dry_run=dry_run,
        tools=executed_tools or [],
        errors=errors or [],
    )


def get_audit_log(limit: int = 50) -> list[dict]:
    """Read the last `limit` audit entries (newest first)."""
    if not AUDIT_LOG_PATH.exists():
        return []
    lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    entries = []
    for line in reversed(lines[-limit:]):
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries
