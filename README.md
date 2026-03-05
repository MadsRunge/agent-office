# Agent Office

A production-minded Slack bot that acts as a personal AI assistant for Google Workspace — Calendar, Gmail, and Drive. Send plain text or voice notes; the bot parses your intent, generates a structured action plan, asks for confirmation on risky actions, and executes via the `gws` CLI or Google APIs.

```
You → Slack DM/voice note
      ↓
   Claude (intent → action plan JSON)
      ↓
   Confirmation gate (for risky actions)
      ↓
   gws CLI  OR  Google API adapter
      ↓
   Human summary + audit log
```

---

## Features

| Feature | Status |
|---|---|
| Slack DMs + mentions | ✅ |
| Voice note transcription (whisper.cpp) | ✅ |
| Calendar: list / create / update / delete | ✅ |
| Gmail: search / get / draft / send / reply | ✅ |
| Drive: list / search / create folder / create doc | ✅ |
| Confirmation gates (Block Kit buttons) | ✅ |
| Dry-run mode (`/dryrun`) | ✅ |
| Audit log (`audit.jsonl`) | ✅ |
| Prompt injection mitigation | ✅ |
| Encrypted token storage | ✅ |
| gws CLI → Google API fallback | ✅ |

---

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- A Slack App and/or a Telegram bot (at least one required)
- Google Cloud project with OAuth 2.0 credentials
- (Optional) `gws` CLI from [googleworkspace/cli](https://github.com/googleworkspace/cli)
- (For voice) `whisper.cpp` + `ffmpeg`

---

## Step-by-Step Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url> agent-office
cd agent-office
uv sync
```

### 2. Create a Telegram Bot (recommended — easiest)

1. Open Telegram and chat with **@BotFather**
2. Send `/newbot` → follow prompts → get your **Bot Token**
3. Copy token → `TELEGRAM_BOT_TOKEN` in `.env`
4. Optionally register slash commands via BotFather:
   ```
   /setcommands
   calendar - Kalender
   gmail - Gmail
   drive - Google Drive
   dryrun - Vis plan uden at udføre
   help - Hjælp
   ```
5. Find your bot by username and start a chat

That's it — no webhooks, no public URL needed. The bot uses polling locally.

---

### 3. Create a Slack App (optional)

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**
2. **Socket Mode** (Basic Information → Enable Socket Mode) → Generate **App-Level Token** with `connections:write` scope → copy as `SLACK_APP_TOKEN`
3. **OAuth & Permissions** → Bot Token Scopes:
   ```
   app_mentions:read
   channels:history
   chat:write
   commands
   files:read
   im:history
   im:read
   im:write
   ```
4. Install app to workspace → copy **Bot User OAuth Token** as `SLACK_BOT_TOKEN`
5. **Signing Secret** (Basic Information → App Credentials) → copy as `SLACK_SIGNING_SECRET`
6. **Slash Commands** → Create:
   - `/calendar` → request URL: (handled via Socket Mode, URL not needed)
   - `/gmail`
   - `/drive`
   - `/dryrun`
7. **Event Subscriptions** → Enable → Subscribe to bot events:
   - `app_mention`
   - `file_shared`
   - `message.im`

### 4. Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or reuse one)
3. Enable these APIs:
   - Google Calendar API
   - Gmail API
   - Google Drive API
   - Google Docs API
4. **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
   - Application type: **Web application**
   - Authorised redirect URIs: `http://localhost:8080/auth/callback`
5. Copy **Client ID** → `GOOGLE_CLIENT_ID`
6. Copy **Client Secret** → `GOOGLE_CLIENT_SECRET`
7. **OAuth consent screen** → User type: **External** → add your Gmail as a test user → add scopes:
   - `https://www.googleapis.com/auth/calendar`
   - `https://www.googleapis.com/auth/gmail.modify`
   - `https://www.googleapis.com/auth/drive`
   - `https://www.googleapis.com/auth/documents`

### 5. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:
- `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_SIGNING_SECRET`
- `ANTHROPIC_API_KEY`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- `ENCRYPTION_KEY` (generate with command below)

```bash
# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 6. Install gws CLI (optional but recommended)

```bash
# macOS
brew install googleworkspace/tap/gws

# Or from source
git clone https://github.com/googleworkspace/cli
cd cli && make install
```

Authenticate the CLI:
```bash
gws auth login
```

The bot will auto-detect if `gws` is installed. If not, it falls back to direct Google APIs.

### 7. Install whisper.cpp (for voice notes)

```bash
# macOS (Homebrew)
brew install whisper-cpp

# Or compile from source
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp && make

# Download model (~142 MB base English model)
mkdir -p ~/.whisper
curl -L -o ~/.whisper/ggml-base.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin

# Install ffmpeg (for non-wav audio)
brew install ffmpeg
```

Update `.env`:
```
WHISPER_CLI_PATH=/usr/local/bin/whisper-cli
WHISPER_MODEL_PATH=~/.whisper/ggml-base.en.bin
```

### 8. Run locally

```bash
uv run python main.py
```

This starts:
- **Slack bot** (Socket Mode, no public URL needed)
- **OAuth server** at http://localhost:8080

### 9. Authenticate Google

Open http://localhost:8080/auth/google in your browser and complete the OAuth flow.

Your tokens are stored encrypted in `.tokens/`.

---

## Usage Examples

### Text messages (DM the bot or mention it)

```
Schedule a meeting with Emma tomorrow at 10 about NorthPlan
```
→ Bot creates calendar event, asks confirmation (attendees present)

```
Find the latest email from Moveforce and draft a reply saying we'll be delayed by one week
```
→ Bot searches Gmail, reads the thread, creates a draft

```
Search my Drive for 'contract' and list top 5
```
→ Bot lists matching Drive files immediately (no confirmation needed)

```
dryrun: Delete the team standup event on Friday
```
→ Bot shows the plan without executing

### Slash commands

```
/calendar List this week's events
/gmail Search for emails from boss@company.com
/drive Search for Q4 report
/dryrun Send Emma an email about the project delay
```

### Voice notes

Upload any `.m4a`, `.mp3`, `.wav`, `.ogg`, or `.webm` file to the bot DM.

> "Book dentist appointment next Tuesday at two pm"

The bot will:
1. Transcribe via whisper.cpp
2. Show the transcript
3. Generate an action plan
4. Ask for confirmation

---

## Security Model

| Threat | Mitigation |
|---|---|
| Prompt injection from email content | Email body never passed as LLM instructions; wrapped in `<untrusted_data>` for summarisation only |
| Accidental email send | Explicit Slack button confirmation required; times out after 5 min |
| Accidental event deletion | Explicit confirmation required |
| Token theft | Tokens encrypted with Fernet + env passphrase; stored in 0600 files |
| Malicious audio file | MIME type + size validated before transcription |
| Subprocess injection | All CLI args passed as `list[str]`; `shell=False` always |
| Audit trail | Every action logged to `audit.jsonl` with user, platform, plan, outcome |

---

## Architecture

```
adapters/slack/     — Slack Bolt event handlers, voice note download
agent/              — Claude-powered planner + plan executor
auth/               — FastAPI OAuth2 callback server
core/               — Pydantic models, policies, confirmation store, audit log, security
services/           — Business logic (calendar, gmail, drive, transcription)
tools/              — gws CLI adapter + Google API adapters (fallback)
```

### Tool Registry

All services register with a central `ToolRegistry`:

```python
registry.register("calendar.create_event", calendar_service.create_event)
result = await registry.execute("calendar.create_event", {"title": "Meeting", ...})
```

### Adding a new platform (e.g. Discord)

1. Create `adapters/discord/bot.py`
2. Import and call `_run_pipeline()` from the handler
3. The entire agent/tool/service layer is reused without changes

---

## Running Tests

```bash
uv run pytest tests/ -v
```

---

## Docker

```bash
# Build
docker build -t agent-office .

# Run
docker compose up

# OAuth: open http://localhost:8080/auth/google
```

---

## Dry-run Mode

Any message prefixed with `dryrun:` or the `/dryrun` slash command runs the full planning pipeline but returns a plan preview without touching any APIs:

```
/dryrun Send the Q4 report to the board as an email
```

Output:
```
[DRY RUN] Would execute 1 action(s) for: Send Q4 report email to board
  • gmail.send_message: {'to': ['board@company.com'], 'subject': 'Q4 Report', ...}
```

---

## Audit Log

All actions are appended to `audit.jsonl` in NDJSON format:

```json
{"timestamp":"2024-01-16T09:45:00","user_id":"U123ABC","platform":"slack","requested_action":"Schedule meeting with Emma","plan":{...},"approved":true,"executed_tools":["calendar.create_event"],"errors":[],"dry_run":false}
```

---

## Troubleshooting

**`ENCRYPTION_KEY` not set**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Add to .env: ENCRYPTION_KEY=<output>
```

**Google not authenticated**
```
Visit http://localhost:8080/auth/google
```

**`gws` CLI not found**
The bot automatically falls back to Google APIs. This is expected if you haven't installed the CLI.

**Whisper model not found**
```bash
mkdir -p ~/.whisper
curl -L -o ~/.whisper/ggml-base.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
```

**Slack events not reaching bot**
Check that Socket Mode is enabled in your Slack App settings (Basic Information → Socket Mode).
