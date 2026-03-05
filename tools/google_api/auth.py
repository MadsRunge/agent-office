"""Google OAuth2 manager — handles token refresh and credential loading."""
from __future__ import annotations

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from core.security import token_store

# Scopes required by the application
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

TOKEN_KEY = "google_oauth_token"


class GoogleAuthManager:
    """Manages OAuth2 credentials for Google APIs."""

    def __init__(self) -> None:
        self._client_id = os.environ["GOOGLE_CLIENT_ID"]
        self._client_secret = os.environ["GOOGLE_CLIENT_SECRET"]
        self._redirect_uri = os.environ.get(
            "GOOGLE_REDIRECT_URI", "http://localhost:8080/auth/callback"
        )

    def get_credentials(self) -> Credentials | None:
        """Load and refresh stored credentials. Returns None if not yet authorised."""
        raw = token_store.load(TOKEN_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self._client_id,
            client_secret=self._client_secret,
            scopes=SCOPES,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            self._save_credentials(creds)
        return creds

    def save_from_code(self, code: str) -> Credentials:
        """Exchange an authorisation code for credentials and persist them."""
        flow = self._build_flow()
        flow.fetch_token(code=code)
        creds = flow.credentials
        self._save_credentials(creds)
        return creds

    def get_auth_url(self) -> str:
        """Return the Google OAuth consent URL."""
        flow = self._build_flow()
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        return auth_url

    def is_authenticated(self) -> bool:
        try:
            creds = self.get_credentials()
            return creds is not None and creds.valid
        except Exception:
            return False

    def _save_credentials(self, creds: Credentials) -> None:
        data = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri,
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": list(creds.scopes or []),
        }
        token_store.save(TOKEN_KEY, json.dumps(data))

    def _build_flow(self) -> Flow:
        client_config = {
            "installed": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uris": [self._redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        return Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=self._redirect_uri,
        )


# Singleton
google_auth = GoogleAuthManager()
