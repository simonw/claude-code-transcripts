# Development Guide

This guide covers everything needed to contribute to claude-code-transcripts.

## Quick Start

```bash
# Clone and setup
git clone https://github.com/simonw/claude-code-transcripts.git
cd claude-code-transcripts

# Install uv if not already installed
# See: https://docs.astral.sh/uv/

# Install dependencies
uv sync --group dev

# Run tests
uv run pytest

# Run the development version
uv run claude-code-transcripts --help
```

## Project Structure

```
claude-code-transcripts/
├── src/claude_code_transcripts/
│   ├── __init__.py          # Main implementation
│   └── templates/           # Jinja2 templates
│       ├── macros.html      # Reusable macros
│       ├── page.html        # Page template
│       ├── index.html       # Index template
│       ├── base.html        # Base template
│       └── search.js        # Client-side search
├── tests/
│   ├── test_generate_html.py  # Main test suite
│   ├── test_all.py            # Batch command tests
│   ├── sample_session.json    # Test fixture (JSON)
│   ├── sample_session.jsonl   # Test fixture (JSONL)
│   └── __snapshots__/         # Snapshot test outputs
├── TASKS.md                   # Implementation roadmap
├── AGENTS.md                  # This file
└── pyproject.toml             # Package configuration
```

## Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_generate_html.py

# Run specific test class
uv run pytest tests/test_generate_html.py::TestRenderContentBlock

# Run specific test
uv run pytest tests/test_generate_html.py::TestRenderContentBlock::test_text_block -v

# Run with verbose output
uv run pytest -v

# Run with stdout capture disabled (for debugging)
uv run pytest -s
```

## Code Formatting

Format code with Black before committing:

```bash
uv run black .
```

Check formatting without making changes:

```bash
uv run black . --check
```

## Test-Driven Development (TDD)

Always practice TDD: write a failing test, watch it fail, then make it pass.

1. Write a failing test for your change
2. Run tests to confirm it fails: `uv run pytest`
3. Implement the feature to make the test pass
4. Format your code: `uv run black .`
5. Run all tests to ensure nothing broke
6. Commit with a descriptive message

## Snapshot Testing

This project uses `syrupy` for snapshot testing. Snapshots are stored in `tests/__snapshots__/`.

Update snapshots when intentionally changing output:

```bash
uv run pytest --snapshot-update
```

## Making Changes

### Commit Guidelines

Commit early and often. Each commit should bundle:
- The test
- The implementation
- Documentation changes (if applicable)

Example commit message:
```
Add support for filtering sessions by date

- Add --since and --until flags to local command
- Filter sessions by modification time
- Add tests for date filtering
```

### Before Submitting a PR

1. All tests pass: `uv run pytest`
2. Code is formatted: `uv run black .`
3. Documentation updated if adding user-facing features
4. TASKS.md updated if completing a tracked task

## Key Files Reference

| File | Purpose |
|------|---------|
| `src/claude_code_transcripts/__init__.py` | Main implementation (~1300 lines) |
| `src/claude_code_transcripts/templates/macros.html` | Jinja2 macros for rendering |
| `tests/test_generate_html.py` | Main test suite |
| `tests/sample_session.json` | Test fixture data |
| `TASKS.md` | Implementation roadmap and status |

## Debugging Tips

```bash
# See full assertion output
uv run pytest -vv

# Stop on first failure
uv run pytest -x

# Run only failed tests from last run
uv run pytest --lf

# Run tests matching a pattern
uv run pytest -k "test_ansi"
```

## Architecture Notes

- CSS and JavaScript are embedded as string constants in `__init__.py`
- Templates use Jinja2 with autoescape enabled
- The `_macros` module exposes macros from `macros.html`
- Tool rendering follows the pattern: Python function → Jinja2 macro → HTML
