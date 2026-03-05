"""
Local whisper.cpp transcription provider.

Requires:
  1. whisper.cpp compiled and `whisper-cli` binary on PATH (or set WHISPER_CLI_PATH)
  2. A ggml model downloaded (e.g. ggml-base.en.bin) at WHISPER_MODEL_PATH
  3. ffmpeg on PATH (or set FFMPEG_PATH) for non-wav audio conversion

Setup:
  # Install whisper.cpp (macOS with homebrew)
  brew install whisper-cpp

  # Or compile from source:
  # git clone https://github.com/ggerganov/whisper.cpp && cd whisper.cpp && make

  # Download model
  mkdir -p ~/.whisper
  curl -L -o ~/.whisper/ggml-base.en.bin \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin

  # Set env vars
  WHISPER_CLI_PATH=/usr/local/bin/whisper-cli
  WHISPER_MODEL_PATH=~/.whisper/ggml-base.en.bin
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import structlog

from services.transcription.base import (
    MAX_AUDIO_SIZE_BYTES,
    ALLOWED_AUDIO_MIME_TYPES,
    TranscriptionError,
    TranscriptionProvider,
)

logger = structlog.get_logger()


class WhisperCppProvider(TranscriptionProvider):
    """Transcription via local whisper.cpp CLI."""

    def __init__(
        self,
        cli_path: str | None = None,
        model_path: str | None = None,
        ffmpeg_path: str | None = None,
    ) -> None:
        self.cli_path = cli_path or os.environ.get("WHISPER_CLI_PATH", "whisper-cli")
        self.model_path = os.path.expanduser(
            model_path or os.environ.get("WHISPER_MODEL_PATH", "~/.whisper/ggml-base.en.bin")
        )
        self.ffmpeg_path = ffmpeg_path or os.environ.get("FFMPEG_PATH", "ffmpeg")

    def check_installation(self) -> dict[str, bool]:
        return {
            "whisper_cli": shutil.which(self.cli_path) is not None,
            "ffmpeg": shutil.which(self.ffmpeg_path) is not None,
            "model_exists": Path(self.model_path).exists(),
        }

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> str:
        self.validate(audio_bytes, mime_type)
        checks = self.check_installation()
        if not checks["whisper_cli"]:
            raise TranscriptionError(
                f"whisper-cli not found at '{self.cli_path}'. "
                "See services/transcription/whisper_cpp.py for setup instructions."
            )
        if not checks["model_exists"]:
            raise TranscriptionError(
                f"Whisper model not found at '{self.model_path}'. "
                "Download with: curl -L -o ~/.whisper/ggml-base.en.bin "
                "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
            )

        # Write audio to temp file
        suffix = self._mime_to_suffix(mime_type)
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = Path(tmpdir) / f"audio{suffix}"
            audio_path.write_bytes(audio_bytes)

            # Convert to wav if needed (whisper.cpp requires wav/16kHz)
            wav_path = Path(tmpdir) / "audio.wav"
            if suffix != ".wav":
                await self._convert_to_wav(audio_path, wav_path)
            else:
                wav_path = audio_path

            transcript = await self._run_whisper(wav_path)
        return transcript.strip()

    async def _convert_to_wav(self, src: Path, dst: Path) -> None:
        if not shutil.which(self.ffmpeg_path):
            raise TranscriptionError(
                f"ffmpeg not found at '{self.ffmpeg_path}'. Install with: brew install ffmpeg"
            )
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(src),
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            str(dst),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise TranscriptionError(
                f"ffmpeg conversion failed: {stderr.decode(errors='replace')[:200]}"
            )

    async def _run_whisper(self, wav_path: Path) -> str:
        # whisper-cli writes transcript to <file>.txt
        txt_path = wav_path.with_suffix(".txt")
        cmd = [
            self.cli_path,
            "-m", self.model_path,
            "-f", str(wav_path),
            "-otxt",            # output plain text
            "--no-timestamps",  # cleaner output
            "-of", str(wav_path.with_suffix("")),  # output file prefix
        ]
        logger.debug("whisper_run", cmd=cmd)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise TranscriptionError(
                f"whisper-cli failed (exit {proc.returncode}): "
                f"{stderr.decode(errors='replace')[:200]}"
            )
        # Try reading output file first, fall back to stdout
        if txt_path.exists():
            return txt_path.read_text(encoding="utf-8")
        return stdout.decode(errors="replace")

    @staticmethod
    def _mime_to_suffix(mime_type: str) -> str:
        mapping = {
            "audio/m4a": ".m4a",
            "audio/mp4": ".mp4",
            "audio/mpeg": ".mp3",
            "audio/mp3": ".mp3",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
            "audio/ogg": ".ogg",
            "audio/webm": ".webm",
            "audio/aac": ".aac",
        }
        return mapping.get(mime_type.lower(), ".audio")


# Singleton
whisper_provider = WhisperCppProvider()
