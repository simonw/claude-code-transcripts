"""Generate complete multi-page HTML transcript files from Claude Code session data.

This module operates at the file level — each function reads session data and
writes one or more HTML files to disk. It orchestrates pagination, index
generation, and batch processing. It delegates all per-block rendering to the
renderer module.
"""

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import click

_GITHUB_REPO_PATTERN = re.compile(
    r"github\.com/([a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)/pull/new/"
)
from claude_code_transcripts.html_generation.renderer import (
    _analyze_conversation,
    _format_tool_stats,
    _make_msg_id,
    _render_markdown_text,
    _render_message,
)
from claude_code_transcripts.html_generation.templates import _get_template, _macros

_static = Path(__file__).parent / "static"
_CSS = (_static / "style.css").read_text(encoding="utf-8")
_JS = (_static / "script.js").read_text(encoding="utf-8")
GIST_PREVIEW_JS = (_static / "gist_preview.js").read_text(encoding="utf-8")

_PROMPTS_PER_PAGE = 5


@dataclass
class Session:
    name: str
    session_dir: Path
    loglines: list = field(default_factory=list)
    size_kb: float = 0.0
    transcript_label: str = "Claude Code"


@dataclass
class Project:
    name: str
    project_dir: Path
    sessions: list = field(default_factory=list)  # list[Session]


def _generate_pagination_html(current_page, total_pages):
    return _macros.pagination(current_page, total_pages)


def _generate_index_pagination_html(total_pages):
    """Generate pagination for index page where Index is current (first page)."""
    return _macros.index_pagination(total_pages)


def _detect_github_repo(loglines):
    """Detect GitHub repo from git push output in tool results."""
    for entry in loglines:
        message = entry.get("message", {})
        content = message.get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result":
                result_content = block.get("content", "")
                if isinstance(result_content, str):
                    match = _GITHUB_REPO_PATTERN.search(result_content)
                    if match:
                        return match.group(1)
    return None


def _resolve_github_repo(loglines, github_repo, warn=True):
    """Auto-detect github_repo from loglines if not provided."""
    if github_repo is None:
        github_repo = _detect_github_repo(loglines)
        if github_repo:
            click.echo(f"Auto-detected GitHub repo: {github_repo}")
        elif warn:
            click.echo(
                "Warning: Could not auto-detect GitHub repo. Commit links will be disabled."
            )
    return github_repo


def _build_conversations(loglines):
    """Build a list of conversation dicts from loglines."""
    conversations = []
    current_conv = None
    for entry in loglines:
        log_type = entry.get("type")
        timestamp = entry.get("timestamp", "")
        is_compact_summary = entry.get("isCompactSummary", False)
        message_data = entry.get("message", {})
        if not message_data:
            continue
        message_json = json.dumps(message_data)
        is_user_prompt = False
        user_text = None
        if log_type == "user":
            content = message_data.get("content", "")
            if isinstance(content, str):
                user_text = content.strip()
            elif isinstance(content, list):
                texts = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                user_text = " ".join(t for t in texts if t).strip()
            if user_text:
                is_user_prompt = True
        if is_user_prompt:
            if current_conv:
                conversations.append(current_conv)
            current_conv = {
                "user_text": user_text,
                "timestamp": timestamp,
                "messages": [(log_type, message_json, timestamp)],
                "is_continuation": bool(is_compact_summary),
            }
        elif current_conv:
            current_conv["messages"].append((log_type, message_json, timestamp))
    if current_conv:
        conversations.append(current_conv)
    return conversations


