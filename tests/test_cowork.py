"""Tests for Claude Cowork session discovery."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from click.testing import CliRunner

from claude_code_transcripts import cli
from claude_code_transcripts.sessions import find_cowork_sessions
from claude_code_transcripts.parser import parse_session_file


def make_cowork_session(
    base_dir,
    org_uuid="org-123",
    workspace_uuid="ws-456",
    session_uuid="sess-789",
    process_name="quirky-eager-fermat",
    cli_session_id="cli-abc",
    title="Review VIMA model",
    last_activity_at=1700000000000,
    folders=None,
    jsonl_content=None,
):
    """Helper to create a mock Cowork session directory structure."""
    if folders is None:
        folders = ["/Users/test/Documents"]

    # Create metadata JSON
    org_dir = base_dir / org_uuid / workspace_uuid
    org_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "sessionId": f"local_{session_uuid}",
        "processName": process_name,
        "cliSessionId": cli_session_id,
        "title": title,
        "initialMessage": f"Initial: {title}",
        "userSelectedFolders": folders,
        "createdAt": last_activity_at - 60000,
        "lastActivityAt": last_activity_at,
        "model": "claude-opus-4-5",
    }
    metadata_file = org_dir / f"local_{session_uuid}.json"
    metadata_file.write_text(json.dumps(metadata))

    # Create JSONL file at expected path
    jsonl_dir = (
        org_dir
        / f"local_{session_uuid}"
        / ".claude"
        / "projects"
        / f"-sessions-{process_name}"
    )
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = jsonl_dir / f"{cli_session_id}.jsonl"

    if jsonl_content is None:
        jsonl_content = (
            '{"type":"queue-operation","data":{}}\n'
            '{"type":"user","timestamp":"2025-01-01T10:00:00.000Z","message":{"role":"user","content":"Hello"}}\n'
            '{"type":"assistant","timestamp":"2025-01-01T10:00:05.000Z","message":{"role":"assistant","content":[{"type":"text","text":"Hi!"}]}}\n'
        )
    jsonl_file.write_text(jsonl_content)

    return metadata_file, jsonl_file


def test_find_cowork_sessions_default_path_uses_platformdirs(tmp_path):
    """Default base_dir is derived from platformdirs.user_data_dir."""
    fake_data_dir = str(tmp_path / "Claude")

    with patch(
        "claude_code_transcripts.sessions.user_data_dir", return_value=fake_data_dir
    ):
        result = find_cowork_sessions()

    assert result == []  # directory doesn't exist, so returns []


def test_find_cowork_sessions_empty(tmp_path):
    """Returns [] when base dir doesn't exist."""
    non_existent = tmp_path / "does-not-exist"
    result = find_cowork_sessions(base_dir=non_existent)
    assert result == []


def test_find_cowork_sessions_finds_sessions(tmp_path):
    """Finds sessions and returns correct metadata."""
    make_cowork_session(tmp_path, title="My Test Session", folders=["/Users/test/Work"])

    result = find_cowork_sessions(base_dir=tmp_path)

    assert len(result) == 1
    session = result[0]
    assert session["title"] == "My Test Session"
    assert isinstance(session["jsonl_path"], Path)
    assert session["jsonl_path"].exists()
    assert session["folders"] == ["/Users/test/Work"]
    assert isinstance(session["mtime"], float)


def test_find_cowork_sessions_skips_missing_jsonl(tmp_path):
    """Skips sessions where the JSONL file doesn't exist."""
    org_dir = tmp_path / "org-123" / "ws-456"
    org_dir.mkdir(parents=True)

    # Create metadata without the JSONL file
    metadata = {
        "sessionId": "local_sess-999",
        "processName": "test-process",
        "cliSessionId": "missing-cli",
        "title": "Missing JSONL",
        "initialMessage": "test",
        "userSelectedFolders": [],
        "createdAt": 1700000000000,
        "lastActivityAt": 1700000000000,
        "model": "claude-opus-4-5",
    }
    (org_dir / "local_sess-999.json").write_text(json.dumps(metadata))
    # No JSONL file created

    result = find_cowork_sessions(base_dir=tmp_path)
    assert result == []


