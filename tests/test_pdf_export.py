"""Tests for PDF export functionality."""

import json
import tempfile
from pathlib import Path

import pytest

from claude_code_transcripts import (
    extract_conversations,
    generate_single_page_html,
)

try:
    import reportlab

    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


@pytest.fixture
def output_dir():
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_loglines():
    return [
        {
            "type": "user",
            "timestamp": "2025-01-01T10:00:00.000Z",
            "message": {"role": "user", "content": "Hello, write a function"},
        },
        {
            "type": "assistant",
            "timestamp": "2025-01-01T10:00:05.000Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "Here is the function:\n```python\ndef hello():\n    print('hello')\n```",
                    }
                ],
            },
        },
        {
            "type": "user",
            "timestamp": "2025-01-01T10:01:00.000Z",
            "message": {"role": "user", "content": "Now add a parameter"},
        },
        {
            "type": "assistant",
            "timestamp": "2025-01-01T10:01:05.000Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "Updated:\n```python\ndef hello(name):\n    print(f'hello {name}')\n```",
                    }
                ],
            },
        },
    ]


@pytest.mark.skipif(
    not HAS_REPORTLAB,
    reason="reportlab not available",
)
class TestGeneratePdf:
    """Tests for PDF generation."""

    def test_generates_pdf_file_from_path(self, output_dir, sample_loglines):
        """Test that generate_pdf creates a PDF file from a session file."""
        from claude_code_transcripts import generate_pdf

        session_file = output_dir / "test_session.json"
        session_file.write_text(
            json.dumps({"loglines": sample_loglines}), encoding="utf-8"
        )

        pdf_path = output_dir / "output.pdf"
        generate_pdf(session_file, pdf_path)

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0
        # PDF files start with %PDF
        with open(pdf_path, "rb") as f:
            assert f.read(4) == b"%PDF"

    def test_generates_pdf_from_dict(self, output_dir, sample_loglines):
        """Test that generate_pdf accepts a dict with loglines."""
        from claude_code_transcripts import generate_pdf

        pdf_path = output_dir / "output.pdf"
        generate_pdf({"loglines": sample_loglines}, pdf_path)

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

    def test_creates_parent_directories(self, output_dir, sample_loglines):
        """Test that generate_pdf creates parent directories."""
        from claude_code_transcripts import generate_pdf

        pdf_path = output_dir / "subdir" / "nested" / "output.pdf"
        generate_pdf({"loglines": sample_loglines}, pdf_path)

        assert pdf_path.exists()

    def test_pdf_with_image_block(self, output_dir):
        """Test that generate_pdf handles image blocks without crashing."""
        from claude_code_transcripts import generate_pdf

        # Valid 2x2 red PNG
        red_pixel = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGP8zwACTGCSAQANHQEDgslx/wAAAABJRU5ErkJggg=="

        loglines = [
            {
                "type": "user",
                "timestamp": "2025-01-01T10:00:00.000Z",
                "message": {"role": "user", "content": "Show me an image"},
            },
            {
                "type": "assistant",
                "timestamp": "2025-01-01T10:00:05.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": red_pixel,
                            },
                        },
                        {"type": "text", "text": "Here is the image."},
                    ],
                },
            },
        ]

        pdf_path = output_dir / "output.pdf"
        generate_pdf({"loglines": loglines}, pdf_path)

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

    def test_pdf_cli_format_option(self, output_dir):
        """Test that --format pdf option works via CLI."""
        from click.testing import CliRunner
        from claude_code_transcripts import cli

        fixture_path = Path(__file__).parent / "sample_session.json"
        pdf_path = output_dir / "output.pdf"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["json", str(fixture_path), "-o", str(pdf_path), "--format", "pdf"],
        )

        assert result.exit_code == 0
        assert pdf_path.exists()
        assert "Output:" in result.output

    def test_pdf_with_thinking_block(self, output_dir):
        """Test that thinking blocks render in the PDF."""
        from claude_code_transcripts import generate_pdf

        loglines = [
            {
                "type": "user",
                "timestamp": "2025-01-01T10:00:00.000Z",
                "message": {"role": "user", "content": "Think about this"},
            },
            {
                "type": "assistant",
                "timestamp": "2025-01-01T10:00:05.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "Let me consider the options carefully...",
                        },
                        {"type": "text", "text": "Here is my answer."},
                    ],
                },
            },
        ]

        pdf_path = output_dir / "output.pdf"
        generate_pdf({"loglines": loglines}, pdf_path)

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

    def test_pdf_with_generic_tool(self, output_dir):
        """Test PDF generation with a non-Write/Edit/Bash tool."""
        from claude_code_transcripts import generate_pdf

        loglines = [
            {
                "type": "user",
                "timestamp": "2025-01-01T10:00:00.000Z",
                "message": {"role": "user", "content": "Search for something"},
            },
            {
                "type": "assistant",
                "timestamp": "2025-01-01T10:00:05.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Grep",
                            "id": "tool_1",
                            "input": {
                                "description": "Search for pattern",
                                "pattern": "def hello",
                                "path": "/src",
                            },
                        }
                    ],
                },
            },
        ]

        pdf_path = output_dir / "output.pdf"
        generate_pdf({"loglines": loglines}, pdf_path)

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

    def test_pdf_with_tool_result_in_assistant(self, output_dir):
        """Test PDF handles tool_result blocks in assistant content."""
        from claude_code_transcripts import generate_pdf

        loglines = [
            {
                "type": "user",
                "timestamp": "2025-01-01T10:00:00.000Z",
                "message": {"role": "user", "content": "Do something"},
            },
            {
                "type": "assistant",
                "timestamp": "2025-01-01T10:00:05.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_result",
                            "content": [
                                {"type": "text", "text": "Result output here"},
                            ],
                            "is_error": False,
                        }
                    ],
                },
            },
        ]

        pdf_path = output_dir / "output.pdf"
        generate_pdf({"loglines": loglines}, pdf_path)

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

    def test_pdf_with_commit_output(self, output_dir):
        """Test PDF renders commit hashes from tool results."""
        from claude_code_transcripts import generate_pdf

        loglines = [
            {
                "type": "user",
                "timestamp": "2025-01-01T10:00:00.000Z",
                "message": {"role": "user", "content": "Commit this"},
            },
            {
                "type": "assistant",
                "timestamp": "2025-01-01T10:00:05.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "id": "tool_1",
                            "input": {"command": "git commit -m 'test'"},
                        }
                    ],
                },
            },
            {
                "type": "user",
                "timestamp": "2025-01-01T10:00:10.000Z",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool_1",
                            "content": "[main abc1234] Add test feature\n 1 file changed",
                        }
                    ],
                },
            },
        ]

        pdf_path = output_dir / "output.pdf"
        generate_pdf({"loglines": loglines}, pdf_path)

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

    def test_pdf_with_error_tool_result(self, output_dir):
        """Test PDF renders error tool results with error styling."""
        from claude_code_transcripts import generate_pdf

        loglines = [
            {
                "type": "user",
                "timestamp": "2025-01-01T10:00:00.000Z",
                "message": {"role": "user", "content": "Run this"},
            },
            {
                "type": "assistant",
                "timestamp": "2025-01-01T10:00:05.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "id": "tool_1",
                            "input": {"command": "exit 1"},
                        }
                    ],
                },
            },
            {
                "type": "user",
                "timestamp": "2025-01-01T10:00:10.000Z",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool_1",
                            "content": "Error: command failed with exit code 1",
                            "is_error": True,
                        }
                    ],
                },
            },
        ]

        pdf_path = output_dir / "output.pdf"
        generate_pdf({"loglines": loglines}, pdf_path)

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0

    def test_pdf_with_oversized_tool_result(self, output_dir):
        """Test PDF handles tool results with many lines without crashing."""
        from claude_code_transcripts import generate_pdf

        # Create a tool result with 100+ lines that would overflow a page
        long_output = "\n".join(f"line {i}: some output text" for i in range(120))
        loglines = [
            {
                "type": "user",
                "timestamp": "2025-01-01T10:00:00.000Z",
                "message": {"role": "user", "content": "List files"},
            },
            {
                "type": "assistant",
                "timestamp": "2025-01-01T10:00:05.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "id": "tool_1",
                            "input": {"command": "find . -type f"},
                        }
                    ],
                },
            },
            {
                "type": "user",
                "timestamp": "2025-01-01T10:00:10.000Z",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool_1",
                            "content": long_output,
                        }
                    ],
                },
            },
        ]

        pdf_path = output_dir / "output.pdf"
        generate_pdf({"loglines": loglines}, pdf_path)

        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0


