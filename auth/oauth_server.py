"""
FastAPI OAuth2 callback server.

Runs on port 8080 (configurable via OAUTH_SERVER_PORT).

Routes:
  GET /             → status page
  GET /health       → liveness probe
  GET /auth/google  → redirect to Google OAuth consent screen
  GET /auth/callback → exchange code, store encrypted token, redirect to success
  GET /auth/status  → check if authenticated
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from tools.google_api.auth import google_auth

app = FastAPI(title="Agent Office OAuth Server", docs_url=None, redoc_url=None)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/auth/status")
async def auth_status():
    authenticated = google_auth.is_authenticated()
    return JSONResponse({"authenticated": authenticated})


@app.get("/auth/google")
async def start_google_auth():
    """Redirect user to Google OAuth consent screen."""
    auth_url = google_auth.get_auth_url()
    return RedirectResponse(url=auth_url)


@app.get("/auth/callback")
async def google_callback(request: Request):
    """Handle Google OAuth callback, exchange code for tokens."""
    code = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        return HTMLResponse(
            _html_page(
                "Authentication Failed",
                f"<p style='color:red'>OAuth error: {error}</p>"
                "<p><a href='/auth/google'>Try again</a></p>",
            ),
            status_code=400,
        )

    if not code:
        return HTMLResponse(
            _html_page("Authentication Failed", "<p>No authorisation code received.</p>"),
            status_code=400,
        )

    try:
        google_auth.save_from_code(code)
    except Exception as exc:
        return HTMLResponse(
            _html_page(
                "Authentication Failed",
                f"<p style='color:red'>Token exchange failed: {exc}</p>"
                "<p><a href='/auth/google'>Try again</a></p>",
            ),
            status_code=500,
        )

    return HTMLResponse(
        _html_page(
            "Authenticated ✅",
            "<p>Google account connected successfully!</p>"
            "<p>You can close this window and return to Slack.</p>",
        )
    )


@app.get("/")
async def index():
    authenticated = google_auth.is_authenticated()
    status = "✅ Connected" if authenticated else "❌ Not connected"
    action = (
        "<p>Google account is connected. Ready to use!</p>"
        if authenticated
        else '<p><a href="/auth/google">Connect Google Account</a></p>'
    )
    return HTMLResponse(
        _html_page(
            "Agent Office",
            f"<h2>Google Account: {status}</h2>{action}",
        )
    )


def _html_page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
  <title>{title} — Agent Office</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 600px; margin: 80px auto; padding: 0 20px; }}
    h1 {{ color: #333; }} a {{ color: #0057b7; }}
  </style>
</head>
<body>
  <h1>Agent Office</h1>
  <h2>{title}</h2>
  {body}
</body>
</html>"""


def create_oauth_app() -> FastAPI:
    return app
