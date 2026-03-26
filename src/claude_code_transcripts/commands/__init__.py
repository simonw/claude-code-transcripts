"""Shared Click option decorators and utilities for commands."""

import shutil
import tempfile
import webbrowser
from pathlib import Path

import click

from claude_code_transcripts.html_generation import (
    Project,
    Session,
    create_gist,
    inject_gist_preview_js,
)
from claude_code_transcripts.parser import parse_session_file
from claude_code_transcripts.sessions import find_all_sessions, find_cowork_sessions


def resolve_output(output, output_auto, gist, stem):
    """Resolve the output directory and whether to auto-open the browser.

    Args:
        output: Explicit output path string, or None.
        output_auto: Whether to auto-name the output dir using stem.
        gist: Whether the gist flag is set (suppresses auto_open).
        stem: Filename stem used for default naming.

    Returns:
        (output_path, auto_open) tuple.
    """
    auto_open = output is None and not gist and not output_auto
    if output_auto:
        parent_dir = Path(output) if output else Path(".")
        output = parent_dir / stem
    elif output is None:
        output = Path(tempfile.gettempdir()) / f"claude-session-{stem}"
    return Path(output), auto_open


def publish_gist(output):
    """Inject gist preview JS, upload to GitHub Gist, and print URLs."""
    inject_gist_preview_js(output)
    click.echo("Creating GitHub gist...")
    gist_id, gist_url = create_gist(output)
    preview_url = f"https://gisthost.github.io/?{gist_id}/index.html"
    click.echo(f"Gist: {gist_url}")
    click.echo(f"Preview: {preview_url}")


def open_in_browser(output, open_browser, auto_open):
    """Open output/index.html in the default browser if requested."""
    if open_browser or auto_open:
        index_url = (output / "index.html").resolve().as_uri()
        webbrowser.open(index_url)


def collect_raw_projects(source, include_agents=False):
    """Discover raw project dicts from the given source.

    Args:
        source: 'code', 'cowork', None (both), or a path string.
        include_agents: Whether to include agent-* session files.

    Returns:
        List of raw project dicts, each with 'name' and 'sessions'.
    """
    raw_projects = []

    if source != "cowork":
        code_folder = (
            Path.home() / ".claude" / "projects"
            if source in (None, "code")
            else Path(source)
        )
        if not code_folder.exists():
            raise click.ClickException(f"Source directory not found: {code_folder}")
        raw_projects = find_all_sessions(code_folder, include_agents=include_agents)

    if source in (None, "cowork"):
        raw_cowork = find_cowork_sessions()
        if raw_cowork:
            cowork_sessions = []
            for session in raw_cowork:
                jsonl_path = session["jsonl_path"]
                stat = jsonl_path.stat()
                cowork_sessions.append(
                    {
                        "path": jsonl_path,
                        "summary": session["title"],
                        "mtime": session["mtime"],
                        "size": stat.st_size,
                        "transcript_label": "Claude Cowork",
                    }
                )
            raw_projects.append({"name": "Cowork", "sessions": cowork_sessions})

    return raw_projects


def build_project(raw_project, output):
    """Build a Project object (with Sessions) from a raw project dict.

    Args:
        raw_project: Dict with 'name' and 'sessions' (each having 'path', 'size', etc.).
        output: Base output directory; project files go in output/name/.

    Returns:
        A Project instance ready for generate_batch_html.
    """
    project_dir = output / raw_project["name"]
    sessions = []
    for raw_session in raw_project["sessions"]:
        session_name = raw_session["path"].stem
        loglines = parse_session_file(raw_session["path"])
        sessions.append(
            Session(
                name=session_name,
                session_dir=project_dir / session_name,
                loglines=loglines,
                size_kb=raw_session["size"] / 1024,
                transcript_label=raw_session.get("transcript_label", "Claude Code"),
            )
        )
    return Project(name=raw_project["name"], project_dir=project_dir, sessions=sessions)


def copy_jsonl_files(raw_project, output):
    """Copy source JSONL files into each session's output directory.

    Args:
        raw_project: Dict with 'name' and 'sessions'.
        output: Base output directory matching what was passed to generate_batch_html.
    """
    project_dir = output / raw_project["name"]
    for raw_session in raw_project["sessions"]:
        session_name = raw_session["path"].stem
        session_dir = project_dir / session_name
        shutil.copy(raw_session["path"], session_dir / raw_session["path"].name)


def output_options(func):
    """Apply the common output-related options to a command.

    Adds: --output, --json, --open
    """
    func = click.option(
        "--open",
        "open_browser",
        is_flag=True,
        help="Open the generated index.html in your default browser (default if no -o specified).",
    )(func)
    func = click.option(
        "--json",
        "include_json",
        is_flag=True,
        help="Include the original session file in the output directory.",
    )(func)
    func = click.option(
        "-o",
        "--output",
        type=click.Path(),
        help="Output directory. If not specified, writes to temp dir and opens in browser.",
    )(func)
    return func


def source_option(func):
    """Apply the --source option to a command."""
    return click.option(
        "-s",
        "--source",
        help=(
            "Session source: 'code' (default Code path), 'cowork' (Cowork sessions), "
            "or a path to a Claude projects directory. "
            "Omit to include both Code and Cowork."
        ),
    )(func)


def limit_option(func):
    """Apply the --limit option to a command."""
    return click.option(
        "--limit",
        default=None,
        type=int,
        help="Maximum number of sessions to show.",
    )(func)


def interactive_options(func):
    """Apply options shared by interactive single-session commands.

    Adds: --output, --json, --open, --output-auto, --gist, --repo
    """
    func = output_options(func)
    func = click.option(
        "--repo",
        help="GitHub repo (owner/name) for commit links.",
    )(func)
    func = click.option(
        "--gist",
        is_flag=True,
        help="Upload to GitHub Gist and output a gisthost.github.io URL.",
    )(func)
    func = click.option(
        "-a",
        "--output-auto",
        is_flag=True,
        help="Auto-name output subdirectory based on session filename (uses -o as parent, or current dir).",
    )(func)
    return func


def local_options(func):
    """Apply the full option set for the local session picker command.

    Adds: --output, --json, --open, --output-auto, --gist, --repo, --limit
    """
    func = limit_option(func)
    func = interactive_options(func)
    return func