class TestPdfSinglePage:
    """Tests for single-page HTML used by PDF (no reportlab needed)."""

    def test_pdf_single_continuous_document(self):
        """Test that the single page HTML has no pagination."""
        loglines = [
            {
                "type": "user",
                "timestamp": "2025-01-01T10:00:00.000Z",
                "message": {"role": "user", "content": "Hello, write a function"},
            },
            {
                "type": "assistant",
                "timestamp": "2025-01-01T10:00:05.000Z",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Here is the function"}],
                },
            },
            {
                "type": "user",
                "timestamp": "2025-01-01T10:01:00.000Z",
                "message": {"role": "user", "content": "Now add a parameter"},
            },
        ]
        convs = extract_conversations(loglines)
        html = generate_single_page_html(convs)

        assert "Hello, write a function" in html
        assert "Now add a parameter" in html
        assert "page-001" not in html
        assert "page-002" not in html


class TestPdfGistIncompatibility:
    """Test that --gist and --format pdf are incompatible."""

    def test_gist_with_pdf_raises_error(self, output_dir):
        """Test that --gist with --format pdf raises an error."""
        from click.testing import CliRunner
        from claude_code_transcripts import cli

        fixture_path = Path(__file__).parent / "sample_session.json"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "json",
                str(fixture_path),
                "-o",
                str(output_dir / "out.pdf"),
                "--format",
                "pdf",
                "--gist",
            ],
        )

        assert result.exit_code != 0
        assert "gist" in result.output.lower() or "HTML" in result.output
