"""
Agent Office — main entrypoint.

Starts concurrently:
  1. FastAPI OAuth callback server  (port 8080, background thread)
  2. Slack Bolt bot                 (Socket Mode, asyncio task)  [if SLACK_BOT_TOKEN set]
  3. Telegram bot                   (polling,     asyncio task)  [if TELEGRAM_BOT_TOKEN set]

Run:
  uv run python main.py
"""
from __future__ import annotations

import asyncio
import os
import threading

import structlog
import uvicorn
from dotenv import load_dotenv

load_dotenv()

logger = structlog.get_logger()


# ── OAuth server (background thread) ─────────────────────────────────────────

def _start_oauth_server() -> None:
    from auth.oauth_server import create_oauth_app
    oauth_app = create_oauth_app()
    host = os.environ.get("OAUTH_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("OAUTH_SERVER_PORT", "8080"))
    logger.info("oauth_server_starting", host=host, port=port)
    uvicorn.run(oauth_app, host=host, port=port, log_level="warning")


# ── Tool registration ─────────────────────────────────────────────────────────

def _register_tools() -> None:
    from services.calendar import calendar_service
    from services.gmail import gmail_service
    from services.drive import drive_service
    from tools.registry import registry

    registry.register("calendar.list_events", calendar_service.list_events)
    registry.register("calendar.create_event", calendar_service.create_event)
    registry.register("calendar.update_event", calendar_service.update_event)
    registry.register("calendar.delete_event", calendar_service.delete_event)

    registry.register("gmail.search_messages", gmail_service.search_messages)
    registry.register("gmail.get_message", gmail_service.get_message)
    registry.register("gmail.draft_message", gmail_service.draft_message)
    registry.register("gmail.send_message", gmail_service.send_message)
    registry.register("gmail.reply_message", gmail_service.reply_message)

    registry.register("drive.list_files", drive_service.list_files)
    registry.register("drive.search_files", drive_service.search_files)
    registry.register("drive.create_folder", drive_service.create_folder)
    registry.register("drive.create_document", drive_service.create_document)

    logger.info("tools_registered", count=len(registry.registered_tools()))


# ── CLI availability check ────────────────────────────────────────────────────

def _check_cli() -> None:
    from tools.workspace_cli import workspace_cli
    if workspace_cli.check_installation():
        version = workspace_cli.get_version()
        logger.info("gws_cli_available", version=version)
    else:
        logger.warning(
            "gws_cli_not_found",
            message="'gws' CLI not installed — using Google API directly. "
                    "Install from https://github.com/googleworkspace/cli",
        )


# ── Platform bots ─────────────────────────────────────────────────────────────

async def _start_slack() -> None:
    if not os.environ.get("SLACK_BOT_TOKEN"):
        logger.info("slack_disabled", reason="SLACK_BOT_TOKEN not set")
        return
    from adapters.slack.bot import create_slack_app
    _, handler = create_slack_app()
    logger.info("slack_bot_starting", mode="socket_mode")
    await handler.start_async()


async def _start_telegram() -> None:
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        logger.info("telegram_disabled", reason="TELEGRAM_BOT_TOKEN not set")
        return
    from adapters.telegram.bot import create_telegram_app
    app = create_telegram_app()
    logger.info("telegram_bot_starting", mode="polling")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        # Run until cancelled
        await asyncio.Event().wait()


# ── Entry point ───────────────────────────────────────────────────────────────

async def _main_async() -> None:
    tasks = []
    slack_token = os.environ.get("SLACK_BOT_TOKEN")
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not slack_token and not telegram_token:
        logger.error(
            "no_platform_configured",
            message="Set at least one of: SLACK_BOT_TOKEN, TELEGRAM_BOT_TOKEN",
        )
        return

    if slack_token:
        tasks.append(asyncio.create_task(_start_slack(), name="slack"))
    if telegram_token:
        tasks.append(asyncio.create_task(_start_telegram(), name="telegram"))

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        for t in tasks:
            t.cancel()


def main() -> None:
    _check_cli()
    _register_tools()

    # OAuth server in background thread
    oauth_thread = threading.Thread(
        target=_start_oauth_server, daemon=True, name="oauth-server"
    )
    oauth_thread.start()

    platforms = [
        p for p, key in [("Slack", "SLACK_BOT_TOKEN"), ("Telegram", "TELEGRAM_BOT_TOKEN")]
        if os.environ.get(key)
    ]
    logger.info("agent_office_starting", platforms=platforms)

    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
