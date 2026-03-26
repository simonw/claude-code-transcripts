import click

from claude_code_transcripts.cli import cli
from claude_code_transcripts.commands import local_options


@cli.command("cowork")
@local_options
@click.pass_context
def cowork_cmd(ctx, output, output_auto, repo, gist, include_json, open_browser, limit):
    """Select and convert a local Claude Cowork session to HTML."""
    # @cli.command replaces local_cmd with a Click Command object, so it cannot be called
    # directly. ctx.invoke calls its underlying callback while correctly threading context.
    from claude_code_transcripts.commands.local import local_cmd

    ctx.invoke(
        local_cmd,
        output=output,
        output_auto=output_auto,
        repo=repo,
        gist=gist,
        include_json=include_json,
        open_browser=open_browser,
        limit=limit,
        source="cowork",
    )
