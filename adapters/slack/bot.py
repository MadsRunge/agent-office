"""
Slack Bolt application setup.

Uses Socket Mode for local development (no public URL needed).
Set SLACK_MODE=http to switch to HTTP mode for production.
"""
from __future__ import annotations

import os

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from adapters.slack.handlers import (
    handle_action,
    handle_file_shared,
    handle_message,
    handle_slash_calendar,
    handle_slash_drive,
    handle_slash_dryrun,
    handle_slash_gmail,
)


def create_slack_app() -> tuple[AsyncApp, AsyncSocketModeHandler]:
    app = AsyncApp(token=os.environ["SLACK_BOT_TOKEN"])

    # ── Message events ────────────────────────────────────────────────────────
    # DMs and app mentions
    @app.event("message")
    async def on_message(body, say, client):
        await handle_message(body, say, client)

    @app.event("app_mention")
    async def on_mention(body, say, client):
        await handle_message(body, say, client)

    # ── File events (voice notes) ─────────────────────────────────────────────
    @app.event("file_shared")
    async def on_file_shared(body, client, say):
        await handle_file_shared(body, client, say)

    # ── Slash commands ────────────────────────────────────────────────────────
    @app.command("/calendar")
    async def on_slash_calendar(body, ack, say, client):
        await handle_slash_calendar(body, ack, say, client)

    @app.command("/gmail")
    async def on_slash_gmail(body, ack, say, client):
        await handle_slash_gmail(body, ack, say, client)

    @app.command("/drive")
    async def on_slash_drive(body, ack, say, client):
        await handle_slash_drive(body, ack, say, client)

    @app.command("/dryrun")
    async def on_slash_dryrun(body, ack, say, client):
        await handle_slash_dryrun(body, ack, say, client)

    # ── Block Kit button actions ──────────────────────────────────────────────
    @app.action({"action_id": {"starts_with": "confirm_action:"}})
    async def on_confirm(body, ack, client, say):
        await handle_action(body, ack, client, say)

    @app.action({"action_id": {"starts_with": "cancel_action:"}})
    async def on_cancel(body, ack, client, say):
        await handle_action(body, ack, client, say)

    handler = AsyncSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    return app, handler