def test_find_cowork_sessions_sorted_by_mtime(tmp_path):
    """Returns sessions sorted by lastActivityAt, most recent first."""
    make_cowork_session(
        tmp_path,
        session_uuid="old-session",
        process_name="old-process",
        cli_session_id="old-cli",
        title="Older Session",
        last_activity_at=1700000000000,
    )
    make_cowork_session(
        tmp_path,
        session_uuid="new-session",
        process_name="new-process",
        cli_session_id="new-cli",
        title="Newer Session",
        last_activity_at=1700001000000,
    )

    result = find_cowork_sessions(base_dir=tmp_path)

    assert len(result) == 2
    assert result[0]["title"] == "Newer Session"
    assert result[1]["title"] == "Older Session"


def test_find_cowork_sessions_limit(tmp_path):
    """Respects the limit parameter."""
    for i in range(5):
        make_cowork_session(
            tmp_path,
            session_uuid=f"session-{i}",
            process_name=f"process-{i}",
            cli_session_id=f"cli-{i}",
            title=f"Session {i}",
            last_activity_at=1700000000000 + i * 1000,
        )

    result = find_cowork_sessions(base_dir=tmp_path, limit=3)
    assert len(result) == 3


def test_cowork_jsonl_parses_with_queue_operation(tmp_path):
    """Verifies parse_session_file handles Cowork JSONL with queue-operation first line."""
    jsonl_content = (
        '{"type":"queue-operation","data":{"some":"data"}}\n'
        '{"type":"user","timestamp":"2025-01-01T10:00:00.000Z","message":{"role":"user","content":"Hello cowork"}}\n'
        '{"type":"assistant","timestamp":"2025-01-01T10:00:05.000Z","message":{"role":"assistant","content":[{"type":"text","text":"Hi from cowork!"}]}}\n'
    )
    jsonl_file = tmp_path / "session.jsonl"
    jsonl_file.write_text(jsonl_content)

    loglines = parse_session_file(jsonl_file)

    # queue-operation should be filtered out
    assert len(loglines) == 2
    assert loglines[0]["type"] == "user"
    assert loglines[1]["type"] == "assistant"
    # Content should be correct
    assert loglines[0]["message"]["content"] == "Hello cowork"


def test_parse_jsonl_skips_is_meta(tmp_path):
    """User entries with isMeta=true are treated as system messages and skipped."""
    jsonl_content = (
        '{"type":"user","timestamp":"2025-01-01T10:00:00.000Z","isMeta":true,"message":{"role":"user","content":"system meta message"}}\n'
        '{"type":"user","timestamp":"2025-01-01T10:00:01.000Z","message":{"role":"user","content":"Hello"}}\n'
        '{"type":"assistant","timestamp":"2025-01-01T10:00:05.000Z","message":{"role":"assistant","content":[{"type":"text","text":"Hi!"}]}}\n'
    )
    jsonl_file = tmp_path / "session.jsonl"
    jsonl_file.write_text(jsonl_content)

    loglines = parse_session_file(jsonl_file)

    assert len(loglines) == 2
    assert loglines[0]["message"]["content"] == "Hello"
    assert loglines[1]["type"] == "assistant"


def test_parse_jsonl_uses_audit_timestamp_fallback(tmp_path):
    """Entries without 'timestamp' fall back to '_audit_timestamp'."""
    jsonl_content = (
        '{"type":"user","_audit_timestamp":"2025-01-01T10:00:00.000Z","message":{"role":"user","content":"Hello"}}\n'
        '{"type":"assistant","_audit_timestamp":"2025-01-01T10:00:05.000Z","message":{"role":"assistant","content":[{"type":"text","text":"Hi!"}]}}\n'
    )
    jsonl_file = tmp_path / "session.jsonl"
    jsonl_file.write_text(jsonl_content)

    loglines = parse_session_file(jsonl_file)

    assert len(loglines) == 2
    assert loglines[0]["timestamp"] == "2025-01-01T10:00:00.000Z"
    assert loglines[1]["timestamp"] == "2025-01-01T10:00:05.000Z"


