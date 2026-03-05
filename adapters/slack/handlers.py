"""
Slack event handlers — wired up in bot.py.

Delegates core pipeline logic to agent/pipeline.py.
Platform-specific concerns here:
  - Extracting user/channel/text from Slack event payloads
  - Formatting Block Kit confirmation messages
  - Handling button action callbacks
  - Downloading audio files from Slack
"""
from __future__ import annotations

import os
import re
import time

import structlog

from adapters.slack.voice import download_slack_file, transcribe_audio
from agent.executor import executor
from agent.pipeline import format_plan_text, format_result, run_pipeline
from core.confirmations import confirmation_store
from core.logging import audit_action
from core.models import PendingConfirmation
from core.security import sanitize_user_input

logger = structlog.get_logger()


# ── Text message handler ──────────────────────────────────────────────────────

async def handle_message(body: dict, say, client) -> None:
    event = body.get("event", {})
    if event.get("bot_id"):
        return

    user_id = event.get("user", "unknown")
    channel_id = event.get("channel", "")
    ts = event.get("ts", "")
    text = re.sub(r"<@\w+>\s*", "", event.get("text", "")).strip()
    if not text:
        return

    clean = sanitize_user_input(text)
    dry_run = bool(re.match(r"^(?:dryrun|dry run)\s*:", clean, re.IGNORECASE))
    if dry_run:
        clean = re.sub(r"^(?:dryrun|dry run)\s*:\s*", "", clean, flags=re.IGNORECASE)

    async def reply(msg: str) -> None:
        await say(text=msg, thread_ts=ts)

    async def confirm(conf: PendingConfirmation) -> None:
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=ts,
            blocks=_build_confirmation_blocks(conf),
            text=f"Handling kræver bekræftelse: {conf.plan.user_message_summary}",
        )

    await run_pipeline(
        message=clean,
        user_id=user_id,
        channel_id=channel_id,
        message_ref=ts,
        platform="slack",
        reply_fn=reply,
        confirm_fn=confirm,
        dry_run=dry_run,
    )


# ── Slash commands ────────────────────────────────────────────────────────────

async def handle_slash_calendar(body: dict, ack, say, client) -> None:
    await ack()
    await _slash_pipeline(body, say, client, prefix="Kalender")


async def handle_slash_gmail(body: dict, ack, say, client) -> None:
    await ack()
    await _slash_pipeline(body, say, client, prefix="Gmail")


async def handle_slash_drive(body: dict, ack, say, client) -> None:
    await ack()
    await _slash_pipeline(body, say, client, prefix="Drive")


async def handle_slash_dryrun(body: dict, ack, say, client) -> None:
    await ack()
    text = sanitize_user_input(body.get("text", "").strip())
    if not text:
        await say(text="Brug: /dryrun <din besked>")
        return
    await _slash_pipeline(body, say, client, prefix="", dry_run=True)


async def _slash_pipeline(
    body: dict,
    say,
    client,
    prefix: str = "",
    dry_run: bool = False,
) -> None:
    text = sanitize_user_input(body.get("text", "").strip())
    user_id = body.get("user_id", "unknown")
    channel_id = body.get("channel_id", "")
    message = f"{prefix}: {text}" if prefix and text else text or f"Vis mine {prefix.lower()}"

    async def reply(msg: str) -> None:
        await say(text=msg)

    async def confirm(conf: PendingConfirmation) -> None:
        await client.chat_postMessage(
            channel=channel_id,
            blocks=_build_confirmation_blocks(conf),
            text=f"Handling kræver bekræftelse: {conf.plan.user_message_summary}",
        )

    await run_pipeline(
        message=message,
        user_id=user_id,
        channel_id=channel_id,
        message_ref="",
        platform="slack",
        reply_fn=reply,
        confirm_fn=confirm,
        dry_run=dry_run,
    )


# ── Voice note handler ────────────────────────────────────────────────────────

