"""Tests for subagent transcript discovery and linking."""

from pathlib import Path

from claude_code_transcripts import link_subagents

FIXTURE = Path(__file__).parent / "sample_subagents" / "parent-session.jsonl"


def test_link_subagents_maps_task_calls_to_transcripts():
    links = link_subagents(FIXTURE)

    # Keyed by the parent Task tool_use id
    assert set(links) == {"toolu_A", "toolu_B"}

    a = links["toolu_A"]
    assert a["agent_id"] == "aaa111"
    assert a["description"] == "Explore repo A"
    assert a["metadata"]["totalToolUseCount"] == 7
    # The nested transcript is parsed into loglines
    assert len(a["loglines"]) == 4
    assert a["loglines"][0]["type"] == "user"

    b = links["toolu_B"]
    assert b["agent_id"] == "bbb222"
    assert len(b["loglines"]) == 2


def test_link_subagents_no_subagents_dir(tmp_path):
    # A parent session with no subagents/ dir yields an empty mapping
    p = tmp_path / "lonely.jsonl"
    p.write_text(
        '{"type":"user","timestamp":"t","message":{"role":"user","content":"hi"}}\n'
    )
    assert link_subagents(p) == {}


def test_generate_html_embeds_subagents_inline(tmp_path):
    from claude_code_transcripts import generate_html

    out = tmp_path / "out"
    generate_html(str(FIXTURE), str(out), github_repo=None)
    html = (out / "page-001.html").read_text()

    # The subagent block is rendered as a collapsible details element
    assert 'class="subagent"' in html
    # Labelled by the Task description and agent metadata
    assert "Explore repo A" in html
    assert "Explore repo B" in html
    # The nested subagent transcript content appears inline
    assert "Looking at repo A files." in html
    # Tool-use count from metadata is surfaced
    assert "7" in html
    # The block announces itself as a transcript with a message count
    assert "Subagent transcript" in html
    assert "4 messages" in html  # agent aaa111 has 4 loglines


def test_index_is_single_scrolling_page_with_nav(tmp_path):
    """index.html holds the full transcript inline with a sticky scroll-nav."""
    from claude_code_transcripts import generate_html

    out = tmp_path / "out"
    generate_html(str(FIXTURE), str(out), github_repo=None)
    index = (out / "index.html").read_text()

    # The full transcript lives on the index page itself (single page)
    assert "Both repos explored. Done." in index
    # Subagents are embedded inline on the single page too
    assert 'class="subagent"' in index
    # A sticky side nav lists the prompts and links to in-page anchors
    assert 'class="transcript-nav"' in index
    assert 'href="#msg-' in index
    # Scroll-spy wiring is present
    assert "IntersectionObserver" in index


def test_agent_graph_renders_spawn_flow(tmp_path):
    """A graph at the top links each spawned subagent to its inline block."""
    from claude_code_transcripts import generate_html

    out = tmp_path / "out"
    generate_html(str(FIXTURE), str(out), github_repo=None)
    index = (out / "index.html").read_text()

    assert 'class="agent-graph"' in index
    # Both subagents appear as nodes that jump to their inline transcript anchors
    assert 'href="#agent-aaa111"' in index
    assert 'href="#agent-bbb222"' in index
    # The graph is drawn as an SVG with curved (cubic-bezier) connector edges
    assert "<svg" in index
    assert 'class="graph-edge"' in index
    assert "<path" in index and " C " in index  # bezier curve command