def test_parse_jsonl_skips_is_synthetic(tmp_path):
    """User entries with isSynthetic=true are treated as system messages and skipped."""
    jsonl_content = (
        '{"type":"user","timestamp":"2025-01-01T10:00:00.000Z","isSynthetic":true,"message":{"role":"user","content":"synthetic message"}}\n'
        '{"type":"user","timestamp":"2025-01-01T10:00:01.000Z","message":{"role":"user","content":"Real message"}}\n'
        '{"type":"assistant","timestamp":"2025-01-01T10:00:05.000Z","message":{"role":"assistant","content":[{"type":"text","text":"Hi!"}]}}\n'
    )
    jsonl_file = tmp_path / "session.jsonl"
    jsonl_file.write_text(jsonl_content)

    loglines = parse_session_file(jsonl_file)

    assert len(loglines) == 2
    assert loglines[0]["message"]["content"] == "Real message"
    assert loglines[1]["type"] == "assistant"


def make_code_session(tmp_path, name="session.jsonl"):
    """Create a minimal Code session JSONL file."""
    session_file = tmp_path / name
    session_file.write_text(
        '{"type":"summary","summary":"Test session"}\n'
        '{"type":"user","timestamp":"2025-01-01T00:00:00Z","message":{"role":"user","content":"Hello"}}\n'
    )
    return session_file


