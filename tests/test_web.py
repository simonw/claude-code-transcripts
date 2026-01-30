"""Tests for web command."""

import json
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from claude_code_transcripts import cli


class TestWebCommandList:
    """Tests for web command --list flag."""

    @patch("claude_code_transcripts.fetch_sessions")
    @patch("claude_code_transcripts.get_access_token_from_keychain")
    @patch("claude_code_transcripts.get_org_uuid_from_config")
    def test_list_displays_sessions_grouped_by_repo(
        self, mock_get_org, mock_get_token, mock_fetch
    ):
        """Should display sessions grouped by repo when --list flag is used."""
        # Setup mocks
        mock_get_token.return_value = "test-token"
        mock_get_org.return_value = "test-org-uuid"

        # Mock API response with sessions
        mock_fetch.return_value = {
            "data": [
                {
                    "id": "session-123",
                    "title": "Fix authentication bug",
                    "created_at": "2026-01-30T10:00:00Z",
                    "session_context": {
                        "outcomes": [
                            {
                                "type": "git_repository",
                                "git_info": {"repo": "owner/repo1", "type": "github"},
                            }
                        ]
                    },
                },
                {
                    "id": "session-456",
                    "title": "Add new feature",
                    "created_at": "2026-01-29T15:30:00Z",
                    "session_context": {
                        "outcomes": [
                            {
                                "type": "git_repository",
                                "git_info": {"repo": "owner/repo1", "type": "github"},
                            }
                        ]
                    },
                },
                {
                    "id": "session-789",
                    "title": "Update documentation",
                    "created_at": "2026-01-28T09:15:00Z",
                    "session_context": {},
                },
            ]
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["web", "--list"])

        # Verify exit code
        assert result.exit_code == 0

        # Verify output contains session IDs
        assert "session-123" in result.output
        assert "session-456" in result.output
        assert "session-789" in result.output

        # Verify output contains titles
        assert "Fix authentication bug" in result.output
        assert "Add new feature" in result.output
        assert "Update documentation" in result.output

        # Verify output shows grouping by repo
        assert "owner/repo1" in result.output
        assert "(no repo)" in result.output

        # Verify count is displayed
        assert "3 session(s)" in result.output or "Total: 3" in result.output

    @patch("claude_code_transcripts.fetch_sessions")
    @patch("claude_code_transcripts.get_access_token_from_keychain")
    @patch("claude_code_transcripts.get_org_uuid_from_config")
    def test_list_with_repo_filter(self, mock_get_org, mock_get_token, mock_fetch):
        """Should filter sessions by repo when --repo flag is used with --list."""
        mock_get_token.return_value = "test-token"
        mock_get_org.return_value = "test-org-uuid"

        mock_fetch.return_value = {
            "data": [
                {
                    "id": "session-123",
                    "title": "Session in repo1",
                    "created_at": "2026-01-30T10:00:00Z",
                    "session_context": {
                        "outcomes": [
                            {
                                "type": "git_repository",
                                "git_info": {"repo": "owner/repo1", "type": "github"},
                            }
                        ]
                    },
                },
                {
                    "id": "session-456",
                    "title": "Session in repo2",
                    "created_at": "2026-01-29T15:30:00Z",
                    "session_context": {
                        "outcomes": [
                            {
                                "type": "git_repository",
                                "git_info": {"repo": "owner/repo2", "type": "github"},
                            }
                        ]
                    },
                },
            ]
        }

        runner = CliRunner()
        result = runner.invoke(cli, ["web", "--list", "--repo", "owner/repo1"])

        assert result.exit_code == 0
        assert "session-123" in result.output
        assert "Session in repo1" in result.output
        # Should not show session from repo2
        assert "session-456" not in result.output
        assert "Session in repo2" not in result.output

    @patch("claude_code_transcripts.fetch_sessions")
    @patch("claude_code_transcripts.get_access_token_from_keychain")
    @patch("claude_code_transcripts.get_org_uuid_from_config")
    def test_list_with_no_sessions(self, mock_get_org, mock_get_token, mock_fetch):
        """Should display appropriate message when no sessions found."""
        mock_get_token.return_value = "test-token"
        mock_get_org.return_value = "test-org-uuid"
        mock_fetch.return_value = {"data": []}

        runner = CliRunner()
        result = runner.invoke(cli, ["web", "--list"])

        assert result.exit_code != 0
        assert "No sessions found" in result.output
