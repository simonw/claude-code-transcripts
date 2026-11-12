import json
import os
import re
from unittest.mock import Mock
from urllib.parse import quote

import pytest
import questionary
from click.testing import CliRunner

from claude_code_transcripts import cli


@pytest.fixture
def sources(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    roots = [tmp_path / name / "projects" for name in (".claude", ".claude-personal")]
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(roots[1].parent))
    for root in roots:
        project = root / "shared"
        project.mkdir(parents=True)
        for i in range(11):
            entry = {
                "type": "user",
                "timestamp": "2025-01-01T10:00:00Z",
                "message": {
                    "role": "user",
                    "content": f"Hello from {root.parent.name} session {i}",
                },
            }
            (project / f"{i}.jsonl").write_text(json.dumps(entry) + "\n")
    return roots


@pytest.mark.parametrize("args,limit", [(["local"], 10), (["--limit", "2"], 2)])
def test_grouped_picker(sources, args, limit, tmp_path, monkeypatch):
    def select(message, choices):
        offset = limit + 1
        assert len(choices) == 2 * offset
        for index, source in enumerate(sources):
            start = index * offset
            assert isinstance(choices[start], questionary.Separator)
            assert source.parent.name in choices[start].title
            assert all(
                c.value.parent.parent == source
                for c in choices[start + 1 : start + offset]
            )
        return Mock(ask=lambda: choices[offset + 1].value)

    monkeypatch.setattr(questionary, "select", select)
    output = tmp_path / "result"
    result = CliRunner().invoke(
        cli, [*args, "-s", sources[0], "--source", sources[1], "-o", output]
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert (
        "Hello from .claude-personal session" in (output / "page-001.html").read_text()
    )


def test_archive_links(sources, tmp_path):
    out = tmp_path / "archive"
    result = CliRunner().invoke(
        cli, ["all", "-s", sources[0], "-s", sources[1], "-o", out]
    )
    assert result.exit_code == 0, result.output
    links = re.findall(r'<a href="([^"]+)"', (out / "index.html").read_text())
    assert len(set(links)) == 2
    for root, link in zip(sources, links):
        source_index = out / link
        assert 'href="shared/index.html"' in source_index.read_text()
        project = source_index.parent / "shared"
        assert 'href="0/index.html"' in (project / "index.html").read_text()
        assert (
            f"Hello from {root.parent.name} session 0"
            in (project / "0/index.html").read_text()
        )


@pytest.mark.parametrize("command", ["all", "local"])
@pytest.mark.parametrize("mode,expected", [("env", 1), ("explicit", 0), ("home", 0)])
def test_single_source(sources, command, mode, expected, tmp_path, monkeypatch):
    if mode == "home":
        monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    monkeypatch.setattr(
        questionary,
        "select",
        lambda message, choices: Mock(ask=lambda: choices[0].value),
    )
    out = tmp_path / "archive"
    args = ["-s", sources[0]] if mode == "explicit" else []
    result = CliRunner().invoke(cli, [command, *args, "-o", out])
    assert result.exit_code == 0, result.output
    index = out / "index.html"
    if command == "all":
        assert 'href="shared/index.html"' in index.read_text()
        index = out / "shared/0/index.html"
    assert f"Hello from {sources[expected].parent.name} session" in index.read_text()


def test_archive_distinguishes_same_directory_names(sources, tmp_path):
    nested = tmp_path / "work" / ".claude" / "projects"
    nested.parent.mkdir(parents=True)
    sources[1].rename(nested)
    out = tmp_path / "archive"
    result = CliRunner().invoke(cli, ["all", "-s", sources[0], "-s", nested, "-o", out])
    assert result.exit_code == 0, result.output
    labels = re.findall(
        r'<div class="index-item-header">\s*<span class="index-item-number">([^<]+)</span>',
        (out / "index.html").read_text(),
    )
    assert len(set(labels)) == 2


@pytest.mark.parametrize("command", ["all", "local"])
@pytest.mark.parametrize("invalid", ["missing", "file"])
def test_invalid_second_source_aborts_before_output(
    command, invalid, sources, tmp_path
):
    bad = tmp_path / invalid
    if invalid == "file":
        bad.touch()
    out = tmp_path / "output"
    result = CliRunner().invoke(cli, [command, "-s", sources[0], "-s", bad, "-o", out])
    assert result.exit_code == 2
    assert str(bad) in result.output
    assert not out.exists()


@pytest.mark.parametrize("command", ["all", "local"])
def test_repeated_source_and_symlink_are_one_source(
    command, sources, tmp_path, monkeypatch
):
    root = sources[0]
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    out = tmp_path / "output"

    def select(message, choices):
        assert len(choices) == 10
        assert all(c.value.parent.parent == root for c in choices)
        return Mock(ask=lambda: None)

    monkeypatch.setattr(questionary, "select", select)
    result = CliRunner().invoke(
        cli, [command, "-s", root, "-s", root, "-s", alias, "-o", out]
    )
    assert result.exit_code == 0, (result.output, result.exception)
    if command == "all":
        assert "1 projects, 11 sessions" in result.output
        assert 'href="shared/index.html"' in (out / "index.html").read_text()
    else:
        assert "No session selected" in result.output
        assert not out.exists()


@pytest.mark.parametrize("command", ["all", "local"])
def test_empty_sources(command, tmp_path):
    roots = [tmp_path / "empty1", tmp_path / "empty2"]
    for root in roots:
        root.mkdir()
    out = tmp_path / "output"
    result = CliRunner().invoke(
        cli, [command, "-s", roots[0], "-s", roots[1], "-o", out]
    )
    assert result.exit_code == 0, result.output
    assert "sessions found" in result.output
    assert not out.exists()


def test_picker_skips_empty_source_and_filters_before_limit(
    sources, tmp_path, monkeypatch
):
    empty = tmp_path / "empty"
    empty.mkdir()
    for root in sources:
        project = root / "shared"
        newest = project / "5.jsonl"
        for file in project.iterdir():
            os.utime(file, (1, 1))
        os.utime(newest, (2, 2))
        (project / "agent-new.jsonl").write_bytes(newest.read_bytes())
        (project / "empty.jsonl").touch()

    def select(message, choices):
        assert [c.title for c in choices if isinstance(c, questionary.Separator)] == [
            str(root) for root in sources
        ]
        assert [
            c.value for c in choices if not isinstance(c, questionary.Separator)
        ] == [root / "shared/5.jsonl" for root in sources]
        return Mock(ask=lambda: None)

    monkeypatch.setattr(questionary, "select", select)
    result = CliRunner().invoke(
        cli,
        [
            "-s",
            str(empty),
            "-s",
            str(sources[0]),
            "-s",
            str(sources[1]),
            "--limit",
            "1",
        ],
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert "No session selected" in result.output


@pytest.mark.parametrize("limit,code", [("0", 0), ("-1", 2)])
def test_picker_limit_boundary(sources, tmp_path, limit, code):
    out = tmp_path / "output"
    result = CliRunner().invoke(
        cli, ["local", "-s", sources[0], "-s", sources[1], "--limit", limit, "-o", out]
    )
    assert result.exit_code == code, result.output
    assert ("No local sessions found" if code == 0 else "--limit") in result.output
    assert not out.exists()


@pytest.mark.parametrize("quiet", [False, True])
def test_multi_source_dry_run(sources, tmp_path, quiet, mock_webbrowser_open):
    out = tmp_path / "output"
    args = ["--quiet"] if quiet else []
    result = CliRunner().invoke(
        cli,
        [
            "all",
            "-s",
            sources[0],
            "-s",
            sources[1],
            "-o",
            out,
            "--open",
            "--dry-run",
            *args,
        ],
    )
    assert result.exit_code == 0, result.output
    if quiet:
        assert result.output == ""
    else:
        preview = result.output.split("Dry run - would convert:")[1]
        assert all(str(source) in preview for source in sources)
        assert preview.count("shared (11 sessions)") == 2
    assert not out.exists()
    assert not mock_webbrowser_open


def test_archive_stable_links_with_empty_source_and_reordered_args(
    sources, tmp_path, mock_webbrowser_open
):
    empty = tmp_path / "empty"
    empty.mkdir()
    out = tmp_path / "output"
    previous = []
    for roots in ([empty, sources[1]], [sources[1], empty]):
        result = CliRunner().invoke(
            cli, ["all", "-s", roots[0], "-s", roots[1], "-o", out, "--open"]
        )
        assert result.exit_code == 0, result.output
        links = re.findall(r'<a href="([^"]+)"', (out / "index.html").read_text())
        assert len(links) == 2
        for root, link in zip(roots, links):
            expected = (
                "0 projects · 0 sessions"
                if root == empty
                else "1 projects · 11 sessions"
            )
            assert expected in (out / link).read_text()
        if previous:
            assert links == previous[::-1]
        previous = links
    assert mock_webbrowser_open == [(out / "index.html").as_uri()] * 2


def test_archive_links_escape_reserved_characters(sources, tmp_path):
    project_name = "shared #1"
    session_name = "part%20two"
    for root in sources:
        project = root / project_name
        (root / "shared").rename(project)
        (project / "0.jsonl").rename(project / f"{session_name}.jsonl")
    out = tmp_path / "archive"
    result = CliRunner().invoke(
        cli, ["all", "-s", sources[0], "-s", sources[1], "-o", out]
    )
    assert result.exit_code == 0, result.output
    for link in re.findall(r'<a href="([^"]+)"', (out / "index.html").read_text()):
        source_index = out / link
        assert f'href="{quote(project_name)}/index.html"' in source_index.read_text()
        project = source_index.parent / project_name
        assert (
            f'href="{quote(session_name)}/index.html"'
            in (project / "index.html").read_text()
        )
        assert (project / session_name / "index.html").is_file()


@pytest.mark.parametrize("include_agents", [False, True])
def test_archive_agent_filter_applies_to_each_source(sources, tmp_path, include_agents):
    for source in sources:
        project = source / "shared"
        (project / "agent-example.jsonl").write_bytes(
            (project / "0.jsonl").read_bytes()
        )
    out = tmp_path / "archive"
    args = ["--include-agents"] if include_agents else []
    result = CliRunner().invoke(
        cli, ["all", "-s", sources[0], "-s", sources[1], "-o", out, *args]
    )
    assert result.exit_code == 0, result.output
    links = re.findall(r'<a href="([^"]+)"', (out / "index.html").read_text())
    assert len(links) == 2
    for link in links:
        project = (out / link).parent / "shared"
        assert (project / "agent-example/index.html").is_file() == include_agents
        assert (
            'href="agent-example/index.html"' in (project / "index.html").read_text()
        ) == include_agents