class TestLocalSourceFlag:
    """Tests for the --source flag behavior in the local command."""

    def cancel_select(self, mock_q):
        mock_q.select.return_value.ask.return_value = None

    def test_source_code_skips_cowork(self, tmp_path):
        """--source code queries Code sessions and never calls find_cowork_sessions."""
        runner = CliRunner()
        with (
            patch(
                "claude_code_transcripts.commands.local.find_local_sessions"
            ) as mock_local,
            patch(
                "claude_code_transcripts.commands.local.find_cowork_sessions"
            ) as mock_cowork,
            patch("claude_code_transcripts.commands.local.questionary") as mock_q,
        ):
            mock_local.return_value = []
            self.cancel_select(mock_q)
            result = runner.invoke(cli, ["local", "--source", "code"])

        assert result.exit_code == 0
        mock_cowork.assert_not_called()

    def test_source_cowork_skips_code(self, tmp_path):
        """--source cowork queries Cowork sessions and never calls find_local_sessions."""
        runner = CliRunner()
        with (
            patch(
                "claude_code_transcripts.commands.local.find_local_sessions"
            ) as mock_local,
            patch(
                "claude_code_transcripts.commands.local.find_cowork_sessions"
            ) as mock_cowork,
            patch("claude_code_transcripts.commands.local.questionary") as mock_q,
        ):
            mock_cowork.return_value = []
            self.cancel_select(mock_q)
            result = runner.invoke(cli, ["local", "--source", "cowork"])

        assert result.exit_code == 0
        mock_local.assert_not_called()
        mock_cowork.assert_called_once()

    def test_source_path_uses_that_path_and_skips_cowork(self, tmp_path):
        """--source <path> searches Code at that path and never calls find_cowork_sessions."""
        runner = CliRunner()
        with (
            patch(
                "claude_code_transcripts.commands.local.find_local_sessions"
            ) as mock_local,
            patch(
                "claude_code_transcripts.commands.local.find_cowork_sessions"
            ) as mock_cowork,
            patch("claude_code_transcripts.commands.local.questionary") as mock_q,
        ):
            mock_local.return_value = []
            self.cancel_select(mock_q)
            result = runner.invoke(cli, ["local", "--source", str(tmp_path)])

        assert result.exit_code == 0
        mock_local.assert_called_once_with(tmp_path, limit=10)
        mock_cowork.assert_not_called()

    def test_no_source_searches_both(self, tmp_path, monkeypatch):
        """No --source calls both find_local_sessions and find_cowork_sessions."""
        projects_dir = tmp_path / ".claude" / "projects"
        projects_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        runner = CliRunner()
        with (
            patch(
                "claude_code_transcripts.commands.local.find_local_sessions"
            ) as mock_local,
            patch(
                "claude_code_transcripts.commands.local.find_cowork_sessions"
            ) as mock_cowork,
            patch("claude_code_transcripts.commands.local.questionary") as mock_q,
        ):
            mock_local.return_value = []
            mock_cowork.return_value = []
            self.cancel_select(mock_q)
            result = runner.invoke(cli, ["local"])

        assert result.exit_code == 0
        mock_local.assert_called_once()
        mock_cowork.assert_called_once()

    def test_limit_filled_by_code_skips_cowork(self, tmp_path, monkeypatch):
        """When Code sessions fill the limit, find_cowork_sessions is not called."""
        projects_dir = tmp_path / ".claude" / "projects"
        projects_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        session_files = [make_code_session(tmp_path, f"s{i}.jsonl") for i in range(3)]

        runner = CliRunner()
        with (
            patch(
                "claude_code_transcripts.commands.local.find_local_sessions"
            ) as mock_local,
            patch(
                "claude_code_transcripts.commands.local.find_cowork_sessions"
            ) as mock_cowork,
            patch("claude_code_transcripts.commands.local.questionary") as mock_q,
        ):
            mock_local.return_value = [(f, "Summary") for f in session_files]
            self.cancel_select(mock_q)
            result = runner.invoke(cli, ["local", "--limit", "3"])

        assert result.exit_code == 0
        mock_cowork.assert_not_called()

    def test_limit_not_filled_cowork_gets_remaining_slots(self, tmp_path, monkeypatch):
        """When Code sessions don't fill the limit, Cowork is queried with remaining count."""
        projects_dir = tmp_path / ".claude" / "projects"
        projects_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        session_file = make_code_session(tmp_path)

        runner = CliRunner()
        with (
            patch(
                "claude_code_transcripts.commands.local.find_local_sessions"
            ) as mock_local,
            patch(
                "claude_code_transcripts.commands.local.find_cowork_sessions"
            ) as mock_cowork,
            patch("claude_code_transcripts.commands.local.questionary") as mock_q,
        ):
            mock_local.return_value = [(session_file, "Summary")]
            mock_cowork.return_value = []
            self.cancel_select(mock_q)
            result = runner.invoke(cli, ["local", "--limit", "3"])

        assert result.exit_code == 0
        mock_cowork.assert_called_once_with(limit=2)


def test_code_command_proxies_to_local_with_code_source():
    """The code command invokes local_cmd with source='code', skipping Cowork."""
    with (
        patch(
            "claude_code_transcripts.commands.local.find_local_sessions"
        ) as mock_local,
        patch(
            "claude_code_transcripts.commands.local.find_cowork_sessions"
        ) as mock_cowork,
        patch("claude_code_transcripts.commands.local.questionary") as mock_q,
    ):
        mock_local.return_value = []
        mock_q.select.return_value.ask.return_value = None
        result = CliRunner().invoke(cli, ["code"])

    assert result.exit_code == 0
    mock_cowork.assert_not_called()


def test_cowork_command_proxies_to_local_with_cowork_source():
    """The cowork command invokes local_cmd with source='cowork', skipping Code."""
    with (
        patch(
            "claude_code_transcripts.commands.local.find_local_sessions"
        ) as mock_local,
        patch(
            "claude_code_transcripts.commands.local.find_cowork_sessions"
        ) as mock_cowork,
        patch("claude_code_transcripts.commands.local.questionary") as mock_q,
    ):
        mock_cowork.return_value = []
        mock_q.select.return_value.ask.return_value = None
        result = CliRunner().invoke(cli, ["cowork"])

    assert result.exit_code == 0
    mock_local.assert_not_called()


