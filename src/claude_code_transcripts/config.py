"""Configuration management for the transcript server."""

import os


class Config:
    """Configuration for the transcript server."""

    def __init__(self):
        """Initialize configuration from environment variables."""
        # Database configuration
        self.database_url = os.environ.get(
            "DATABASE_URL", "postgresql://localhost/claude_transcripts"
        )

        # Storage configuration
        self.storage_path = os.environ.get(
            "STORAGE_PATH", os.path.expanduser("~/.claude-transcripts")
        )

        # Update interval (in minutes)
        try:
            self.update_interval_minutes = int(
                os.environ.get("UPDATE_INTERVAL_MINUTES", "60")
            )
        except ValueError:
            raise ValueError("UPDATE_INTERVAL_MINUTES must be an integer")

        # Server configuration
        self.server_host = os.environ.get("SERVER_HOST", "127.0.0.1")

        try:
            self.server_port = int(os.environ.get("SERVER_PORT", "5000"))
        except ValueError:
            raise ValueError("SERVER_PORT must be an integer")

        # Claude API credentials (optional, will fall back to keychain on macOS)
        self.claude_token = os.environ.get("CLAUDE_TOKEN")
        self.claude_org_uuid = os.environ.get("CLAUDE_ORG_UUID")

        # GitHub repo for commit links (optional)
        self.github_repo = os.environ.get("GITHUB_REPO")

    def __repr__(self):
        """Return a string representation of the config."""
        return (
            f"<Config(database_url='{self.database_url[:20]}...', "
            f"storage_path='{self.storage_path}', "
            f"update_interval_minutes={self.update_interval_minutes}, "
            f"server_host='{self.server_host}', "
            f"server_port={self.server_port})>"
        )
