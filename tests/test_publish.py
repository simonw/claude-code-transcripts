"""Tests for GitHub Pages publishing functionality."""

import base64
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import click
import pytest
from click.testing import CliRunner

from claude_code_transcripts import (
    get_github_username,
    publish_to_github,
    generate_session_slug,
    cli,
)


class TestGetGithubUsername:
    """Tests for get_github_username function."""

    def test_returns_username_from_gh_api(self, monkeypatch):
        """Test successful username retrieval from gh CLI."""
        mock_result = subprocess.CompletedProcess(
            args=["gh", "api", "user", "--jq", ".login"],
            returncode=0,
            stdout="testuser\n",
            stderr="",
        )

        def mock_run(*args, **kwargs):
            return mock_result

        monkeypatch.setattr(subprocess, "run", mock_run)

        username = get_github_username()
        assert username == "testuser"

    def test_strips_whitespace(self, monkeypatch):
        """Test that username is stripped of whitespace."""
        mock_result = subprocess.CompletedProcess(
            args=["gh", "api", "user", "--jq", ".login"],
            returncode=0,
            stdout="  myuser  \n",
            stderr="",
        )

        def mock_run(*args, **kwargs):
            return mock_result

        monkeypatch.setattr(subprocess, "run", mock_run)

        username = get_github_username()
        assert username == "myuser"

    def test_raises_on_gh_not_found(self, monkeypatch):
        """Test error when gh CLI is not installed."""

        def mock_run(*args, **kwargs):
            raise FileNotFoundError()

        monkeypatch.setattr(subprocess, "run", mock_run)

        with pytest.raises(click.ClickException) as exc_info:
            get_github_username()

        assert "gh CLI not found" in str(exc_info.value)
        assert "https://cli.github.com/" in str(exc_info.value)

    def test_raises_on_not_authenticated(self, monkeypatch):
        """Test error when gh is not authenticated."""

        def mock_run(*args, **kwargs):
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=["gh", "api", "user"],
                stderr="gh: Not logged in to any GitHub hosts.",
            )

        monkeypatch.setattr(subprocess, "run", mock_run)

        with pytest.raises(click.ClickException) as exc_info:
            get_github_username()

        assert "gh auth login" in str(exc_info.value)


class TestGenerateSessionSlug:
    """Tests for generate_session_slug function."""

    def test_generates_slug_from_title(self):
        """Test slug generation from session title."""
        slug = generate_session_slug("Fix auth bug", "2025-01-15T10:30:00.000Z")
        assert slug == "2025-01-15-fix-auth-bug"

    def test_handles_long_titles(self):
        """Test that long titles are truncated."""
        long_title = (
            "This is a very long title that should be truncated to keep URLs manageable"
        )
        slug = generate_session_slug(long_title, "2025-01-15T10:30:00.000Z")
        assert len(slug) <= 60
        assert slug.startswith("2025-01-15-")

    def test_handles_special_characters(self):
        """Test that special characters are handled."""
        slug = generate_session_slug(
            "Fix: auth bug (URGENT!!)", "2025-01-15T10:30:00.000Z"
        )
        # Should convert to lowercase, replace special chars with hyphens
        assert ":" not in slug
        assert "(" not in slug
        assert "!" not in slug
        assert slug.startswith("2025-01-15-")

    def test_handles_missing_timestamp(self):
        """Test slug generation with missing timestamp uses current date."""
        slug = generate_session_slug("Test session", None)
        # Should still produce a valid slug with a date prefix
        assert "-test-session" in slug

    def test_collapses_multiple_hyphens(self):
        """Test that multiple consecutive hyphens are collapsed."""
        slug = generate_session_slug(
            "Fix --- multiple    spaces", "2025-01-15T10:00:00Z"
        )
        assert "---" not in slug
        assert "  " not in slug


