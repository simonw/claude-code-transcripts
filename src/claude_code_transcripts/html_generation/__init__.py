"""Public API for the html_generation package."""

from claude_code_transcripts.html_generation.generator import (
    GIST_PREVIEW_JS,
    Project,
    Session,
    create_gist,
    generate_batch_html,
    generate_html,
    inject_gist_preview_js,
)

__all__ = [
    "Session",
    "Project",
    "GIST_PREVIEW_JS",
    "generate_html",
    "generate_batch_html",
    "inject_gist_preview_js",
    "create_gist",
]
