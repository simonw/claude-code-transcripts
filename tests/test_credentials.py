"""Tests for credential retrieval functions."""

import json
import platform
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from claude_code_transcripts import (
    CredentialsError,
    get_access_token_from_keychain,
    get_org_uuid_from_config,
)


class TestGetAccessTokenFromKeychain:
    """Tests for get_access_token_from_keychain function."""

    @patch("claude_code_transcripts.platform.system")
    def test_returns_none_on_unsupported_platform(self, mock_system):
        """Should return None on Windows."""
        mock_system.return_value = "Windows"
        assert get_access_token_from_keychain() is None

    @patch("claude_code_transcripts.platform.system")
    @patch("claude_code_transcripts.subprocess.run")
    def test_macos_keychain_success(self, mock_run, mock_system):
        """Should retrieve token from macOS keychain."""
        mock_system.return_value = "Darwin"
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "test-token-macos",
                    "expiresAt": "2099-12-31T23:59:59Z",
                }
            }
        )
        mock_run.return_value = mock_result

        token = get_access_token_from_keychain()
        assert token == "test-token-macos"

    @patch("claude_code_transcripts.platform.system")
    @patch("claude_code_transcripts.subprocess.run")
    def test_macos_keychain_not_found(self, mock_run, mock_system):
        """Should return None if keychain entry not found."""
        mock_system.return_value = "Darwin"
        mock_result = Mock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        token = get_access_token_from_keychain()
        assert token is None

    @patch("claude_code_transcripts.platform.system")
    @patch("claude_code_transcripts.Path.home")
    def test_linux_credentials_file_success(self, mock_home, mock_system, tmp_path):
        """Should retrieve token from ~/.claude/.credentials.json on Linux."""
        mock_system.return_value = "Linux"
        mock_home.return_value = tmp_path

        # Create credentials file
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"

        future_time = (
            (datetime.now(timezone.utc) + timedelta(days=30))
            .isoformat()
            .replace("+00:00", "Z")
        )
        creds_data = {
            "claudeAiOauth": {
                "accessToken": "test-token-linux",
                "expiresAt": future_time,
                "refreshToken": "refresh-token",
            }
        }
        creds_file.write_text(json.dumps(creds_data))

        token = get_access_token_from_keychain()
        assert token == "test-token-linux"

    @patch("claude_code_transcripts.platform.system")
    @patch("claude_code_transcripts.Path.home")
    def test_linux_credentials_file_not_found(self, mock_home, mock_system, tmp_path):
        """Should return None if credentials file doesn't exist on Linux."""
        mock_system.return_value = "Linux"
        mock_home.return_value = tmp_path

        token = get_access_token_from_keychain()
        assert token is None

    @patch("claude_code_transcripts.platform.system")
    @patch("claude_code_transcripts.Path.home")
    def test_linux_credentials_expired_token(self, mock_home, mock_system, tmp_path):
        """Should return None if token is expired on Linux."""
        mock_system.return_value = "Linux"
        mock_home.return_value = tmp_path

        # Create credentials file with expired token
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"

        past_time = (
            (datetime.now(timezone.utc) - timedelta(days=1))
            .isoformat()
            .replace("+00:00", "Z")
        )
        creds_data = {
            "claudeAiOauth": {
                "accessToken": "expired-token",
                "expiresAt": past_time,
                "refreshToken": "refresh-token",
            }
        }
        creds_file.write_text(json.dumps(creds_data))

        token = get_access_token_from_keychain()
        assert token is None

    @patch("claude_code_transcripts.platform.system")
    @patch("claude_code_transcripts.Path.home")
    def test_linux_credentials_invalid_json(self, mock_home, mock_system, tmp_path):
        """Should return None if credentials file contains invalid JSON."""
        mock_system.return_value = "Linux"
        mock_home.return_value = tmp_path

        # Create credentials file with invalid JSON
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_file.write_text("not valid json {")

        token = get_access_token_from_keychain()
        assert token is None

    @patch("claude_code_transcripts.platform.system")
    @patch("claude_code_transcripts.Path.home")
    def test_linux_credentials_missing_fields(self, mock_home, mock_system, tmp_path):
        """Should return None if credentials file is missing required fields."""
        mock_system.return_value = "Linux"
        mock_home.return_value = tmp_path

        # Create credentials file with missing fields
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_data = {"someOtherField": "value"}
        creds_file.write_text(json.dumps(creds_data))

        token = get_access_token_from_keychain()
        assert token is None

    @patch("claude_code_transcripts.platform.system")
    @patch("claude_code_transcripts.Path.home")
    def test_linux_credentials_no_expiration(self, mock_home, mock_system, tmp_path):
        """Should accept token if expiresAt field is missing (no expiration)."""
        mock_system.return_value = "Linux"
        mock_home.return_value = tmp_path

        # Create credentials file without expiresAt
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_data = {
            "claudeAiOauth": {
                "accessToken": "test-token-no-expiry",
            }
        }
        creds_file.write_text(json.dumps(creds_data))

        token = get_access_token_from_keychain()
        assert token == "test-token-no-expiry"

    @patch("claude_code_transcripts.platform.system")
    @patch("claude_code_transcripts.Path.home")
    def test_linux_credentials_invalid_expiration_format(
        self, mock_home, mock_system, tmp_path
    ):
        """Should accept token if expiresAt format is invalid (treat as no expiration)."""
        mock_system.return_value = "Linux"
        mock_home.return_value = tmp_path

        # Create credentials file with invalid expiresAt format
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        creds_file = claude_dir / ".credentials.json"
        creds_data = {
            "claudeAiOauth": {
                "accessToken": "test-token-invalid-expiry",
                "expiresAt": "not-a-valid-date",
            }
        }
        creds_file.write_text(json.dumps(creds_data))

        token = get_access_token_from_keychain()
        assert token == "test-token-invalid-expiry"
