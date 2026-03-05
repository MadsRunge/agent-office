"""
Telegram event handlers.

Uses python-telegram-bot v21 (asyncio-native).

Supported:
  - Text messages (DM to bot)
  - Voice messages (.ogg/opus — Telegram's native format)
  - Audio file attachments (.mp3, .m4a, .wav, etc.)
  - Slash commands: /calendar, /gmail, /drive, /dryrun, /start, /help
  - InlineKeyboard confirmation buttons

Confirmation callback_data format (max 64 bytes):
  "confirm:<uuid>"  (44 chars — within limit)
  "cancel:<uuid>"   (43 chars — within limit)
"""
from __future__ import annotations

import io
import os
import time

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from agent.executor import executor
from agent.pipeline import format_plan_text, format_result, run_pipeline
from core.confirmations import confirmation_store
from core.logging import audit_action
from core.models import PendingConfirmation
from core.security import sanitize_user_input
from services.transcription.base import ALLOWED_AUDIO_MIME_TYPES
from services.transcription.whisper_cpp import whisper_provider

logger = structlog.get_logger()

OAUTH_PORT = os.environ.get("OAUTH_SERVER_PORT", "8080")

# ── /start + /help ────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Hej! Jeg er din Google Workspace-assistent.\n\n"
        "Du kan skrive direkte til mig eller bruge kommandoer:\n"
        "/calendar — kalender\n"
        "/gmail — email\n"
        "/drive — Google Drive\n"
        "/dryrun <besked> — vis plan uden at udføre\n"
        "/help — denne besked\n\n"
        "Du kan også sende stemmebeseder 🎙️\n\n"
        f"Google-konto: Autentificer via http://localhost:{OAUTH_PORT}/auth/google"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


# ── Text message handler ──────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)
    message_id = str(update.message.message_id)
    text = sanitize_user_input(update.message.text)

    dry_run = text.lower().startswith("dryrun:") or text.lower().startswith("dry run:")
    if dry_run:
        import re
        text = re.sub(r"^(?:dryrun|dry run)\s*:\s*", "", text, flags=re.IGNORECASE)

    await _pipeline(
        message=text,
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        update=update,
        dry_run=dry_run,
    )


# ── Slash commands ────────────────────────────────────────────────────────────

async def cmd_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = " ".join(context.args) if context.args else ""
    text = f"Kalender: {args}" if args else "Vis mine kommende kalenderbegivenheder"
    await _pipeline_from_update(update, text)


async def cmd_gmail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = " ".join(context.args) if context.args else ""
    text = f"Gmail: {args}" if args else "Vis mine seneste emails"
    await _pipeline_from_update(update, text)


async def cmd_drive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = " ".join(context.args) if context.args else ""
    text = f"Drive: {args}" if args else "Vis mine seneste Drive-filer"
    await _pipeline_from_update(update, text)


