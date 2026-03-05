"""Download and validate voice note attachments from Slack."""
from __future__ import annotations

import httpx
import structlog

from services.transcription.base import (
    ALLOWED_AUDIO_MIME_TYPES,
    MAX_AUDIO_SIZE_BYTES,
    TranscriptionError,
)
from services.transcription.whisper_cpp import whisper_provider

logger = structlog.get_logger()

# Slack file types that are audio
SLACK_AUDIO_SUBTYPES = {"audio"}
SLACK_AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".ogg", ".webm", ".mp4", ".aac"}


async def download_slack_file(
    file_info: dict,
    bot_token: str,
) -> tuple[bytes, str]:
    """
    Download a Slack file. Returns (bytes, mime_type).

    Raises ValueError if the file is not a supported audio type or exceeds size limit.
    """
    filetype = file_info.get("filetype", "")
    mimetype = file_info.get("mimetype", "")
    size = file_info.get("size", 0)
    url = file_info.get("url_private_download") or file_info.get("url_private")
    name: str = file_info.get("name", "")

    # Check size before downloading
    if size > MAX_AUDIO_SIZE_BYTES:
        mb = size / (1024 * 1024)
        raise ValueError(f"File too large: {mb:.1f} MB (max 25 MB)")

    # Determine MIME type
    resolved_mime = mimetype or _extension_to_mime(name)
    if resolved_mime not in ALLOWED_AUDIO_MIME_TYPES:
        raise ValueError(
            f"Unsupported file type: {mimetype or filetype or name}. "
            f"Supported: {', '.join(sorted(ALLOWED_AUDIO_MIME_TYPES))}"
        )

    if not url:
        raise ValueError("No download URL found in file info")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {bot_token}"},
            follow_redirects=True,
            timeout=60.0,
        )
        resp.raise_for_status()
        audio_bytes = resp.content

    # Validate actual size
    if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
        mb = len(audio_bytes) / (1024 * 1024)
        raise ValueError(f"Downloaded file too large: {mb:.1f} MB")

    return audio_bytes, resolved_mime


async def transcribe_audio(audio_bytes: bytes, mime_type: str) -> str:
    """Transcribe audio bytes using the configured provider."""
    return await whisper_provider.transcribe(audio_bytes, mime_type)


def _extension_to_mime(filename: str) -> str:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    mapping = {
        ".m4a": "audio/m4a",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".mp4": "audio/mp4",
        ".aac": "audio/aac",
    }
    return mapping.get(ext, f"audio/{ext.lstrip('.')}" if ext else "application/octet-stream")