class TestPublishToGithub:
    """Tests for publish_to_github function."""

    def test_publishes_html_files(self, tmp_path, monkeypatch):
        """Test successful publishing of HTML files."""
        # Create test HTML files
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "index.html").write_text("<html><body>Index</body></html>")
        (output_dir / "page-001.html").write_text("<html><body>Page 1</body></html>")

        # Track API calls
        api_calls = []

        def mock_run(cmd, *args, **kwargs):
            api_calls.append(cmd)
            if cmd[0] == "gh" and cmd[1] == "api" and cmd[2] == "user":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="testuser\n", stderr=""
                )
            if cmd[0] == "gh" and cmd[1] == "api" and "-X" in cmd:
                # Simulate file upload - check if file exists (GET returns 404 for new files)
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout='{"sha": "abc123"}', stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", mock_run)

        url = publish_to_github(
            output_dir=output_dir,
            repo="myorg/transcripts",
            branch="gh-pages",
            session_title="Fix auth bug",
            session_timestamp="2025-01-15T10:30:00.000Z",
        )

        # Should return a GitHub Pages URL
        assert "transcripts" in url  # repo name
        assert "myorg" in url  # owner
        assert "testuser" in url
        assert "2025-01-15" in url

    def test_raises_on_repo_not_found(self, tmp_path, monkeypatch):
        """Test error when repository is not found."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "index.html").write_text("<html><body>Test</body></html>")

        def mock_run(cmd, *args, **kwargs):
            if cmd[0] == "gh" and cmd[1] == "api" and cmd[2] == "user":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="testuser\n", stderr=""
                )
            if cmd[0] == "gh" and cmd[1] == "api":
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=cmd,
                    stderr="gh: Could not resolve to a Repository",
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", mock_run)

        with pytest.raises(click.ClickException) as exc_info:
            publish_to_github(
                output_dir=output_dir,
                repo="nonexistent/repo",
                branch="gh-pages",
                session_title="Test",
                session_timestamp="2025-01-15T10:30:00.000Z",
            )

        assert "not found" in str(exc_info.value).lower() or "Repository" in str(
            exc_info.value
        )

    def test_raises_on_branch_not_found(self, tmp_path, monkeypatch):
        """Test error when branch does not exist."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "index.html").write_text("<html><body>Test</body></html>")

        def mock_run(cmd, *args, **kwargs):
            if cmd[0] == "gh" and cmd[1] == "api" and cmd[2] == "user":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="testuser\n", stderr=""
                )
            if cmd[0] == "gh" and cmd[1] == "api":
                raise subprocess.CalledProcessError(
                    returncode=1,
                    cmd=cmd,
                    stderr="gh: No commit found for the ref nonexistent-branch",
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", mock_run)

        with pytest.raises(click.ClickException) as exc_info:
            publish_to_github(
                output_dir=output_dir,
                repo="myorg/transcripts",
                branch="nonexistent-branch",
                session_title="Test",
                session_timestamp="2025-01-15T10:30:00.000Z",
            )

        assert (
            "branch" in str(exc_info.value).lower()
            or "does not exist" in str(exc_info.value).lower()
        )

    def test_updates_existing_files(self, tmp_path, monkeypatch):
        """Test that existing files are updated with correct SHA."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / "index.html").write_text("<html><body>Updated</body></html>")

        api_calls = []

        def mock_run(cmd, *args, **kwargs):
            api_calls.append(cmd)
            if cmd[0] == "gh" and cmd[1] == "api" and cmd[2] == "user":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="testuser\n", stderr=""
                )
            if cmd[0] == "gh" and cmd[1] == "api":
                # Check if this is a GET request (no -X flag or -X not followed by PUT)
                if "-X" not in cmd:
                    # Return existing file with SHA
                    return subprocess.CompletedProcess(
                        args=cmd,
                        returncode=0,
                        stdout='{"sha": "existing-sha-123"}',
                        stderr="",
                    )
                # PUT request
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout='{"sha": "new-sha-456"}', stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", mock_run)

        publish_to_github(
            output_dir=output_dir,
            repo="myorg/transcripts",
            branch="gh-pages",
            session_title="Test",
            session_timestamp="2025-01-15T10:30:00.000Z",
        )

        # Check that a PUT request was made with SHA
        put_calls = [c for c in api_calls if "-X" in c and "PUT" in c]
        assert len(put_calls) > 0


class TestPublishToGithubCLI:
    """Tests for CLI integration of --publish-to-github flag."""

    def test_json_command_has_publish_options(self):
        """Test that json command has publish-to-github options."""
        runner = CliRunner()
        result = runner.invoke(cli, ["json", "--help"])

        assert result.exit_code == 0
        assert "--publish-to-github" in result.output
        assert "--publish-to-github-repo" in result.output
        assert "--publish-to-github-branch" in result.output

    def test_local_command_has_publish_options(self):
        """Test that local command has publish-to-github options."""
        runner = CliRunner()
        result = runner.invoke(cli, ["local", "--help"])

        assert result.exit_code == 0
        assert "--publish-to-github" in result.output
        assert "--publish-to-github-repo" in result.output
        assert "--publish-to-github-branch" in result.output

    def test_web_command_has_publish_options(self):
        """Test that web command has publish-to-github options."""
        runner = CliRunner()
        result = runner.invoke(cli, ["web", "--help"])

        assert result.exit_code == 0
        assert "--publish-to-github" in result.output
        assert "--publish-to-github-repo" in result.output
        assert "--publish-to-github-branch" in result.output

    def test_all_command_does_not_have_publish_options(self):
        """Test that all command does NOT have publish-to-github options."""
        runner = CliRunner()
        result = runner.invoke(cli, ["all", "--help"])

        assert result.exit_code == 0
        assert "--publish-to-github" not in result.output

    def test_json_publish_to_github_success(self, tmp_path, monkeypatch):
        """Test successful publishing via json command."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        api_calls = []

        def mock_run(cmd, *args, **kwargs):
            api_calls.append(cmd)
            if cmd[0] == "gh" and cmd[1] == "api" and cmd[2] == "user":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="testuser\n", stderr=""
                )
            if cmd[0] == "gh" and cmd[1] == "api":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout='{"sha": "abc123"}', stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", mock_run)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "json",
                str(fixture_path),
                "-o",
                str(tmp_path / "output"),
                "--publish-to-github",
                "--publish-to-github-repo",
                "myorg/transcripts",
            ],
        )

        assert result.exit_code == 0
        assert "Publishing to" in result.output or "Published" in result.output

    def test_publish_prompts_for_repo_when_missing(self, tmp_path, monkeypatch):
        """Test that interactive prompt is shown when repo is not specified."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        # Mock questionary to return a repo
        mock_questionary = MagicMock()
        mock_questionary.text.return_value.ask.return_value = "myorg/transcripts"
        monkeypatch.setattr("claude_code_transcripts.questionary", mock_questionary)

        def mock_run(cmd, *args, **kwargs):
            if cmd[0] == "gh" and cmd[1] == "api" and cmd[2] == "user":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="testuser\n", stderr=""
                )
            if cmd[0] == "gh" and cmd[1] == "api":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout='{"sha": "abc123"}', stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", mock_run)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "json",
                str(fixture_path),
                "-o",
                str(tmp_path / "output"),
                "--publish-to-github",
            ],
        )

        # Should have prompted for repo
        mock_questionary.text.assert_called()
        assert (
            "myorg/transcripts" in str(mock_questionary.text.call_args_list)
            or result.exit_code == 0
        )

    def test_publish_uses_default_branch(self, tmp_path, monkeypatch):
        """Test that gh-pages is used as default branch."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        # Track JSON payloads written to temp files
        json_payloads = []

        def mock_run(cmd, *args, **kwargs):
            if cmd[0] == "gh" and cmd[1] == "api" and cmd[2] == "user":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="testuser\n", stderr=""
                )
            if cmd[0] == "gh" and cmd[1] == "api":
                # If this is a PUT with --input, capture the JSON payload
                if "-X" in cmd and "PUT" in cmd and "--input" in cmd:
                    input_idx = cmd.index("--input")
                    input_file = cmd[input_idx + 1]
                    with open(input_file) as f:
                        json_payloads.append(json.load(f))
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout='{"sha": "abc123"}', stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", mock_run)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "json",
                str(fixture_path),
                "-o",
                str(tmp_path / "output"),
                "--publish-to-github",
                "--publish-to-github-repo",
                "myorg/transcripts",
            ],
        )

        assert result.exit_code == 0
        # Check that gh-pages was used in the JSON payloads
        assert len(json_payloads) > 0
        assert all(p.get("branch") == "gh-pages" for p in json_payloads)

    def test_publish_with_custom_branch(self, tmp_path, monkeypatch):
        """Test publishing with custom branch."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        # Track JSON payloads written to temp files
        json_payloads = []

        def mock_run(cmd, *args, **kwargs):
            if cmd[0] == "gh" and cmd[1] == "api" and cmd[2] == "user":
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="testuser\n", stderr=""
                )
            if cmd[0] == "gh" and cmd[1] == "api":
                # If this is a PUT with --input, capture the JSON payload
                if "-X" in cmd and "PUT" in cmd and "--input" in cmd:
                    input_idx = cmd.index("--input")
                    input_file = cmd[input_idx + 1]
                    with open(input_file) as f:
                        json_payloads.append(json.load(f))
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout='{"sha": "abc123"}', stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", mock_run)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "json",
                str(fixture_path),
                "-o",
                str(tmp_path / "output"),
                "--publish-to-github",
                "--publish-to-github-repo",
                "myorg/transcripts",
                "--publish-to-github-branch",
                "html",
            ],
        )

        assert result.exit_code == 0
        # Check that custom branch was used in the JSON payloads
        assert len(json_payloads) > 0
        assert all(p.get("branch") == "html" for p in json_payloads)
