"""
Platform-agnostic core pipeline.

Both Slack and Telegram (and any future adapter) call run() with two
platform-specific async callbacks:

  reply_fn(text)       — send a plain-text message back to the user
  confirm_fn(conf)     — present a confirmation UI (buttons) to the user

Everything else — planning, execution, audit logging — lives here.
"""
from __future__ import annotations

import os
import time
from typing import Awaitable, Callable

import structlog

from agent.executor import executor
from agent.planner import Planner, PlannerError
from core.confirmations import confirmation_store
from core.logging import audit_action
from core.models import ExecutionResult, PendingConfirmation
from core.security import sanitize_user_input
from tools.google_api.auth import google_auth

logger = structlog.get_logger()

# One shared planner instance
_planner = Planner()

ReplyFn = Callable[[str], Awaitable[None]]
ConfirmFn = Callable[[PendingConfirmation], Awaitable[None]]

OAUTH_PORT = os.environ.get("OAUTH_SERVER_PORT", "8080")


async def run_pipeline(
    *,
    message: str,
    user_id: str,
    channel_id: str,           # Slack channel or Telegram chat_id
    message_ref: str,          # Slack thread_ts or Telegram message_id (str)
    platform: str,             # "slack" | "telegram"
    reply_fn: ReplyFn,
    confirm_fn: ConfirmFn,
    dry_run: bool = False,
) -> None:
    """Core pipeline: message → plan → (confirm?) → execute → reply."""

    # ── Auth check ────────────────────────────────────────────────────────────
    if not google_auth.is_authenticated():
        await reply_fn(
            f"⚠️ Google-konto ikke forbundet.\n"
            f"Autentificer her: http://localhost:{OAUTH_PORT}/auth/google"
        )
        return

    clean = sanitize_user_input(message)
    t0 = time.monotonic()

    # ── Plan ──────────────────────────────────────────────────────────────────
    try:
        plan = await _planner.plan(clean, dry_run=dry_run)
    except PlannerError as exc:
        await reply_fn(f"❌ Kunne ikke forstå din besked: {exc}")
        audit_action(
            user_id=user_id, platform=platform,
            requested_action=clean[:200], errors=[str(exc)],
        )
        return

    # ── Follow-up question ────────────────────────────────────────────────────
    if plan.follow_up_question:
        await reply_fn(f"🤔 {plan.follow_up_question}")
        audit_action(
            user_id=user_id, platform=platform,
            requested_action=clean[:200], plan=plan, approved=None,
        )
        return

    # ── Dry run ───────────────────────────────────────────────────────────────
    if dry_run or plan.dry_run:
        result = await executor.run(plan)
        await reply_fn(result.summary)
        return

    # ── Confirmation required ─────────────────────────────────────────────────
    if plan.requires_confirmation:
        conf = PendingConfirmation(
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=message_ref,
            plan=plan,
        )
        confirmation_store.add(conf)
        await confirm_fn(conf)
        audit_action(
            user_id=user_id, platform=platform,
            requested_action=clean[:200], plan=plan, approved=None,
        )
        return

    # ── Execute immediately ───────────────────────────────────────────────────
    result = await executor.run(plan)
    duration_ms = (time.monotonic() - t0) * 1000

    await reply_fn(format_result(result))
    audit_action(
        user_id=user_id, platform=platform,
        requested_action=clean[:200],
        plan=plan, approved=True,
        executed_tools=[a.tool for a in plan.actions],
        errors=result.errors,
        duration_ms=duration_ms,
    )


def format_result(result: ExecutionResult) -> str:
    """Shared result formatter — used by both Slack and Telegram."""
    lines = [result.summary]
    if result.citations:
        lines.append("\nHandlinger udført:")
        for c in result.citations:
            lines.append(f"  • {c}")
    if result.errors:
        lines.append("\nFejl:")
        for e in result.errors:
            lines.append(f"  ⚠️ {e}")
    return "\n".join(lines)


def format_plan_text(conf: PendingConfirmation) -> str:
    """Plain-text plan summary for confirmation messages (both platforms)."""
    plan = conf.plan
    risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(plan.risk_level, "⚪")
    actions_lines = []
    for a in plan.actions:
        args = a.args
        detail = (
            args.title or args.query or args.subject
            or args.file_name or args.search_query or ""
        )
        actions_lines.append(f"  • {a.tool}" + (f": {detail}" if detail else ""))

    return (
        f"📋 Handlingsplan {risk_emoji}\n"
        f"Intent: {plan.intent}\n"
        f"Resumé: {plan.user_message_summary}\n"
        f"Handlinger:\n" + "\n".join(actions_lines) + "\n"
        f"Risikoniveau: {plan.risk_level}"
    )
