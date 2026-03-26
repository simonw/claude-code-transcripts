"""CLI commands for claude-code-transcripts."""

import click
from click_default_group import DefaultGroup


@click.group(cls=DefaultGroup, default="local", default_if_no_args=True)
@click.version_option(None, "-v", "--version", package_name="claude-code-transcripts")
def cli():
    """Convert Claude Code session JSON to mobile-friendly HTML pages."""
    pass


import importlib
import pkgutil

import claude_code_transcripts.commands as _commands_pkg

for _mod in pkgutil.iter_modules(_commands_pkg.__path__, _commands_pkg.__name__ + "."):
    importlib.import_module(_mod.name)
