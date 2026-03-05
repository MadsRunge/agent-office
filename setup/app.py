"""
Agent Office — Streamlit Setup Wizard

Run with:  uv run streamlit run setup/app.py
Then open: http://localhost:8501
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import streamlit as st

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
ENV_FILE = ROOT / ".env"

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Agent Office Setup", page_icon="🤖", layout="wide")

# ── Session state defaults ────────────────────────────────────────────────────

DEFAULTS = {
    "openai_key": "",
    "openai_valid": False,
    "telegram_token": "",
    "telegram_valid": False,
    "encryption_key": "",
    "model": "gpt-4o-mini",
    "oauth_port": "8080",
    "confirm_ttl": "300",
    "env_saved": False,
    "agent_pid": None,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Helpers ────────────────────────────────────────────────────────────────────


def _validate_openai(key: str) -> tuple[bool, str]:
    try:
        import openai
        client = openai.OpenAI(api_key=key)
        client.models.list()
        return True, "OK"
    except Exception as e:
        return False, str(e)[:120]


def _validate_telegram(token: str) -> tuple[bool, str]:
    try:
        import httpx
        r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        if r.status_code == 200 and r.json().get("ok"):
            name = r.json()["result"].get("username", "?")
            return True, f"@{name}"
        return False, r.json().get("description", "Invalid token")
    except Exception as e:
        return False, str(e)[:120]


def _generate_encryption_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def _read_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip().strip('"')
    return values


def _write_env(values: dict[str, str]) -> None:
    """Atomic env write: preserve comments, update/add keys, rename tmp → .env."""
    existing_lines: list[str] = []
    if ENV_FILE.exists():
        existing_lines = ENV_FILE.read_text().splitlines()

    written_keys: set[str] = set()
    new_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            new_lines.append(line)
            continue
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in values:
                new_lines.append(f'{key}="{values[key]}"')
                written_keys.add(key)
                continue
        new_lines.append(line)

    # Append new keys not already in file
    for key, val in values.items():
        if key not in written_keys:
            new_lines.append(f'{key}="{val}"')

    tmp = ENV_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(new_lines) + "\n")
    os.replace(tmp, ENV_FILE)


# ── Step status ────────────────────────────────────────────────────────────────

def _step_status() -> list[str]:
    """Return list of status icons per step."""
    icons = []

    # Step 1: api keys
    both = st.session_state.openai_valid and st.session_state.telegram_valid
    icons.append("ok" if both else ("warn" if st.session_state.openai_valid else "error"))

    # Step 2: google credentials (just checks env vars set)
    has_google = bool(
        st.session_state.get("google_client_id") and st.session_state.get("google_client_secret")
    )
    icons.append("ok" if has_google else "warn")

    # Step 3: config (always optional → ok)
    icons.append("ok")

    # Step 4: saved
    icons.append("ok" if st.session_state.env_saved else "pending")

    return icons


# ── Sidebar ────────────────────────────────────────────────────────────────────

STEP_LABELS = [
    "1. API-nøgler",
    "2. Google OAuth",
    "3. Konfiguration",
    "4. Klar",
]

ICON_MAP = {"ok": "✅", "warn": "⚠️", "error": "❌", "pending": "⏳"}

if "current_step" not in st.session_state:
    st.session_state.current_step = 0

with st.sidebar:
    st.title("Agent Office")
    st.caption("Setup Wizard")
    st.divider()
    statuses = _step_status()
    for i, (label, status) in enumerate(zip(STEP_LABELS, statuses)):
        icon = ICON_MAP[status]
        is_active = i == st.session_state.current_step
        prefix = "**" if is_active else ""
        suffix = "**" if is_active else ""
        if st.button(f"{icon} {prefix}{label}{suffix}", key=f"nav_{i}", use_container_width=True):
            st.session_state.current_step = i

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("◀ Tilbage", use_container_width=True) and st.session_state.current_step > 0:
            st.session_state.current_step -= 1
    with col2:
        if st.button("Næste ▶", use_container_width=True) and st.session_state.current_step < 3:
            st.session_state.current_step += 1

step = st.session_state.current_step

# ── Step 1: API Keys ──────────────────────────────────────────────────────────

if step == 0:
    st.header("Trin 1 — API-nøgler")

    existing = _read_env()
    if not st.session_state.openai_key:
        st.session_state.openai_key = existing.get("OPENAI_API_KEY", "")
    if not st.session_state.telegram_token:
        st.session_state.telegram_token = existing.get("TELEGRAM_BOT_TOKEN", "")

    st.subheader("OpenAI API Key")
    st.markdown("Hent din nøgle på [platform.openai.com/api-keys](https://platform.openai.com/api-keys).")
    col1, col2 = st.columns([3, 1])
    with col1:
        ak = st.text_input(
            "OpenAI API Key",
            value=st.session_state.openai_key,
            type="password",
            key="openai_input",
            label_visibility="collapsed",
            placeholder="sk-...",
        )
        st.session_state.openai_key = ak
    with col2:
        if st.button("Test", key="test_openai"):
            if not ak:
                st.warning("Indtast en nøgle.")
            else:
                with st.spinner("Validerer..."):
                    ok, msg = _validate_openai(ak)
                st.session_state.openai_valid = ok
                if ok:
                    st.success("Gyldig!")
                else:
                    st.error(f"Fejl: {msg}")

    if st.session_state.openai_valid:
        st.success("OpenAI API OK")

    st.divider()
    st.subheader("Telegram Bot Token")
    st.markdown("Opret en bot via [@BotFather](https://t.me/BotFather) og kopier tokenet.")
    col3, col4 = st.columns([3, 1])
    with col3:
        tt = st.text_input(
            "Telegram Bot Token",
            value=st.session_state.telegram_token,
            type="password",
            key="telegram_input",
            label_visibility="collapsed",
            placeholder="123456:ABC-...",
        )
        st.session_state.telegram_token = tt
    with col4:
        if st.button("Test", key="test_telegram"):
            if not tt:
                st.warning("Indtast et token.")
            else:
                with st.spinner("Validerer..."):
                    ok2, msg2 = _validate_telegram(tt)
                st.session_state.telegram_valid = ok2
                if ok2:
                    st.success(f"Bot: {msg2}")
                else:
                    st.error(f"Fejl: {msg2}")

    if st.session_state.telegram_valid:
        st.success("Telegram bot OK")

    st.divider()
    st.caption("ENCRYPTION_KEY genereres automatisk — du behøver ikke angive den.")
    if not st.session_state.encryption_key:
        st.session_state.encryption_key = _generate_encryption_key()

# ── Step 2: Google OAuth credentials ─────────────────────────────────────────

elif step == 1:
    st.header("Trin 2 — Google OAuth")
    st.write(
        "Opret OAuth 2.0-legitimationsoplysninger i Google Cloud Console, "
        "og angiv Client ID og Client Secret herunder."
    )

    st.markdown(
        "**Trin:**\n"
        "1. Åbn [Google Cloud Console](https://console.cloud.google.com/apis/credentials)\n"
        "2. Opret et projekt (eller vælg eksisterende)\n"
        "3. Aktivér Google Calendar API, Gmail API og Drive API\n"
        "4. Opret OAuth 2.0-klientid (type: **Webapplikation**)\n"
        "5. Tilføj `http://localhost:8080/auth/callback` som godkendt omdirigerings-URI\n"
        "6. Kopier Client ID og Client Secret herunder"
    )

    existing = _read_env()
    if "google_client_id" not in st.session_state:
        st.session_state.google_client_id = existing.get("GOOGLE_CLIENT_ID", "")
    if "google_client_secret" not in st.session_state:
        st.session_state.google_client_secret = existing.get("GOOGLE_CLIENT_SECRET", "")

    st.session_state.google_client_id = st.text_input(
        "Google Client ID",
        value=st.session_state.google_client_id,
        placeholder="xxx.apps.googleusercontent.com",
    )
    st.session_state.google_client_secret = st.text_input(
        "Google Client Secret",
        value=st.session_state.google_client_secret,
        type="password",
        placeholder="GOCSPX-...",
    )

    if st.session_state.google_client_id and st.session_state.google_client_secret:
        st.success("Google OAuth-legitimationsoplysninger angivet.")
    else:
        st.warning("Angiv både Client ID og Client Secret.")

# ── Step 3: Configuration ─────────────────────────────────────────────────────

elif step == 2:
    st.header("Trin 3 — Konfiguration")
    st.write("Alle felter er valgfrie. Standard-værdier er fornuftige til de fleste setups.")

    existing = _read_env()

    model_options = ["gpt-4o-mini", "gpt-4o"]
    current_model = existing.get("OPENAI_MODEL", st.session_state.model)
    idx = model_options.index(current_model) if current_model in model_options else 0

    st.session_state.model = st.selectbox(
        "OpenAI-model",
        options=model_options,
        index=idx,
        help="gpt-4o-mini er hurtigst og billigst. gpt-4o er kraftigst.",
    )

    st.session_state.oauth_port = st.text_input(
        "OAuth-port (Google)",
        value=existing.get("OAUTH_PORT", st.session_state.oauth_port),
        help="Port som FastAPI OAuth-serveren lytter på.",
    )

    st.session_state.confirm_ttl = st.text_input(
        "Bekræftelse TTL (sekunder)",
        value=existing.get("CONFIRMATION_TTL_SECONDS", st.session_state.confirm_ttl),
        help="Tid brugeren har til at bekræfte risikable handlinger.",
    )

# ── Step 4: Ready ─────────────────────────────────────────────────────────────

elif step == 3:
    st.header("Trin 4 — Klar")

    st.subheader("Status")

    def status_row(label: str, ok: bool, optional: bool = False) -> None:
        icon = "✅" if ok else ("⚠️" if optional else "❌")
        suffix = " _(valgfrit)_" if optional and not ok else ""
        st.markdown(f"{icon} {label}{suffix}")

    status_row("OpenAI API nøgle", st.session_state.openai_valid)
    status_row("Telegram bot tilsluttet", st.session_state.telegram_valid)
    status_row(
        "Google OAuth legitimationsoplysninger",
        bool(st.session_state.get("google_client_id") and st.session_state.get("google_client_secret")),
    )

    ready = st.session_state.openai_valid

    st.divider()

    if not ready:
        st.warning("Fuldfør mindst Trin 1 (OpenAI API-nøgle) før du gemmer konfigurationen.")

    col_save, col_start = st.columns(2)

    with col_save:
        if st.button("Gem konfiguration", type="primary", disabled=not ready):
            env_values: dict[str, str] = {
                "OPENAI_API_KEY": st.session_state.openai_key,
                "OPENAI_MODEL": st.session_state.model,
                "TELEGRAM_BOT_TOKEN": st.session_state.telegram_token,
                "GOOGLE_CLIENT_ID": st.session_state.get("google_client_id", ""),
                "GOOGLE_CLIENT_SECRET": st.session_state.get("google_client_secret", ""),
                "ENCRYPTION_KEY": st.session_state.encryption_key,
                "OAUTH_PORT": st.session_state.oauth_port,
                "CONFIRMATION_TTL_SECONDS": st.session_state.confirm_ttl,
            }
            env_values = {k: v for k, v in env_values.items() if v}
            try:
                _write_env(env_values)
                st.session_state.env_saved = True
                st.success(f"Gemt til {ENV_FILE}")
            except Exception as e:
                st.error(f"Fejl ved skrivning: {e}")

    with col_start:
        if st.button("Start Agent Office", disabled=not st.session_state.env_saved):
            try:
                proc2 = subprocess.Popen(
                    ["uv", "run", "python", str(ROOT / "main.py")],
                    cwd=str(ROOT),
                )
                st.session_state.agent_pid = proc2.pid
                st.success(f"Agent Office startet (PID {proc2.pid})")
            except Exception as e2:
                st.error(f"Fejl: {e2}")

    if st.session_state.env_saved:
        st.info(f".env gemt til: `{ENV_FILE}`")

    if st.session_state.agent_pid:
        st.info(f"Agent Office kører med PID {st.session_state.agent_pid}")
        if st.session_state.telegram_valid and st.session_state.telegram_token:
            st.markdown(
                "Din Telegram-bot er klar! Find den via [@BotFather](https://t.me/BotFather) "
                "eller søg efter dit bot-brugernavn."
            )