def test_local_command_passes_cowork_label_for_cowork_sessions(tmp_path):
    """The local command passes transcript_label='Claude Cowork' for Cowork sessions."""
    _, jsonl_file = make_cowork_session(
        tmp_path,
        process_name="test-process",
        cli_session_id="cli-label",
        title="Label Test",
    )
    output_dir = tmp_path / "output"
    session = {
        "title": "Label Test",
        "jsonl_path": jsonl_file,
        "folders": ["/test"],
        "mtime": 1700000000.0,
    }
    selected = {
        "mtime": session["mtime"],
        "size_kb": 1.0,
        "source": "Cowork",
        "title": session["title"],
        "session_file": jsonl_file,
        "transcript_label": "Claude Cowork",
    }

    runner = CliRunner()
    with (
        patch(
            "claude_code_transcripts.commands.local.find_cowork_sessions"
        ) as mock_cowork,
        patch(
            "claude_code_transcripts.commands.local.find_local_sessions"
        ) as mock_local,
        patch("claude_code_transcripts.commands.local.questionary") as mock_q,
        patch("claude_code_transcripts.commands.local.generate_html") as mock_gen,
    ):
        mock_cowork.return_value = [session]
        mock_local.return_value = []
        mock_q.select.return_value.ask.return_value = selected
        result = runner.invoke(
            cli,
            ["local", "-o", str(output_dir)],
        )

    assert result.exit_code == 0, result.output
    mock_gen.assert_called_once()
    call_kwargs = mock_gen.call_args
    assert call_kwargs.kwargs.get("transcript_label") == "Claude Cowork"


def test_local_include_json_copies_jsonl_to_output(tmp_path):
    """--json copies the session JSONL file into the output directory."""
    session_file = make_code_session(tmp_path, "my-session.jsonl")
    output_dir = tmp_path / "output"

    selected = {
        "mtime": session_file.stat().st_mtime,
        "size_kb": 1.0,
        "source": "Code",
        "title": "Test session",
        "session_file": session_file,
        "transcript_label": "Claude Code",
    }

    runner = CliRunner()
    with (
        patch(
            "claude_code_transcripts.commands.local.find_local_sessions"
        ) as mock_local,
        patch(
            "claude_code_transcripts.commands.local.find_cowork_sessions"
        ) as mock_cowork,
        patch("claude_code_transcripts.commands.local.questionary") as mock_q,
        patch("claude_code_transcripts.commands.local.generate_html"),
    ):
        mock_local.return_value = [(session_file, "Test session")]
        mock_cowork.return_value = []
        mock_q.select.return_value.ask.return_value = selected
        result = runner.invoke(cli, ["local", "--json", "-o", str(output_dir)])

    assert result.exit_code == 0, result.output
    assert (output_dir / "my-session.jsonl").exists()


def test_local_without_json_does_not_copy_jsonl(tmp_path):
    """Without --json the session JSONL file is not copied to the output directory."""
    session_file = make_code_session(tmp_path, "my-session.jsonl")
    output_dir = tmp_path / "output"

    selected = {
        "mtime": session_file.stat().st_mtime,
        "size_kb": 1.0,
        "source": "Code",
        "title": "Test session",
        "session_file": session_file,
        "transcript_label": "Claude Code",
    }

    runner = CliRunner()
    with (
        patch(
            "claude_code_transcripts.commands.local.find_local_sessions"
        ) as mock_local,
        patch(
            "claude_code_transcripts.commands.local.find_cowork_sessions"
        ) as mock_cowork,
        patch("claude_code_transcripts.commands.local.questionary") as mock_q,
        patch("claude_code_transcripts.commands.local.generate_html"),
    ):
        mock_local.return_value = [(session_file, "Test session")]
        mock_cowork.return_value = []
        mock_q.select.return_value.ask.return_value = selected
        result = runner.invoke(cli, ["local", "-o", str(output_dir)])

    assert result.exit_code == 0, result.output
    assert not (output_dir / "my-session.jsonl").exists()