async def cmd_dryrun(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = " ".join(context.args) if context.args else ""
    if not args:
        await update.message.reply_text("Brug: /dryrun <din besked>")
        return
    await _pipeline_from_update(update, args, dry_run=True)


# ── Voice + audio file handler ────────────────────────────────────────────────

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Telegram voice messages (ogg/opus, recorded in-app)."""
    voice = update.message.voice
    if not voice:
        return

    mime_type = voice.mime_type or "audio/ogg"
    file_size = voice.file_size or 0
    duration = voice.duration  # seconds

    await update.message.reply_text(
        f"🎙️ Modtaget stemmebesked ({duration}s) — transskriberer…"
    )
    await _transcribe_and_run(
        update=update,
        context=context,
        file_id=voice.file_id,
        mime_type=mime_type,
        file_size=file_size,
    )


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle audio file attachments (.mp3, .m4a, .wav, etc.)."""
    audio = update.message.audio
    if not audio:
        return

    mime_type = audio.mime_type or "audio/mpeg"
    file_size = audio.file_size or 0

    if mime_type not in ALLOWED_AUDIO_MIME_TYPES and not mime_type.startswith("audio/"):
        await update.message.reply_text(
            f"⚠️ Ikke-understøttet lydformat: {mime_type}"
        )
        return

    await update.message.reply_text("🎙️ Modtaget lydfil — transskriberer…")
    await _transcribe_and_run(
        update=update,
        context=context,
        file_id=audio.file_id,
        mime_type=mime_type,
        file_size=file_size,
    )


async def _transcribe_and_run(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    mime_type: str,
    file_size: int,
) -> None:
    from services.transcription.base import MAX_AUDIO_SIZE_BYTES

    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)
    message_id = str(update.message.message_id)

    if file_size > MAX_AUDIO_SIZE_BYTES:
        mb = file_size / (1024 * 1024)
        await update.message.reply_text(f"⚠️ Filen er for stor: {mb:.1f} MB (maks 25 MB)")
        return

    try:
        tg_file = await context.bot.get_file(file_id)
        buf = io.BytesIO()
        await tg_file.download_to_memory(buf)
        audio_bytes = buf.getvalue()
    except Exception as exc:
        logger.error("telegram_audio_download_failed", error=str(exc))
        await update.message.reply_text(f"❌ Kunne ikke hente lydfilen: {exc}")
        return

    try:
        transcript = await whisper_provider.transcribe(audio_bytes, mime_type)
    except Exception as exc:
        await update.message.reply_text(f"❌ Transskribering fejlede: {exc}")
        audit_action(
            user_id=user_id, platform="telegram",
            requested_action="voice_transcription", errors=[str(exc)],
        )
        return

    await update.message.reply_text(f"🎙️ Transskriberet: _{transcript}_", parse_mode=ParseMode.MARKDOWN)

    await _pipeline(
        message=transcript,
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        update=update,
    )


# ── Confirmation button callbacks ─────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # stop the loading spinner

    data: str = query.data or ""
    user_id = str(update.effective_user.id)

    if data.startswith("confirm:"):
        conf_id = data[len("confirm:"):]
        conf = confirmation_store.get(conf_id)

        if not conf:
            await query.edit_message_text("⚠️ Bekræftelse er udløbet eller allerede behandlet.")
            return

        if conf.user_id != user_id:
            await query.answer(
                "⚠️ Kun den originale afsender kan bekræfte.", show_alert=True
            )
            return

        confirmation_store.remove(conf_id)
        await query.edit_message_text(
            text=format_plan_text(conf) + "\n\n⏳ Udfører…",
            reply_markup=None,
        )

        t0 = time.monotonic()
        result = await executor.run(conf.plan)
        duration_ms = (time.monotonic() - t0) * 1000

        await query.edit_message_text(text=format_result(result))
        audit_action(
            user_id=user_id, platform="telegram",
            requested_action=conf.plan.user_message_summary,
            plan=conf.plan, approved=True,
            executed_tools=[a.tool for a in conf.plan.actions],
            errors=result.errors,
            duration_ms=duration_ms,
        )

    elif data.startswith("cancel:"):
        conf_id = data[len("cancel:"):]
        confirmation_store.remove(conf_id)
        await query.edit_message_text("🚫 Handling annulleret.", reply_markup=None)
        audit_action(
            user_id=user_id, platform="telegram",
            requested_action="(bruger annullerede)", approved=False,
        )


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _pipeline_from_update(
    update: Update,
    message: str,
    dry_run: bool = False,
) -> None:
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)
    message_id = str(update.message.message_id)
    await _pipeline(
        message=message,
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        update=update,
        dry_run=dry_run,
    )


async def _pipeline(
    *,
    message: str,
    user_id: str,
    chat_id: str,
    message_id: str,
    update: Update,
    dry_run: bool = False,
) -> None:
    async def reply(text: str) -> None:
        await update.message.reply_text(text)

    async def confirm(conf: PendingConfirmation) -> None:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Bekræft", callback_data=f"confirm:{conf.id}"),
                InlineKeyboardButton("❌ Annuller", callback_data=f"cancel:{conf.id}"),
            ]
        ])
        await update.message.reply_text(
            text=format_plan_text(conf),
            reply_markup=keyboard,
        )

    await run_pipeline(
        message=message,
        user_id=user_id,
        channel_id=chat_id,
        message_ref=message_id,
        platform="telegram",
        reply_fn=reply,
        confirm_fn=confirm,
        dry_run=dry_run,
    )
