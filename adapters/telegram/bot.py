"""
Telegram bot — python-telegram-bot v21 (asyncio-native).

Uses long-polling for local dev (no public URL or webhook needed).
Set TELEGRAM_WEBHOOK_URL + TELEGRAM_WEBHOOK_PORT to switch to webhook mode.

Setup:
  1. Chat with @BotFather on Telegram → /newbot → get token
  2. Set TELEGRAM_BOT_TOKEN in .env
  3. Optionally: /setcommands in BotFather to register slash commands
"""
from __future__ import annotations

import os

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from adapters.telegram.handlers import (
    cmd_calendar,
    cmd_dryrun,
    cmd_gmail,
    cmd_drive,
    cmd_help,
    cmd_start,
    handle_audio,
    handle_callback,
    handle_message,
    handle_voice,
)


def create_telegram_app() -> Application:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    # ── Commands ──────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("calendar", cmd_calendar))
    app.add_handler(CommandHandler("gmail", cmd_gmail))
    app.add_handler(CommandHandler("drive", cmd_drive))
    app.add_handler(CommandHandler("dryrun", cmd_dryrun))

    # ── Voice + audio ─────────────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.AUDIO, handle_audio))

    # ── Inline keyboard callbacks ─────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(handle_callback))

    # ── Text messages (must be last — most permissive) ────────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app
