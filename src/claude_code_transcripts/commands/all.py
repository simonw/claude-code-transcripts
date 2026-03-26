import webbrowser
from datetime import datetime
from pathlib import Path

import click

from claude_code_transcripts.cli import cli

from claude_code_transcripts.html_generation import generate_batch_html
from claude_code_transcripts.commands import (
    build_project,
    collect_raw_projects,
    copy_jsonl_files,
    output_options,
    source_option,
)


@cli.command("all")
@output_options
@source_option
@click.option(
    "--include-agents",
    is_flag=True,
    help="Include agent-* session files (excluded by default).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be converted without creating files.",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Suppress all output except errors.",
)
def all_cmd(output, include_json, open_browser, source, include_agents, dry_run, quiet):
    """Convert all local Claude Code sessions to a browsable HTML archive.

    Creates a directory structure with:
    - Master index listing all projects
    - Per-project pages listing sessions
    - Individual session transcripts
    """
    if not quiet and source != "cowork":
        code_folder = (
            Path.home() / ".claude" / "projects"
            if source in (None, "code")
            else Path(source)
        )
        click.echo(f"Scanning {code_folder}...")

    raw_projects = collect_raw_projects(source, include_agents=include_agents)

    if not raw_projects:
        if not quiet:
            click.echo("No sessions found.")
        return

    total_sessions = sum(len(p["sessions"]) for p in raw_projects)

    if not quiet:
        click.echo(f"Found {len(raw_projects)} projects with {total_sessions} sessions")

    if dry_run:
        if not quiet:
            click.echo("\nDry run - would convert:")
            for project in raw_projects:
                click.echo(
                    f"\n  {project['name']} ({len(project['sessions'])} sessions)"
                )
                for session in project["sessions"][:3]:
                    mod_time = datetime.fromtimestamp(session["mtime"])
                    click.echo(
                        f"    - {session['path'].stem} ({mod_time.strftime('%Y-%m-%d')})"
                    )
                if len(project["sessions"]) > 3:
                    click.echo(f"    ... and {len(project['sessions']) - 3} more")
        return

    output = Path(output) if output else Path("./claude-archive")

    if not quiet:
        click.echo(f"\nParsing sessions...")

    projects = [build_project(raw, output) for raw in raw_projects]

    if not quiet:
        click.echo(f"Generating archive in {output}...")

    def on_progress(project_name, session_name, current, total):
        if not quiet and current % 10 == 0:
            click.echo(f"  Processed {current}/{total} sessions...")

    stats = generate_batch_html(
        projects,
        output,
        progress_callback=on_progress,
    )

    if include_json:
        for raw_project in raw_projects:
            copy_jsonl_files(raw_project, output)

    if stats["failed_sessions"]:
        click.echo(f"\nWarning: {len(stats['failed_sessions'])} session(s) failed:")
        for failure in stats["failed_sessions"]:
            click.echo(
                f"  {failure['project']}/{failure['session']}: {failure['error']}"
            )

    if not quiet:
        click.echo(
            f"\nGenerated archive with {stats['total_projects']} projects, "
            f"{stats['total_sessions']} sessions"
        )
        click.echo(f"Output: {output.resolve()}")

    if open_browser:
        index_url = (output / "index.html").resolve().as_uri()
        webbrowser.open(index_url)
