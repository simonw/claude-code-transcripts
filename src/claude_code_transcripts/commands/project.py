import webbrowser
from pathlib import Path

import click
import questionary

from claude_code_transcripts.cli import cli
from claude_code_transcripts.commands import (
    build_project,
    collect_raw_projects,
    copy_jsonl_files,
    output_options,
    source_option,
)
from claude_code_transcripts.html_generation import generate_batch_html


@cli.command("project")
@output_options
@source_option
def project_cmd(output, include_json, open_browser, source):
    """Select a project and convert all its sessions to a browsable HTML archive."""
    raw_projects = collect_raw_projects(source)

    if not raw_projects:
        click.echo("No projects found.")
        return

    choices = [
        questionary.Choice(
            title=f"{p['name']}  ({len(p['sessions'])} session{'s' if len(p['sessions']) != 1 else ''})",
            value=p,
        )
        for p in raw_projects
    ]

    selected = questionary.select("Select a project to convert:", choices=choices).ask()

    if selected is None:
        click.echo("No project selected.")
        return

    output = Path(output) if output else Path("./claude-archive")

    project = build_project(selected, output)

    click.echo(f"Generating archive in {output}...")
    stats = generate_batch_html([project], output)

    if include_json:
        copy_jsonl_files(selected, output)

    if stats["failed_sessions"]:
        click.echo(f"\nWarning: {len(stats['failed_sessions'])} session(s) failed:")
        for failure in stats["failed_sessions"]:
            click.echo(
                f"  {failure['project']}/{failure['session']}: {failure['error']}"
            )

    click.echo(
        f"Generated archive with {stats['total_sessions']} session(s) "
        f"from project '{selected['name']}'"
    )
    click.echo(f"Output: {output.resolve()}")

    if open_browser:
        index_url = (project.project_dir / "index.html").resolve().as_uri()
        webbrowser.open(index_url)
