"""Tests for shared command utilities in commands/__init__.py."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_code_transcripts.commands import (
    build_project,
    collect_raw_projects,
    copy_jsonl_files,
)


@pytest.fixture
def mock_projects_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        projects_dir = Path(tmpdir)

        project_a = projects_dir / "-home-user-projects-project-a"
        project_a.mkdir(parents=True)
        (project_a / "abc123.jsonl").write_text(
            '{"type": "user", "timestamp": "2025-01-01T10:00:00.000Z", "message": {"role": "user", "content": "Hello from project A"}}\n'
        )
        (project_a / "def456.jsonl").write_text(
            '{"type": "user", "timestamp": "2025-01-02T10:00:00.000Z", "message": {"role": "user", "content": "Second session"}}\n'
        )

        yield projects_dir


@pytest.fixture
def output_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestCollectRawProjects:
    def test_returns_projects_from_path(self, mock_projects_dir):
        result = collect_raw_projects(str(mock_projects_dir))
        assert len(result) == 1
        assert result[0]["name"] == "project-a"
        assert len(result[0]["sessions"]) == 2

    def test_source_none_searches_both_code_and_cowork(self, tmp_path, monkeypatch):
        projects_dir = tmp_path / ".claude" / "projects"
        projects_dir.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        with (
            patch("claude_code_transcripts.commands.find_all_sessions") as mock_all,
            patch(
                "claude_code_transcripts.commands.find_cowork_sessions"
            ) as mock_cowork,
        ):
            mock_all.return_value = []
            mock_cowork.return_value = []
            collect_raw_projects(None)

        mock_all.assert_called_once()
        mock_cowork.assert_called_once()

    def test_source_code_skips_cowork(self, mock_projects_dir):
        with patch(
            "claude_code_transcripts.commands.find_cowork_sessions"
        ) as mock_cowork:
            collect_raw_projects(str(mock_projects_dir))

        mock_cowork.assert_not_called()

    def test_source_cowork_skips_code(self):
        with (
            patch("claude_code_transcripts.commands.find_all_sessions") as mock_all,
            patch(
                "claude_code_transcripts.commands.find_cowork_sessions"
            ) as mock_cowork,
        ):
            mock_cowork.return_value = []
            collect_raw_projects("cowork")

        mock_all.assert_not_called()

    def test_cowork_sessions_mapped_to_cowork_project(self, tmp_path):
        jsonl_file = tmp_path / "session.jsonl"
        jsonl_file.write_text(
            '{"type":"user","timestamp":"2025-01-01T10:00:00.000Z","message":{"role":"user","content":"Hello"}}\n'
        )
        cowork_session = {
            "title": "My cowork session",
            "jsonl_path": jsonl_file,
            "folders": [],
            "mtime": 1700000000.0,
        }

        with patch(
            "claude_code_transcripts.commands.find_cowork_sessions",
            return_value=[cowork_session],
        ):
            result = collect_raw_projects("cowork")

        assert len(result) == 1
        assert result[0]["name"] == "Cowork"
        assert result[0]["sessions"][0]["transcript_label"] == "Claude Cowork"

    def test_include_agents_passed_through(self, mock_projects_dir):
        with patch("claude_code_transcripts.commands.find_all_sessions") as mock_all:
            mock_all.return_value = []
            collect_raw_projects(str(mock_projects_dir), include_agents=True)

        mock_all.assert_called_once_with(mock_projects_dir, include_agents=True)

    def test_missing_source_dir_raises(self, tmp_path):
        import click

        with pytest.raises(click.ClickException, match="not found"):
            collect_raw_projects(str(tmp_path / "nonexistent"))


class TestBuildProject:
    def test_returns_project_with_sessions(self, mock_projects_dir, output_dir):
        from claude_code_transcripts.commands import collect_raw_projects

        raw_projects = collect_raw_projects(str(mock_projects_dir))
        project = build_project(raw_projects[0], output_dir)

        assert project.name == "project-a"
        assert len(project.sessions) == 2

    def test_session_dirs_nested_under_output(self, mock_projects_dir, output_dir):
        raw_projects = collect_raw_projects(str(mock_projects_dir))
        project = build_project(raw_projects[0], output_dir)

        for session in project.sessions:
            assert session.session_dir.parent == output_dir / "project-a"

    def test_default_transcript_label(self, mock_projects_dir, output_dir):
        raw_projects = collect_raw_projects(str(mock_projects_dir))
        project = build_project(raw_projects[0], output_dir)

        for session in project.sessions:
            assert session.transcript_label == "Claude Code"

    def test_cowork_transcript_label_preserved(self, tmp_path, output_dir):
        jsonl_file = tmp_path / "session.jsonl"
        jsonl_file.write_text(
            '{"type":"user","timestamp":"2025-01-01T10:00:00.000Z","message":{"role":"user","content":"Hello"}}\n'
        )
        raw_project = {
            "name": "Cowork",
            "sessions": [
                {
                    "path": jsonl_file,
                    "summary": "Hello",
                    "mtime": 1700000000.0,
                    "size": jsonl_file.stat().st_size,
                    "transcript_label": "Claude Cowork",
                }
            ],
        }

        project = build_project(raw_project, output_dir)
        assert project.sessions[0].transcript_label == "Claude Cowork"


class TestCopyJsonlFiles:
    def test_copies_jsonl_into_session_dirs(self, mock_projects_dir, output_dir):
        raw_projects = collect_raw_projects(str(mock_projects_dir))
        raw_project = raw_projects[0]
        project = build_project(raw_project, output_dir)

        # Generate output dirs so copy has somewhere to write
        from claude_code_transcripts.html_generation import generate_batch_html

        generate_batch_html([project], output_dir)

        copy_jsonl_files(raw_project, output_dir)

        assert (output_dir / "project-a" / "abc123" / "abc123.jsonl").exists()
        assert (output_dir / "project-a" / "def456" / "def456.jsonl").exists()
