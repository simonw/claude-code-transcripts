"""Tests for the new unified UI feature for viewing transcript history."""

import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from claude_code_transcripts import (
    cli,
    generate_html,
    generate_unified_html,
)


@pytest.fixture
def sample_session():
    """Load the sample session fixture."""
    fixture_path = Path(__file__).parent / "sample_session.json"
    with open(fixture_path) as f:
        return json.load(f)


@pytest.fixture
def output_dir():
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestNewUiCliFlag:
    """Tests for the --new-ui CLI flag."""

    def test_json_command_has_new_ui_flag(self):
        """Test that the json command accepts --new-ui flag."""
        runner = CliRunner()
        fixture_path = Path(__file__).parent / "sample_session.json"

        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(
                cli,
                ["json", str(fixture_path), "-o", tmpdir, "--new-ui"],
            )

            assert result.exit_code == 0
            # Should generate unified.html instead of multiple pages
            assert (Path(tmpdir) / "unified.html").exists()

    def test_local_command_has_new_ui_flag(self, tmp_path, monkeypatch):
        """Test that the local command accepts --new-ui flag."""
        import questionary

        # Create mock .claude/projects structure
        projects_dir = tmp_path / ".claude" / "projects" / "test-project"
        projects_dir.mkdir(parents=True)

        session_file = projects_dir / "session-123.jsonl"
        session_file.write_text(
            '{"type":"summary","summary":"Test session"}\n'
            '{"type":"user","timestamp":"2025-01-01T00:00:00Z","message":{"role":"user","content":"Hello"}}\n'
            '{"type":"assistant","timestamp":"2025-01-01T00:00:01Z","message":{"role":"assistant","content":[{"type":"text","text":"Hi"}]}}\n'
        )

        # Mock Path.home() to return our tmp_path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Mock questionary.select to return the session file
        class MockSelect:
            def __init__(self, *args, **kwargs):
                pass

            def ask(self):
                return session_file

        monkeypatch.setattr(questionary, "select", MockSelect)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(cli, ["local", "-o", str(output_dir), "--new-ui"])

        assert result.exit_code == 0
        assert (output_dir / "unified.html").exists()

    def test_new_ui_flag_generates_single_file(self, output_dir):
        """Test that --new-ui generates a single unified.html file."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["json", str(fixture_path), "-o", str(output_dir), "--new-ui"],
        )

        assert result.exit_code == 0
        # Should have unified.html
        assert (output_dir / "unified.html").exists()
        # Should NOT have paginated files
        assert not (output_dir / "page-001.html").exists()
        assert not (output_dir / "index.html").exists()


class TestGenerateUnifiedHtml:
    """Tests for the generate_unified_html function."""

    def test_generates_unified_html(self, output_dir):
        """Test that generate_unified_html creates a unified.html file."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        assert (output_dir / "unified.html").exists()

    def test_unified_html_contains_all_messages(self, output_dir):
        """Test that unified.html contains all messages from the session."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should contain user and assistant messages
        assert "User" in html or "user" in html
        assert "Assistant" in html or "assistant" in html

    def test_unified_html_has_sidebar_navigation(self, output_dir):
        """Test that unified.html includes a sidebar navigation."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have sidebar navigation
        assert 'id="sidebar"' in html or 'class="sidebar"' in html
        # Should have nav links
        assert 'class="nav-link"' in html or 'class="sidebar-link"' in html

    def test_unified_html_has_search_functionality(self, output_dir):
        """Test that unified.html includes search functionality."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have search input
        assert 'id="search-input"' in html or 'id="unified-search"' in html
        # Should have search-related JavaScript
        assert "search" in html.lower()

    def test_unified_html_has_section_anchors(self, output_dir):
        """Test that unified.html has anchor IDs for each section."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have section anchors with IDs
        assert 'id="section-' in html or 'id="prompt-' in html


class TestUnifiedHtmlSidebar:
    """Tests for the sidebar navigation in unified HTML."""

    def test_sidebar_has_prompt_links(self, output_dir):
        """Test that sidebar contains links to each prompt section."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Sidebar should have links with href pointing to sections
        assert 'href="#section-' in html or 'href="#prompt-' in html

    def test_sidebar_shows_prompt_previews(self, output_dir):
        """Test that sidebar shows preview text for each prompt."""
        # Create a session with known prompts
        session_data = {
            "loglines": [
                {
                    "type": "user",
                    "timestamp": "2025-01-01T10:00:00.000Z",
                    "message": {"content": "First test prompt", "role": "user"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2025-01-01T10:00:05.000Z",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Response 1"}],
                    },
                },
                {
                    "type": "user",
                    "timestamp": "2025-01-01T11:00:00.000Z",
                    "message": {"content": "Second test prompt", "role": "user"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2025-01-01T11:00:05.000Z",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Response 2"}],
                    },
                },
            ]
        }

        session_file = output_dir / "test_session.json"
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        generate_unified_html(session_file, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # The sidebar should show the prompt text (or truncated version)
        assert "First test" in html
        assert "Second test" in html

    def test_sidebar_is_fixed_position(self, output_dir):
        """Test that sidebar has fixed/sticky positioning CSS."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # CSS should include fixed or sticky positioning for sidebar
        assert "position: fixed" in html or "position: sticky" in html


class TestUnifiedHtmlSearch:
    """Tests for the search functionality in unified HTML."""

    def test_search_filters_content(self, output_dir):
        """Test that search JavaScript can filter content."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have JavaScript for filtering/searching
        assert "filter" in html.lower() or "search" in html.lower()
        # Should handle input events
        assert "input" in html or "keyup" in html or "keydown" in html

    def test_search_highlights_matches(self, output_dir):
        """Test that search highlights matching text."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have highlighting capability (mark element or highlight class)
        assert "mark" in html.lower() or "highlight" in html.lower()

    def test_search_updates_url(self, output_dir):
        """Test that search updates URL with query parameter."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should update URL hash or query param
        assert "location.hash" in html or "history." in html


class TestUnifiedHtmlScrolling:
    """Tests for smooth scrolling and navigation in unified HTML."""

    def test_sidebar_links_scroll_to_sections(self, output_dir):
        """Test that clicking sidebar links scrolls to the section."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have smooth scrolling behavior
        assert "scroll-behavior: smooth" in html or "scrollIntoView" in html

    def test_active_section_highlighted_in_sidebar(self, output_dir):
        """Test that current section is highlighted in sidebar during scroll."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have scroll event handling for active state
        assert "scroll" in html.lower()
        # Should have active class or similar for highlighting
        assert "active" in html.lower()


class TestUnifiedHtmlResponsive:
    """Tests for responsive design of unified HTML."""

    def test_sidebar_collapses_on_mobile(self, output_dir):
        """Test that sidebar has responsive behavior for mobile."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have media query for mobile
        assert "@media" in html
        # Should have toggle or collapse mechanism
        assert (
            "toggle" in html.lower()
            or "collapse" in html.lower()
            or "hidden" in html.lower()
        )


class TestUnifiedHtmlStats:
    """Tests for statistics display in unified HTML."""

    def test_shows_session_stats(self, output_dir):
        """Test that unified HTML shows session statistics."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should show stats like number of prompts, messages, tool calls
        assert "prompt" in html.lower()
        assert "message" in html.lower() or "tool" in html.lower()

    def test_shows_timestamps(self, output_dir):
        """Test that unified HTML displays timestamps."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have timestamp elements
        assert "<time" in html or "timestamp" in html.lower()
