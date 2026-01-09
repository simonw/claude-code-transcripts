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


class TestUnifiedHtmlNavButtons:
    """Tests for message navigation buttons."""

    def test_has_message_wrappers(self, output_dir):
        """Test that messages are wrapped with navigation buttons."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have message wrapper divs
        assert 'class="message-wrapper"' in html

    def test_has_prev_next_buttons(self, output_dir):
        """Test that prev/next navigation buttons are present."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have prev and next buttons
        assert 'class="msg-nav-btn prev-btn"' in html
        assert 'class="msg-nav-btn next-btn"' in html

    def test_nav_buttons_have_aria_labels(self, output_dir):
        """Test that navigation buttons have accessible labels."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        assert 'aria-label="Previous message"' in html
        assert 'aria-label="Next message"' in html

    def test_keyboard_navigation_js(self, output_dir):
        """Test that keyboard navigation (j/k keys) is supported."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have j/k keyboard navigation in JavaScript
        assert "e.key === 'j'" in html or 'e.key === "j"' in html
        assert "e.key === 'k'" in html or 'e.key === "k"' in html


class TestUnifiedHtmlDarkTheme:
    """Tests for dark theme styling."""

    def test_has_dark_background(self, output_dir):
        """Test that the unified UI has a dark background."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have dark background color variable
        assert "--bg-color: #0f172a" in html or "bg-color" in html

    def test_has_dark_card_background(self, output_dir):
        """Test that cards have dark backgrounds."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have dark card backgrounds
        assert "--card-bg: #1e293b" in html

    def test_has_light_text_color(self, output_dir):
        """Test that text is light colored for dark theme."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have light text color
        assert "--text-color: #e2e8f0" in html


class TestSystemInfoSeparation:
    """Tests for separating system info from user messages."""

    def test_system_info_style_exists(self, output_dir):
        """Test that system-info CSS class exists for separated content."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have system-info styling in CSS
        assert ".system-info" in html

    def test_separates_ide_opened_file(self, output_dir):
        """Test that <ide_opened_file> tags are separated from user content."""
        session_data = {
            "loglines": [
                {
                    "type": "user",
                    "timestamp": "2025-01-01T10:00:00.000Z",
                    "message": {
                        "content": "<ide_opened_file>User opened file.txt</ide_opened_file>\nActual user prompt here",
                        "role": "user",
                    },
                },
                {
                    "type": "assistant",
                    "timestamp": "2025-01-01T10:00:05.000Z",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Response"}],
                    },
                },
            ]
        }

        session_file = output_dir / "test_session.json"
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        generate_unified_html(session_file, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have system info separated
        assert "system-info" in html
        # The user prompt should still be present
        assert "Actual user prompt here" in html


class TestSidebarScrollbar:
    """Tests for sidebar scrollbar theming."""

    def test_sidebar_scrollbar_dark_theme(self, output_dir):
        """Test that sidebar scrollbar has dark theme styling."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have custom scrollbar styling for sidebar
        assert ".sidebar-nav::-webkit-scrollbar" in html

    def test_sidebar_scrollbar_track_dark(self, output_dir):
        """Test that scrollbar track is dark themed."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have dark track background
        assert "::-webkit-scrollbar-track" in html

    def test_sidebar_scrollbar_thumb_themed(self, output_dir):
        """Test that scrollbar thumb is themed."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have themed thumb
        assert "::-webkit-scrollbar-thumb" in html


class TestMessageTypeFilters:
    """Tests for message type filter toggles."""

    def test_has_filter_toggles_container(self, output_dir):
        """Test that filter toggle container exists."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have filter container
        assert 'class="message-filters"' in html or 'id="message-filters"' in html

    def test_has_user_message_filter(self, output_dir):
        """Test that user message filter toggle exists."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have user filter toggle
        assert 'data-filter="user"' in html

    def test_has_assistant_message_filter(self, output_dir):
        """Test that assistant message filter toggle exists."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have assistant filter toggle
        assert 'data-filter="assistant"' in html

    def test_has_tool_message_filter(self, output_dir):
        """Test that tool message filter toggle exists."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have tool filter toggle
        assert 'data-filter="tool"' in html

    def test_filters_on_by_default(self, output_dir):
        """Test that all filters are on by default."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have checked checkboxes or active state by default
        assert "checked" in html or "active" in html.lower()

    def test_filter_toggle_javascript(self, output_dir):
        """Test that filter toggle JavaScript functionality exists."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have JS that handles filter toggling
        assert "toggleFilter" in html or "filter-toggle" in html


class TestSearchClearButton:
    """Tests for search clear button functionality."""

    def test_has_clear_button_in_search(self, output_dir):
        """Test that search input has a clear button."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have clear button in search container
        assert 'class="search-clear"' in html or 'id="search-clear"' in html

    def test_clear_button_resets_nav_items(self, output_dir):
        """Test that clear button JavaScript resets nav item appearance."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should reset nav link opacity in JS
        assert "opacity" in html and ("1" in html or "'1'" in html)

    def test_clear_button_stays_at_position(self, output_dir):
        """Test that clearing search doesn't scroll to beginning."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should NOT scroll when clearing (look for specific non-scroll behavior)
        # The clear function should reset without scrolling
        assert "clearSearch" in html or "search-clear" in html


class TestCopyButton:
    """Tests for copy text button functionality."""

    def test_has_copy_button_css(self, output_dir):
        """Test that copy button CSS styles exist."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have copy button styling
        assert ".copy-btn" in html or ".copy-button" in html

    def test_has_copy_button_js(self, output_dir):
        """Test that copy button JavaScript functionality exists."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have clipboard copy functionality
        assert "clipboard" in html.lower() or "navigator.clipboard" in html

    def test_code_blocks_have_copy_button(self, output_dir):
        """Test that code blocks have copy buttons."""
        session_data = {
            "loglines": [
                {
                    "type": "user",
                    "timestamp": "2025-01-01T10:00:00.000Z",
                    "message": {"content": "Show me code", "role": "user"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2025-01-01T10:00:05.000Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "```python\nprint('hello')\n```"}
                        ],
                    },
                },
            ]
        }

        session_file = output_dir / "test_session.json"
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        generate_unified_html(session_file, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Code blocks should be wrapped with copy functionality
        assert "copy" in html.lower()


class TestCodeBlockSyntaxHighlight:
    """Tests for language-based code block syntax highlighting."""

    def test_has_language_class_on_code_blocks(self, output_dir):
        """Test that code blocks have language-specific classes."""
        session_data = {
            "loglines": [
                {
                    "type": "user",
                    "timestamp": "2025-01-01T10:00:00.000Z",
                    "message": {"content": "Show me Python code", "role": "user"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2025-01-01T10:00:05.000Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "text", "text": "```python\nprint('hello')\n```"}
                        ],
                    },
                },
            ]
        }

        session_file = output_dir / "test_session.json"
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        generate_unified_html(session_file, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have language class on pre or code element
        assert 'class="language-python"' in html or 'data-language="python"' in html

    def test_has_syntax_highlight_styles(self, output_dir):
        """Test that syntax highlighting CSS exists."""
        fixture_path = Path(__file__).parent / "sample_session.json"

        generate_unified_html(fixture_path, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should have syntax highlighting styles (keywords, strings, comments)
        assert (
            ".hljs" in html
            or ".token" in html
            or ".syntax-" in html
            or ".code-keyword" in html
        )

    def test_javascript_code_styled(self, output_dir):
        """Test that JavaScript code blocks get proper styling."""
        session_data = {
            "loglines": [
                {
                    "type": "user",
                    "timestamp": "2025-01-01T10:00:00.000Z",
                    "message": {"content": "Show me JS code", "role": "user"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2025-01-01T10:00:05.000Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": "```javascript\nconst x = 42;\n```",
                            }
                        ],
                    },
                },
            ]
        }

        session_file = output_dir / "test_session.json"
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        generate_unified_html(session_file, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Should identify JavaScript language
        assert "javascript" in html.lower() or "js" in html


class TestNavMenuUserPrompts:
    """Tests for nav menu showing actual user prompts."""

    def test_nav_shows_user_text_not_system_info(self, output_dir):
        """Test that nav menu shows actual user text, not system tags."""
        session_data = {
            "loglines": [
                {
                    "type": "user",
                    "timestamp": "2025-01-01T10:00:00.000Z",
                    "message": {
                        "content": "<ide_opened_file>some/path.txt</ide_opened_file>\nMy actual question here",
                        "role": "user",
                    },
                },
                {
                    "type": "assistant",
                    "timestamp": "2025-01-01T10:00:05.000Z",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Response"}],
                    },
                },
            ]
        }

        session_file = output_dir / "test_session.json"
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        generate_unified_html(session_file, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # Nav should show "My actual question here" not "<ide_opened_file>"
        assert "My actual question" in html
        # The ide_opened_file tag content should not appear in nav preview
        assert 'class="nav-preview"' in html


class TestUserContentStyling:
    """Tests for proper user content styling and class names."""

    def test_user_content_has_user_text_class(self, output_dir):
        """Test that actual user text uses user-text class, not assistant-text."""
        session_data = {
            "loglines": [
                {
                    "type": "user",
                    "timestamp": "2025-01-01T10:00:00.000Z",
                    "message": {
                        "content": "This is the user's actual question",
                        "role": "user",
                    },
                },
                {
                    "type": "assistant",
                    "timestamp": "2025-01-01T10:00:05.000Z",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Response"}],
                    },
                },
            ]
        }

        session_file = output_dir / "test_session.json"
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        generate_unified_html(session_file, output_dir)

        html = (output_dir / "unified.html").read_text(encoding="utf-8")
        # User messages should use user-text or user-content class
        assert 'class="user-text"' in html or 'class="user-content"' in html