def _render_sessions(loglines, output_dir, github_repo, transcript_label):
    """Core HTML generation logic shared by generate_html and generate_html_from_session_data."""
    output_dir = Path(output_dir)
    conversations = _build_conversations(loglines)

    total_convs = len(conversations)
    total_pages = (total_convs + _PROMPTS_PER_PAGE - 1) // _PROMPTS_PER_PAGE

    for page_num in range(1, total_pages + 1):
        start_idx = (page_num - 1) * _PROMPTS_PER_PAGE
        end_idx = min(start_idx + _PROMPTS_PER_PAGE, total_convs)
        page_convs = conversations[start_idx:end_idx]
        messages_html = []
        for conv in page_convs:
            is_first = True
            for log_type, message_json, timestamp in conv["messages"]:
                msg_html = _render_message(
                    log_type, message_json, timestamp, github_repo
                )
                if msg_html:
                    if is_first and conv.get("is_continuation"):
                        msg_html = f'<details class="continuation"><summary>Session continuation summary</summary>{msg_html}</details>'
                    messages_html.append(msg_html)
                is_first = False
        pagination_html = _generate_pagination_html(page_num, total_pages)
        page_template = _get_template("page.html")
        page_content = page_template.render(
            css=_CSS,
            js=_JS,
            page_num=page_num,
            total_pages=total_pages,
            pagination_html=pagination_html,
            messages_html="".join(messages_html),
            transcript_label=transcript_label,
        )
        (output_dir / f"page-{page_num:03d}.html").write_text(
            page_content, encoding="utf-8"
        )
        click.echo(f"Generated page-{page_num:03d}.html")

    # Collect overall stats and commits for timeline
    total_tool_counts = {}
    total_messages = 0
    all_commits = []
    for i, conv in enumerate(conversations):
        total_messages += len(conv["messages"])
        stats = _analyze_conversation(conv["messages"])
        for tool, count in stats["tool_counts"].items():
            total_tool_counts[tool] = total_tool_counts.get(tool, 0) + count
        page_num = (i // _PROMPTS_PER_PAGE) + 1
        for commit_hash, commit_msg, commit_ts in stats["commits"]:
            all_commits.append((commit_ts, commit_hash, commit_msg, page_num, i))
    total_tool_calls = sum(total_tool_counts.values())
    total_commits = len(all_commits)

    # Build timeline: prompts and commits merged by timestamp
    timeline_items = []

    prompt_num = 0
    for i, conv in enumerate(conversations):
        if conv.get("is_continuation"):
            continue
        if conv["user_text"].startswith("Stop hook feedback:"):
            continue
        prompt_num += 1
        page_num = (i // _PROMPTS_PER_PAGE) + 1
        msg_id = _make_msg_id(conv["timestamp"])
        link = f"page-{page_num:03d}.html#{msg_id}"
        rendered_content = _render_markdown_text(conv["user_text"])

        # Include messages from subsequent continuation conversations
        all_messages = list(conv["messages"])
        for j in range(i + 1, len(conversations)):
            if not conversations[j].get("is_continuation"):
                break
            all_messages.extend(conversations[j]["messages"])

        stats = _analyze_conversation(all_messages)
        tool_stats_str = _format_tool_stats(stats["tool_counts"])

        long_texts_html = ""
        for lt in stats["long_texts"]:
            rendered_lt = _render_markdown_text(lt)
            long_texts_html += _macros.index_long_text(rendered_lt)

        stats_html = _macros.index_stats(tool_stats_str, long_texts_html)

        item_html = _macros.index_item(
            prompt_num, link, conv["timestamp"], rendered_content, stats_html
        )
        timeline_items.append((conv["timestamp"], "prompt", item_html))

    for commit_ts, commit_hash, commit_msg, page_num, conv_idx in all_commits:
        item_html = _macros.index_commit(
            commit_hash, commit_msg, commit_ts, github_repo
        )
        timeline_items.append((commit_ts, "commit", item_html))

    timeline_items.sort(key=lambda x: x[0])
    index_items = [item[2] for item in timeline_items]

    index_pagination = _generate_index_pagination_html(total_pages)
    index_template = _get_template("index.html")
    index_content = index_template.render(
        css=_CSS,
        js=_JS,
        pagination_html=index_pagination,
        prompt_num=prompt_num,
        total_messages=total_messages,
        total_tool_calls=total_tool_calls,
        total_commits=total_commits,
        total_pages=total_pages,
        index_items_html="".join(index_items),
        transcript_label=transcript_label,
    )
    index_path = output_dir / "index.html"
    index_path.write_text(index_content, encoding="utf-8")
    click.echo(
        f"Generated {index_path.resolve()} ({total_convs} prompts, {total_pages} pages)"
    )


def generate_html(
    loglines, output_dir, github_repo=None, transcript_label="Claude Code"
):
    """Generate HTML from a list of loglines.

    github_repo may be None; it will be auto-detected from loglines if possible.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)

    github_repo = _resolve_github_repo(loglines, github_repo)
    _render_sessions(loglines, output_dir, github_repo, transcript_label)


def inject_gist_preview_js(output_dir):
    """Inject gist preview JavaScript into all HTML files in the output directory."""
    output_dir = Path(output_dir)
    for html_file in output_dir.glob("*.html"):
        content = html_file.read_text(encoding="utf-8")
        if "</body>" in content:
            content = content.replace(
                "</body>", f"<script>{GIST_PREVIEW_JS}</script>\n</body>"
            )
            html_file.write_text(content, encoding="utf-8")


def create_gist(output_dir, public=False):
    """Create a GitHub gist from the HTML files in output_dir.

    Returns the gist ID on success, or raises click.ClickException on failure.
    """
    output_dir = Path(output_dir)
    html_files = list(output_dir.glob("*.html"))
    if not html_files:
        raise click.ClickException("No HTML files found to upload to gist.")

    cmd = ["gh", "gist", "create"]
    cmd.extend(str(f) for f in sorted(html_files))
    if public:
        cmd.append("--public")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        gist_url = result.stdout.strip()
        gist_id = gist_url.rstrip("/").split("/")[-1]
        return gist_id, gist_url
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        raise click.ClickException(f"Failed to create gist: {error_msg}")
    except FileNotFoundError:
        raise click.ClickException(
            "gh CLI not found. Install it from https://cli.github.com/ and run 'gh auth login'."
        )


def generate_batch_html(projects, output_dir, progress_callback=None):
    """Generate HTML archive from a pre-built list of Project objects.

    Creates:
    - Master index.html listing all projects
    - Per-project directories with index.html listing sessions
    - Per-session directories with transcript pages

    Returns statistics dict with total_projects, total_sessions, failed_sessions, output_dir.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total_session_count = sum(len(p.sessions) for p in projects)
    processed_count = 0
    successful_sessions = 0
    failed_sessions = []

    for project in projects:
        project.project_dir.mkdir(exist_ok=True)

        for session in project.sessions:
            try:
                generate_html(
                    session.loglines,
                    session.session_dir,
                    transcript_label=session.transcript_label,
                )
                successful_sessions += 1
            except Exception as e:
                failed_sessions.append(
                    {
                        "project": project.name,
                        "session": session.name,
                        "error": str(e),
                    }
                )

            processed_count += 1

            if progress_callback:
                progress_callback(
                    project.name, session.name, processed_count, total_session_count
                )

        _generate_project_index(project)

    _generate_master_index(projects, output_dir)

    return {
        "total_projects": len(projects),
        "total_sessions": successful_sessions,
        "failed_sessions": failed_sessions,
        "output_dir": output_dir,
    }


def _generate_project_index(project):
    """Generate index.html for a single project."""
    template = _get_template("project_index.html")

    sessions_data = []
    for session in project.sessions:
        # Derive date from first logline timestamp
        date = ""
        if session.loglines:
            ts = session.loglines[0].get("timestamp", "")
            if ts:
                date = ts[:16].replace("T", " ")

        # Derive summary from first user message
        summary = ""
        for entry in session.loglines:
            if entry.get("type") == "user":
                content = entry.get("message", {}).get("content", "")
                if isinstance(content, str):
                    summary = content.strip()
                elif isinstance(content, list):
                    texts = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    summary = " ".join(t for t in texts if t).strip()
                if summary:
                    break

        sessions_data.append(
            {
                "name": session.name,
                "summary": summary,
                "date": date,
                "size_kb": session.size_kb,
            }
        )

    html_content = template.render(
        project_name=project.name,
        sessions=sessions_data,
        session_count=len(sessions_data),
        css=_CSS,
        js=_JS,
    )

    (project.project_dir / "index.html").write_text(html_content, encoding="utf-8")


def _generate_master_index(projects, output_dir):
    """Generate master index.html listing all projects."""
    template = _get_template("master_index.html")

    projects_data = []
    total_sessions = 0

    for project in projects:
        session_count = len(project.sessions)
        total_sessions += session_count

        # Derive most recent date from first session's first logline
        recent_date = "N/A"
        if project.sessions and project.sessions[0].loglines:
            ts = project.sessions[0].loglines[0].get("timestamp", "")
            if ts:
                recent_date = ts[:10]

        projects_data.append(
            {
                "name": project.name,
                "session_count": session_count,
                "recent_date": recent_date,
            }
        )

    html_content = template.render(
        projects=projects_data,
        total_projects=len(projects),
        total_sessions=total_sessions,
        css=_CSS,
        js=_JS,
    )

    (output_dir / "index.html").write_text(html_content, encoding="utf-8")
