"""Tests for the publish subcommand and gist preview JS idempotency."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from claude_code_transcripts import (
    cli,
    inject_gist_preview_js,
    GIST_PREVIEW_JS,
)


@pytest.fixture
def output_dir():
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestInjectGistPreviewJsIdempotency:
    """Tests for inject_gist_preview_js idempotency behaviour."""

    def test_running_inject_twice_does_not_duplicate_script(self, output_dir):
        """Running inject twice does not duplicate the script."""
        html = output_dir / "index.html"
        html.write_text("<html><body></body></html>")
        inject_gist_preview_js(output_dir)
        inject_gist_preview_js(output_dir)
        content = html.read_text()
        assert content.count(GIST_PREVIEW_JS) == 1


class TestPublishCommand:
    """Tests for the publish CLI subcommand."""

    def test_errors_when_directory_does_not_exist(self):
        """publish errors when directory does not exist."""
        runner = CliRunner()
        result = runner.invoke(cli, ["publish", "/nonexistent/path"])
        assert result.exit_code != 0
        assert "does not exist" in result.output or "Error" in result.output

    def test_errors_when_no_html_files(self, output_dir):
        """publish errors when directory has no HTML files."""
        runner = CliRunner()
        result = runner.invoke(cli, ["publish", str(output_dir)])
        assert result.exit_code != 0
        assert "No HTML files" in result.output

    def test_injects_js_and_creates_gist(self, output_dir):
        """publish injects JS and creates gist."""
        runner = CliRunner()
        (output_dir / "index.html").write_text("<html><body></body></html>")
        (output_dir / "page-001.html").write_text("<html><body></body></html>")

        with patch("claude_code_transcripts.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "https://gist.github.com/user/abc123\n"
            mock_run.return_value.returncode = 0
            result = runner.invoke(cli, ["publish", str(output_dir)])

        assert result.exit_code == 0
        assert "gisthost.github.io" in result.output
        assert "abc123" in result.output

        # Verify JS was injected
        content = (output_dir / "index.html").read_text()
        assert GIST_PREVIEW_JS in content

    def test_open_flag_opens_browser(self, output_dir, mock_webbrowser_open):
        """publish --open opens the preview URL in a browser."""
        runner = CliRunner()
        (output_dir / "index.html").write_text("<html><body></body></html>")

        with patch("claude_code_transcripts.subprocess.run") as mock_run:
            mock_run.return_value.stdout = "https://gist.github.com/user/abc123\n"
            mock_run.return_value.returncode = 0
            result = runner.invoke(cli, ["publish", "--open", str(output_dir)])

        assert result.exit_code == 0
        assert len(mock_webbrowser_open) == 1
        assert "gisthost.github.io" in mock_webbrowser_open[0]
