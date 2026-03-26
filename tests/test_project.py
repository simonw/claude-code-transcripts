"""Tests for the project command."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from claude_code_transcripts import cli


@pytest.fixture
def mock_projects_dir():
    """Create a mock ~/.claude/projects structure with test sessions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        projects_dir = Path(tmpdir)

        project_a = projects_dir / "-home-user-projects-project-a"
        project_a.mkdir(parents=True)

        (project_a / "abc123.jsonl").write_text(
            '{"type": "user", "timestamp": "2025-01-01T10:00:00.000Z", "message": {"role": "user", "content": "Hello from project A"}}\n'
            '{"type": "assistant", "timestamp": "2025-01-01T10:00:05.000Z", "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi there!"}]}}\n'
        )
        (project_a / "def456.jsonl").write_text(
            '{"type": "user", "timestamp": "2025-01-02T10:00:00.000Z", "message": {"role": "user", "content": "Second session in project A"}}\n'
            '{"type": "assistant", "timestamp": "2025-01-02T10:00:05.000Z", "message": {"role": "assistant", "content": [{"type": "text", "text": "Got it!"}]}}\n'
        )

        project_b = projects_dir / "-home-user-projects-project-b"
        project_b.mkdir(parents=True)

        (project_b / "ghi789.jsonl").write_text(
            '{"type": "user", "timestamp": "2025-01-04T10:00:00.000Z", "message": {"role": "user", "content": "Hello from project B"}}\n'
            '{"type": "assistant", "timestamp": "2025-01-04T10:00:05.000Z", "message": {"role": "assistant", "content": [{"type": "text", "text": "Welcome!"}]}}\n'
        )

        yield projects_dir


@pytest.fixture
def output_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestProjectCommand:
    def test_project_command_exists(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["project", "--help"])
        assert result.exit_code == 0
        assert "project" in result.output.lower() or "convert" in result.output.lower()

    def test_project_command_picks_project_and_converts(
        self, mock_projects_dir, output_dir
    ):
        """Selecting project-a converts only its sessions."""
        runner = CliRunner()
        with patch(
            "claude_code_transcripts.commands.project.questionary.select"
        ) as mock_select:
            # Simulate user selecting project-a
            mock_select.return_value.ask.return_value = None  # will be overridden below

            # We need to capture what choices are passed and return the right one
            def fake_select(prompt, choices):
                # Pick the choice whose value has name == "project-a"
                for choice in choices:
                    if choice.value["name"] == "project-a":
                        mock_select.return_value.ask.return_value = choice.value
                        break
                return mock_select.return_value

            mock_select.side_effect = fake_select

            result = runner.invoke(
                cli,
                [
                    "project",
                    "--source",
                    str(mock_projects_dir),
                    "--output",
                    str(output_dir),
                ],
            )

        assert result.exit_code == 0, result.output
        # project-a sessions should be generated
        assert (output_dir / "project-a").is_dir()
        assert (output_dir / "project-a" / "abc123" / "index.html").exists()
        assert (output_dir / "project-a" / "def456" / "index.html").exists()
        # project-b should NOT be in the output
        assert not (output_dir / "project-b").exists()

    def test_project_command_no_selection_exits_cleanly(
        self, mock_projects_dir, output_dir
    ):
        """Cancelling the picker exits without error and creates no files."""
        runner = CliRunner()
        with patch(
            "claude_code_transcripts.commands.project.questionary.select"
        ) as mock_select:
            mock_select.return_value.ask.return_value = None

            result = runner.invoke(
                cli,
                [
                    "project",
                    "--source",
                    str(mock_projects_dir),
                    "--output",
                    str(output_dir),
                ],
            )

        assert result.exit_code == 0
        assert not (output_dir / "project-a").exists()

    def test_project_command_no_sessions_found(self, output_dir, tmp_path):
        """Empty source directory exits cleanly."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "project",
                "--source",
                str(empty_dir),
                "--output",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0
        assert "No projects found" in result.output

    def test_project_command_include_json_copies_jsonl(
        self, mock_projects_dir, output_dir
    ):
        """--json flag copies source JSONL files into each session directory."""
        runner = CliRunner()
        with patch(
            "claude_code_transcripts.commands.project.questionary.select"
        ) as mock_select:

            def fake_select(prompt, choices):
                for choice in choices:
                    if choice.value["name"] == "project-a":
                        mock_select.return_value.ask.return_value = choice.value
                        break
                return mock_select.return_value

            mock_select.side_effect = fake_select

            result = runner.invoke(
                cli,
                [
                    "project",
                    "--source",
                    str(mock_projects_dir),
                    "--output",
                    str(output_dir),
                    "--json",
                ],
            )

        assert result.exit_code == 0, result.output
        assert (output_dir / "project-a" / "abc123" / "abc123.jsonl").exists()
        assert (output_dir / "project-a" / "def456" / "def456.jsonl").exists()

    def test_project_command_shows_session_count_in_picker(
        self, mock_projects_dir, output_dir
    ):
        """The picker choices include session counts."""
        runner = CliRunner()
        captured_choices = []

        with patch(
            "claude_code_transcripts.commands.project.questionary.select"
        ) as mock_select:

            def fake_select(prompt, choices):
                captured_choices.extend(choices)
                mock_select.return_value.ask.return_value = None
                return mock_select.return_value

            mock_select.side_effect = fake_select

            runner.invoke(
                cli,
                [
                    "project",
                    "--source",
                    str(mock_projects_dir),
                    "--output",
                    str(output_dir),
                ],
            )

        assert len(captured_choices) == 2
        titles = [c.title for c in captured_choices]
        # Both project names should appear
        assert any("project-a" in t for t in titles)
        assert any("project-b" in t for t in titles)
        # Session counts should appear
        assert any("2" in t for t in titles)  # project-a has 2 sessions
        assert any("1" in t for t in titles)  # project-b has 1 session
