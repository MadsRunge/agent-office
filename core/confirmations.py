"""In-memory pending confirmation store with TTL enforcement."""
from __future__ import annotations

import threading
from typing import Optional

from core.models import PendingConfirmation


class ConfirmationStore:
    """Thread-safe in-memory store for pending action confirmations."""

    def __init__(self) -> None:
        self._store: dict[str, PendingConfirmation] = {}
        self._lock = threading.Lock()

    def add(self, confirmation: PendingConfirmation) -> str:
        with self._lock:
            self._store[confirmation.id] = confirmation
        return confirmation.id

    def get(self, confirmation_id: str) -> Optional[PendingConfirmation]:
        with self._lock:
            conf = self._store.get(confirmation_id)
            if conf is None:
                return None
            if conf.is_expired():
                del self._store[confirmation_id]
                return None
            return conf

    def remove(self, confirmation_id: str) -> Optional[PendingConfirmation]:
        with self._lock:
            return self._store.pop(confirmation_id, None)

    def purge_expired(self) -> int:
        """Remove all expired confirmations. Returns count removed."""
        with self._lock:
            expired = [k for k, v in self._store.items() if v.is_expired()]
            for k in expired:
                del self._store[k]
            return len(expired)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._store)


# Singleton used across the application
confirmation_store = ConfirmationStore()
