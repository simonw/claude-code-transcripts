# Claude Code Transcripts Server

The server component automatically syncs and serves Claude Code transcripts from both local sessions and the Claude API.

## Features

- **Automated hourly syncing** of transcripts from Claude Code (local) and Claude Web (API)
- **Change detection** - only re-generates HTML for updated conversations
- **PostgreSQL database** for tracking transcript metadata
- **Flask web interface** for browsing and viewing transcripts
- **Mobile-friendly UI** with dark mode
- **Manual sync trigger** via web interface

## Quick Start

### 1. Set up PostgreSQL

First, create a PostgreSQL database:

```bash
# Using psql
createdb claude_transcripts

# Or specify connection details
createdb -h localhost -U myuser claude_transcripts
```

### 2. Configure Environment Variables

Create a `.env` file or export these variables:

```bash
# Required: Database connection
export DATABASE_URL="postgresql://localhost/claude_transcripts"

# Optional: Storage location (default: ~/.claude-transcripts)
export STORAGE_PATH="/path/to/store/html/files"

# Optional: Update interval in minutes (default: 60)
export UPDATE_INTERVAL_MINUTES="60"

# Optional: Server configuration (defaults shown)
export SERVER_HOST="127.0.0.1"
export SERVER_PORT="5000"

# Optional: Claude API credentials (auto-detected on macOS)
export CLAUDE_TOKEN="your-api-token"
export CLAUDE_ORG_UUID="your-org-uuid"

# Optional: GitHub repo for commit links
export GITHUB_REPO="owner/repo"
```

### 3. Run Database Migrations

```bash
# Initialize the database schema
DATABASE_URL="postgresql://localhost/claude_transcripts" uv run alembic upgrade head
```

### 4. Start the Server

```bash
uv run claude-code-transcripts-server
```

The server will:
- Start on http://127.0.0.1:5000 by default
- Run an initial sync on startup
- Automatically sync every hour (configurable)
- Serve transcripts via a web interface

## Usage

### Web Interface

Navigate to `http://127.0.0.1:5000` to:
- Browse all synced transcripts
- View conversation statistics
- Manually trigger syncs
- Click any transcript to view the full HTML

### Manual Sync

Trigger a sync programmatically:

```bash
curl http://127.0.0.1:5000/sync
```

### Command Line Options

```bash
# Start server with custom host/port
uv run claude-code-transcripts-server --host 0.0.0.0 --port 8080

# Disable automatic hourly updates
uv run claude-code-transcripts-server --no-scheduler

# Run in debug mode
uv run claude-code-transcripts-server --debug
```

## Configuration Details

### Database URL Format

PostgreSQL:
```
postgresql://username:password@localhost:5432/database_name
```

For local development with PostgreSQL:
```
postgresql://localhost/claude_transcripts
```

### Storage Path

HTML files are organized by session ID:
```
~/.claude-transcripts/
├── session_abc123/
│   ├── index.html
│   ├── page-001.html
│   ├── page-002.html
│   └── ...
├── session_def456/
│   └── ...
```

### Update Interval

Set how often to sync transcripts (in minutes):
```bash
export UPDATE_INTERVAL_MINUTES="30"  # Sync every 30 minutes
```

## Database Schema

The server uses a single `conversations` table:

```sql
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    source VARCHAR(50) NOT NULL,          -- 'local' or 'web'
    last_updated TIMESTAMP NOT NULL,
    message_count INTEGER NOT NULL,
    html_path VARCHAR(512) NOT NULL,
    first_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_conversations_session_id ON conversations(session_id);
```

## Running in Production

### Using systemd

Create `/etc/systemd/system/claude-transcripts.service`:

```ini
[Unit]
Description=Claude Code Transcripts Server
After=network.target postgresql.service

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/claude-code-transcripts
Environment="DATABASE_URL=postgresql://localhost/claude_transcripts"
Environment="STORAGE_PATH=/var/lib/claude-transcripts"
ExecStart=/home/youruser/.local/bin/uv run claude-code-transcripts-server
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable claude-transcripts
sudo systemctl start claude-transcripts
```

### Using Docker

Example `Dockerfile`:

```dockerfile
FROM python:3.11-slim

RUN pip install uv

WORKDIR /app
COPY . .

RUN uv sync

EXPOSE 5000

CMD ["uv", "run", "claude-code-transcripts-server", "--host", "0.0.0.0"]
```

Build and run:
```bash
docker build -t claude-transcripts .
docker run -p 5000:5000 \
  -e DATABASE_URL="postgresql://host.docker.internal/claude_transcripts" \
  -e STORAGE_PATH="/data" \
  -v /path/to/storage:/data \
  claude-transcripts
```

## Troubleshooting

### Database Connection Errors

Verify PostgreSQL is running:
```bash
psql -h localhost -U postgres -c "SELECT version();"
```

Test connection string:
```bash
psql "postgresql://localhost/claude_transcripts"
```

### Claude API Authentication

On macOS, credentials are auto-detected from keychain. On other platforms:

```bash
# Get your token (log into claude.ai and check browser dev tools)
export CLAUDE_TOKEN="your-token"

# Get org UUID from config
export CLAUDE_ORG_UUID="your-org-uuid"
```

### Storage Path Permissions

Ensure the server has write access:
```bash
mkdir -p ~/.claude-transcripts
chmod 755 ~/.claude-transcripts
```

### Migration Issues

Reset migrations (WARNING: deletes all data):
```bash
DATABASE_URL="postgresql://localhost/claude_transcripts" uv run alembic downgrade base
DATABASE_URL="postgresql://localhost/claude_transcripts" uv run alembic upgrade head
```

## Development

Run tests:
```bash
uv run pytest
```

Format code:
```bash
uv run black .
```

Create a new migration:
```bash
DATABASE_URL="postgresql://localhost/claude_transcripts" uv run alembic revision --autogenerate -m "Description"
```

## API Reference

### GET /

Main page - lists all transcripts.

### GET /transcript/<session_id>

View a specific transcript's index page.

### GET /transcript/<session_id>/page-<num>.html

View a specific page of a transcript.

### GET /sync

Trigger a manual sync of all transcripts.

Returns:
```json
{
  "status": "success",
  "timestamp": "2025-01-01T12:00:00",
  "stats": {
    "local_updated": 5,
    "web_updated": 3,
    "total_updated": 8
  }
}
```
