"""Tests for configuration system."""

import os
import pytest
from claude_code_transcripts.config import Config


def test_config_defaults():
    """Test default configuration values."""
    config = Config()
    assert config.database_url == "postgresql://localhost/claude_transcripts"
    assert config.storage_path == os.path.expanduser("~/.claude-transcripts")
    assert config.update_interval_minutes == 60
    assert config.server_host == "127.0.0.1"
    assert config.server_port == 5000


def test_config_from_environment(monkeypatch):
    """Test configuration from environment variables."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db:5432/mydb")
    monkeypatch.setenv("STORAGE_PATH", "/custom/path")
    monkeypatch.setenv("UPDATE_INTERVAL_MINUTES", "30")
    monkeypatch.setenv("SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("SERVER_PORT", "8080")

    config = Config()
    assert config.database_url == "postgresql://user:pass@db:5432/mydb"
    assert config.storage_path == "/custom/path"
    assert config.update_interval_minutes == 30
    assert config.server_host == "0.0.0.0"
    assert config.server_port == 8080


def test_config_invalid_port(monkeypatch):
    """Test that invalid port raises ValueError."""
    monkeypatch.setenv("SERVER_PORT", "invalid")

    with pytest.raises(ValueError):
        Config()


def test_config_invalid_interval(monkeypatch):
    """Test that invalid interval raises ValueError."""
    monkeypatch.setenv("UPDATE_INTERVAL_MINUTES", "not_a_number")

    with pytest.raises(ValueError):
        Config()
