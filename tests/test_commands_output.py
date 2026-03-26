"""Tests for shared output utilities in commands/__init__.py."""

import tempfile
import webbrowser
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from claude_code_transcripts.commands import (
    open_in_browser,
    publish_gist,
    resolve_output,
)


class TestResolveOutput:
    def test_explicit_output_returned_as_path(self):
        output, auto_open = resolve_output("/tmp/mydir", False, False, "session123")
        assert output == Path("/tmp/mydir")
        assert auto_open is False

    def test_output_auto_uses_stem_under_cwd(self):
        output, auto_open = resolve_output(None, True, False, "session123")
        assert output == Path(".") / "session123"
        assert auto_open is False

    def test_output_auto_with_explicit_parent(self):
        output, auto_open = resolve_output("/tmp/parent", True, False, "session123")
        assert output == Path("/tmp/parent") / "session123"
        assert auto_open is False

    def test_no_output_uses_tempdir(self):
        output, auto_open = resolve_output(None, False, False, "session123")
        assert output == Path(tempfile.gettempdir()) / "claude-session-session123"
        assert auto_open is True

    def test_no_output_with_gist_suppresses_auto_open(self):
        output, auto_open = resolve_output(None, False, True, "session123")
        assert auto_open is False

    def test_no_output_with_output_auto_suppresses_auto_open(self):
        output, auto_open = resolve_output(None, True, False, "session123")
        assert auto_open is False


class TestPublishGist:
    def test_calls_inject_and_create_gist(self, tmp_path):
        with (
            patch(
                "claude_code_transcripts.commands.inject_gist_preview_js"
            ) as mock_inject,
            patch("claude_code_transcripts.commands.create_gist") as mock_create,
        ):
            mock_create.return_value = ("abc123", "https://gist.github.com/abc123")
            publish_gist(tmp_path)

        mock_inject.assert_called_once_with(tmp_path)
        mock_create.assert_called_once_with(tmp_path)

    def test_prints_gist_and_preview_urls(self, tmp_path, capsys):
        with (
            patch("claude_code_transcripts.commands.inject_gist_preview_js"),
            patch("claude_code_transcripts.commands.create_gist") as mock_create,
        ):
            mock_create.return_value = ("abc123", "https://gist.github.com/abc123")
            publish_gist(tmp_path)

        out = capsys.readouterr().out
        assert "https://gist.github.com/abc123" in out
        assert "gisthost.github.io" in out
        assert "abc123" in out


class TestOpenInBrowser:
    def test_opens_when_open_browser_true(self, tmp_path):
        (tmp_path / "index.html").write_text("<html/>")
        with patch("webbrowser.open") as mock_open:
            open_in_browser(tmp_path, open_browser=True, auto_open=False)
        mock_open.assert_called_once()
        assert "index.html" in mock_open.call_args[0][0]

    def test_opens_when_auto_open_true(self, tmp_path):
        (tmp_path / "index.html").write_text("<html/>")
        with patch("webbrowser.open") as mock_open:
            open_in_browser(tmp_path, open_browser=False, auto_open=True)
        mock_open.assert_called_once()

    def test_does_not_open_when_both_false(self, tmp_path):
        with patch("webbrowser.open") as mock_open:
            open_in_browser(tmp_path, open_browser=False, auto_open=False)
        mock_open.assert_not_called()

    def test_url_points_to_index_html(self, tmp_path):
        (tmp_path / "index.html").write_text("<html/>")
        with patch("webbrowser.open") as mock_open:
            open_in_browser(tmp_path, open_browser=True, auto_open=False)
        url = mock_open.call_args[0][0]
        assert url.startswith("file://")
        assert url.endswith("index.html")
