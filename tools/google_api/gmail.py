"""Google Gmail API adapter (handles send/draft/reply — always uses API)."""
from __future__ import annotations

import base64
import email as email_lib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import build

from core.context import current_user_id
from tools.google_api.auth import google_auth


def _service():
    creds = google_auth.get_credentials(current_user_id.get())
    if not creds:
        raise RuntimeError("Google account not authenticated. Visit /auth/google")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _encode_message(msg: MIMEMultipart | MIMEText) -> dict:
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}


class GmailAPIAdapter:
    """Direct Gmail API calls."""

    def search_messages(
        self,
        query: str,
        max_results: int = 10,
        user_id: str = "me",
    ) -> list[dict]:
        svc = _service()
        resp = svc.users().messages().list(
            userId=user_id, q=query, maxResults=max_results
        ).execute()
        return resp.get("messages", [])

    def get_message(self, message_id: str, user_id: str = "me") -> dict:
        svc = _service()
        return svc.users().messages().get(
            userId=user_id, id=message_id, format="full"
        ).execute()

    def get_message_text(self, message_id: str, user_id: str = "me") -> dict[str, str]:
        """Return {'subject': ..., 'from': ..., 'body': ...} — treated as untrusted data."""
        msg = self.get_message(message_id, user_id)
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = self._extract_body(msg)
        return {
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "date": headers.get("date", ""),
            "body": body,
        }

    def draft_message(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        user_id: str = "me",
        thread_id: str | None = None,
    ) -> dict:
        msg = self._build_message(to=to, subject=subject, body=body, cc=cc)
        draft_body: dict[str, Any] = {"message": _encode_message(msg)}
        if thread_id:
            draft_body["message"]["threadId"] = thread_id
        svc = _service()
        return svc.users().drafts().create(userId=user_id, body=draft_body).execute()

    def send_message(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        user_id: str = "me",
        thread_id: str | None = None,
    ) -> dict:
        msg = self._build_message(to=to, subject=subject, body=body, cc=cc)
        raw = _encode_message(msg)
        if thread_id:
            raw["threadId"] = thread_id
        svc = _service()
        return svc.users().messages().send(userId=user_id, body=raw).execute()

    def reply_message(
        self,
        *,
        message_id: str,
        body: str,
        user_id: str = "me",
    ) -> dict:
        """Draft a reply to an existing message and send it."""
        original = self.get_message_text(message_id, user_id)
        reply_to = original.get("from", "")
        subject = original.get("subject", "")
        if not subject.startswith("Re: "):
            subject = f"Re: {subject}"
        # Get thread_id from original message headers
        raw_msg = self.get_message(message_id, user_id)
        thread_id = raw_msg.get("threadId")
        return self.send_message(
            to=[reply_to],
            subject=subject,
            body=body,
            user_id=user_id,
            thread_id=thread_id,
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _build_message(
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
    ) -> MIMEMultipart:
        msg = MIMEMultipart()
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = ", ".join(cc)
        msg.attach(MIMEText(body, "plain", "utf-8"))
        return msg

    @staticmethod
    def _extract_body(msg: dict) -> str:
        """Extract plain-text body from Gmail message payload."""
        payload = msg.get("payload", {})
        if payload.get("mimeType") == "text/plain":
            data = payload.get("body", {}).get("data", "")
            return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
        return ""


gmail_api = GmailAPIAdapter()
