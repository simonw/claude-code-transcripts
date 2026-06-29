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
