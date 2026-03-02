"""Tests for the sync CLI command."""

import sqlite3
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from claude_code_transcripts import cli
from claude_code_transcripts.db import (
    get_db,
    list_projects,
    list_sessions,
    get_session_page,
)


@pytest.fixture
def mock_projects_dir():
    """Create a mock ~/.claude/projects structure with test sessions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        projects_dir = Path(tmpdir)

        # Create project-a with 2 sessions
        project_a = projects_dir / "-home-user-projects-project-a"
        project_a.mkdir(parents=True)

        session_a1 = project_a / "abc123.jsonl"
        session_a1.write_text(
            '{"type": "user", "timestamp": "2025-01-01T10:00:00.000Z", "message": {"role": "user", "content": "Hello from project A"}}\n'
            '{"type": "assistant", "timestamp": "2025-01-01T10:00:05.000Z", "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi there!"}]}}\n'
        )

        session_a2 = project_a / "def456.jsonl"
        session_a2.write_text(
            '{"type": "user", "timestamp": "2025-01-02T10:00:00.000Z", "message": {"role": "user", "content": "Second session in project A"}}\n'
            '{"type": "assistant", "timestamp": "2025-01-02T10:00:05.000Z", "message": {"role": "assistant", "content": [{"type": "text", "text": "Got it!"}]}}\n'
        )

        # Create project-b with 1 session
        project_b = projects_dir / "-home-user-projects-project-b"
        project_b.mkdir(parents=True)

        session_b1 = project_b / "ghi789.jsonl"
        session_b1.write_text(
            '{"type": "user", "timestamp": "2025-01-04T10:00:00.000Z", "message": {"role": "user", "content": "Hello from project B"}}\n'
            '{"type": "assistant", "timestamp": "2025-01-04T10:00:05.000Z", "message": {"role": "assistant", "content": [{"type": "text", "text": "Welcome!"}]}}\n'
        )

        # Create warmup session (should be skipped)
        warmup = project_b / "warmup123.jsonl"
        warmup.write_text(
            '{"type": "user", "timestamp": "2025-01-05T10:00:00.000Z", "message": {"role": "user", "content": "warmup"}}\n'
        )

        yield projects_dir


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


class TestSyncCommand:
    def test_imports_sessions_into_sqlite(self, mock_projects_dir, db_path):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["sync", "--source", str(mock_projects_dir), "--db", str(db_path)],
        )
        assert result.exit_code == 0
        assert "Synced 3 new sessions" in result.output

        # Verify database contents
        conn = get_db(db_path)
        projects = list_projects(conn)
        assert len(projects) == 2
        conn.close()

    def test_dedup_on_second_run(self, mock_projects_dir, db_path):
        runner = CliRunner()
        # First run
        runner.invoke(
            cli,
            ["sync", "--source", str(mock_projects_dir), "--db", str(db_path)],
        )
        # Second run should find 0 new
        result = runner.invoke(
            cli,
            ["sync", "--source", str(mock_projects_dir), "--db", str(db_path)],
        )
        assert result.exit_code == 0
        assert "Synced 0 new sessions" in result.output
        assert "3 already present" in result.output

    def test_stores_html_pages(self, mock_projects_dir, db_path):
        runner = CliRunner()
        runner.invoke(
            cli,
            ["sync", "--source", str(mock_projects_dir), "--db", str(db_path)],
        )
        conn = get_db(db_path)
        # Each session should have at least an index.html and a page-001.html
        html = get_session_page(conn, "abc123", "index.html")
        assert html is not None
        assert "<html" in html.lower() or "<!doctype" in html.lower()

        html = get_session_page(conn, "abc123", "page-001.html")
        assert html is not None
        conn.close()

    def test_stores_session_metadata(self, mock_projects_dir, db_path):
        runner = CliRunner()
        runner.invoke(
            cli,
            ["sync", "--source", str(mock_projects_dir), "--db", str(db_path)],
        )
        conn = get_db(db_path)
        sessions = list_sessions(conn, "project-a")
        assert len(sessions) == 2
        # Check that summaries are populated
        summaries = {s["session_id"]: s["summary"] for s in sessions}
        assert "abc123" in summaries
        assert "Hello from project A" in summaries["abc123"]
        conn.close()

    def test_quiet_mode(self, mock_projects_dir, db_path):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "sync",
                "--source",
                str(mock_projects_dir),
                "--db",
                str(db_path),
                "--quiet",
            ],
        )
        assert result.exit_code == 0
        # Should only show the final summary line
        lines = result.output.strip().split("\n")
        assert len(lines) == 1
        assert "Synced" in lines[0]

    def test_nonexistent_source_dir(self, db_path):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["sync", "--source", "/nonexistent/path", "--db", str(db_path)],
        )
        assert result.exit_code == 0
        assert "No sessions found" in result.output

    def test_stores_raw_session_json(self, mock_projects_dir, db_path):
        runner = CliRunner()
        runner.invoke(
            cli,
            ["sync", "--source", str(mock_projects_dir), "--db", str(db_path)],
        )
        conn = get_db(db_path)
        row = conn.execute(
            "SELECT session_json FROM sessions WHERE session_id = ?", ("abc123",)
        ).fetchone()
        assert row is not None
        assert "Hello from project A" in row[0]
        conn.close()
