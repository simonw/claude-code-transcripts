"""Jinja2 template environment shared by renderer and generator."""

from jinja2 import Environment, PackageLoader

_jinja_env = Environment(
    loader=PackageLoader("claude_code_transcripts.html_generation", "templates"),
    autoescape=True,
)

_macros_template = _jinja_env.get_template("macros.html")
_macros = _macros_template.module


def _get_template(name):
    """Get a Jinja2 template by name."""
    return _jinja_env.get_template(name)
