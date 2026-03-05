"""Abstract transcription provider interface."""
from __future__ import annotations

from abc import ABC, abstractmethod

ALLOWED_AUDIO_MIME_TYPES: frozenset[str] = frozenset(
    {
        "audio/m4a",
        "audio/mp4",
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/ogg",
        "audio/webm",
        "audio/aac",
    }
)

MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB


class TranscriptionError(RuntimeError):
    pass


class TranscriptionProvider(ABC):
    """All transcription providers must implement this interface."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        """Transcribe audio bytes to text. Raises TranscriptionError on failure."""
        ...

    def validate(self, audio_bytes: bytes, mime_type: str) -> None:
        """Validate audio before transcription. Raises ValueError on invalid input."""
        if mime_type.lower() not in ALLOWED_AUDIO_MIME_TYPES:
            raise ValueError(
                f"Unsupported audio type: {mime_type}. "
                f"Allowed: {', '.join(sorted(ALLOWED_AUDIO_MIME_TYPES))}"
            )
        if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
            mb = len(audio_bytes) / (1024 * 1024)
            raise ValueError(f"Audio file too large: {mb:.1f} MB (max 25 MB)")
        if len(audio_bytes) == 0:
            raise ValueError("Audio file is empty")