async def handle_file_shared(body: dict, client, say) -> None:
    event = body.get("event", {})
    user_id = event.get("user_id", event.get("user", "unknown"))
    channel_id = event.get("channel_id", event.get("channel", ""))
    file_id = event.get("file_id") or event.get("file", {}).get("id")
    if not file_id:
        return

    try:
        file_resp = await client.files_info(file=file_id)
        file_info = file_resp["file"]
    except Exception as exc:
        logger.error("slack_file_info_failed", error=str(exc))
        return

    mimetype = file_info.get("mimetype", "")
    filetype = file_info.get("filetype", "")
    if not (mimetype.startswith("audio/") or filetype in {"m4a", "mp3", "wav", "ogg", "webm"}):
        return

    try:
        audio_bytes, resolved_mime = await download_slack_file(
            file_info, os.environ["SLACK_BOT_TOKEN"]
        )
    except ValueError as exc:
        await client.chat_postMessage(channel=channel_id, text=f"⚠️ Kan ikke behandle lyd: {exc}")
        return

    await client.chat_postMessage(channel=channel_id, text="🎙️ Transskriberer stemmebesked…")

    try:
        transcript = await transcribe_audio(audio_bytes, resolved_mime)
    except Exception as exc:
        await client.chat_postMessage(channel=channel_id, text=f"❌ Transskribering fejlede: {exc}")
        return

    await client.chat_postMessage(channel=channel_id, text=f"🎙️ Transskriberet: _{transcript}_")

    async def reply(msg: str) -> None:
        await client.chat_postMessage(channel=channel_id, text=msg)

    async def confirm(conf: PendingConfirmation) -> None:
        await client.chat_postMessage(
            channel=channel_id,
            blocks=_build_confirmation_blocks(conf),
            text=f"Handling kræver bekræftelse: {conf.plan.user_message_summary}",
        )

    await run_pipeline(
        message=transcript,
        user_id=user_id,
        channel_id=channel_id,
        message_ref="",
        platform="slack",
        reply_fn=reply,
        confirm_fn=confirm,
    )


# ── Confirmation button handler ───────────────────────────────────────────────

async def handle_action(body: dict, ack, client, say) -> None:
    await ack()
    action = body.get("actions", [{}])[0]
    action_id: str = action.get("action_id", "")
    user_id = body.get("user", {}).get("id", "unknown")

    if action_id.startswith("confirm_action:"):
        conf_id = action_id.split(":", 1)[1]
        conf = confirmation_store.get(conf_id)
        if not conf:
            await client.chat_postMessage(
                channel=body["channel"]["id"],
                thread_ts=body["message"]["ts"],
                text="⚠️ Bekræftelse er udløbet eller allerede behandlet.",
            )
            return
        if conf.user_id != user_id:
            await client.chat_postMessage(
                channel=conf.channel_id,
                thread_ts=conf.thread_ts,
                text="⚠️ Kun den originale afsender kan bekræfte denne handling.",
            )
            return

        confirmation_store.remove(conf_id)
        t0 = time.monotonic()
        result = await executor.run(conf.plan)
        duration_ms = (time.monotonic() - t0) * 1000

        await client.chat_postMessage(
            channel=conf.channel_id,
            thread_ts=conf.thread_ts,
            text=format_result(result),
        )
        audit_action(
            user_id=user_id, platform="slack",
            requested_action=conf.plan.user_message_summary,
            plan=conf.plan, approved=True,
            executed_tools=[a.tool for a in conf.plan.actions],
            errors=result.errors,
            duration_ms=duration_ms,
        )

    elif action_id.startswith("cancel_action:"):
        conf_id = action_id.split(":", 1)[1]
        confirmation_store.remove(conf_id)
        await client.chat_postMessage(
            channel=body["channel"]["id"],
            thread_ts=body["message"]["ts"],
            text="🚫 Handling annulleret.",
        )
        audit_action(
            user_id=user_id, platform="slack",
            requested_action="(bruger annullerede)", approved=False,
        )


# ── Block Kit helpers ─────────────────────────────────────────────────────────

def _build_confirmation_blocks(conf: PendingConfirmation) -> list[dict]:
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": format_plan_text(conf)},
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Bekræft"},
                    "style": "primary",
                    "action_id": f"confirm_action:{conf.id}",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ Annuller"},
                    "style": "danger",
                    "action_id": f"cancel_action:{conf.id}",
                },
            ],
        },
    ]
