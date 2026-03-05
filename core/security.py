"""Security utilities: token encryption, input sanitisation."""
from __future__ import annotations

import os
import re
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


# ── Token store ───────────────────────────────────────────────────────────────

class TokenStore:
    """Fernet-encrypted token persistence."""

    def __init__(self, store_dir: str | None = None) -> None:
        self._dir = Path(store_dir or os.getenv("TOKEN_STORE_DIR", ".tokens"))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._dir.chmod(0o700)

    def _path(self, key: str) -> Path:
        # Sanitise key to safe filename
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", key)
        return self._dir / f"{safe}.enc"

    def save(self, key: str, data: str) -> None:
        f = _get_fernet()
        encrypted = f.encrypt(data.encode("utf-8"))
        path = self._path(key)
        path.write_bytes(encrypted)
        path.chmod(0o600)

    def load(self, key: str) -> str | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            f = _get_fernet()
            return f.decrypt(path.read_bytes()).decode("utf-8")
        except InvalidToken:
            return None

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


# ── Input sanitisation ────────────────────────────────────────────────────────

MAX_INPUT_LENGTH = int(os.getenv("MAX_INPUT_LENGTH", "2000"))

# Patterns that look like prompt-injection attempts
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),
    re.compile(r"<\s*/?system\s*>", re.IGNORECASE),
    re.compile(r"\[\[.*\]\]"),   # common injection delimiters
]


def sanitize_user_input(text: str) -> str:
    """Strip null bytes, limit length, return cleaned text."""
    text = text.replace("\x00", "")
    text = text[:MAX_INPUT_LENGTH]
    return text.strip()


def has_injection_pattern(text: str) -> bool:
    """Heuristic check for obvious prompt-injection in user-supplied text."""
    return any(p.search(text) for p in _INJECTION_PATTERNS)


def redact_tokens(text: str) -> str:
    """Redact Bearer tokens, API keys, etc. from log lines."""
    text = re.sub(r"(Bearer\s+)\S+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"(token[=: ]+)\S+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"(key[=: ]+)\S+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"(secret[=: ]+)\S+", r"\1[REDACTED]", text, flags=re.IGNORECASE)
    return text


# Singleton
token_store = TokenStore()
