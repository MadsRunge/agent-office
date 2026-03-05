"""OpenAI Whisper API transcription provider."""
from __future__ import annotations

import os
import tempfile

import openai

from services.transcription.base import TranscriptionError, TranscriptionProvider


class OpenAIWhisperProvider(TranscriptionProvider):
    def __init__(self) -> None:
        self._client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        self.validate(audio_bytes, mime_type)
        ext = mime_type.split("/")[-1].replace("x-wav", "wav").replace("mpeg", "mp3")
        try:
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=True) as tmp:
                tmp.write(audio_bytes)
                tmp.flush()
                with open(tmp.name, "rb") as f:
                    result = await self._client.audio.transcriptions.create(
                        model="whisper-1",
                        file=f,
                    )
            return result.text
        except openai.APIError as exc:
            raise TranscriptionError(f"OpenAI Whisper error: {exc}") from exc


# Singleton
openai_whisper_provider = OpenAIWhisperProvider()
