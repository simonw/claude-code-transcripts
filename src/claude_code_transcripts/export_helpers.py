"""Shared helpers for PDF, DOCX, and single-page HTML export.

All imports from the parent package are done inside function bodies
to avoid circular imports.
"""

import json


def extract_conversations(loglines):
    """Extract conversations from loglines.

    Groups loglines into conversations, where each conversation starts with
    a user prompt and includes all subsequent messages until the next user prompt.

    Returns a list of conversation dicts, each with keys:
    - user_text: str
    - timestamp: str
    - messages: list of (log_type, message_json, timestamp) tuples
    - is_continuation: bool
    """
    from . import extract_text_from_content

    conversations = []
    current_conv = None
    for entry in loglines:
        log_type = entry.get("type")
        timestamp = entry.get("timestamp", "")
        is_compact_summary = entry.get("isCompactSummary", False)
        message_data = entry.get("message", {})
        if not message_data:
            continue
        # Convert message dict to JSON string for compatibility with existing render functions
        message_json = json.dumps(message_data)
        is_user_prompt = False
        user_text = None
        if log_type == "user":
            content = message_data.get("content", "")
            text = extract_text_from_content(content)
            if text:
                is_user_prompt = True
                user_text = text
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


def load_conversations(source, github_repo=None):
    """Load and parse conversations from a session file or session data dict.

    Args:
        source: Path to session file, or dict with 'loglines' key
        github_repo: Optional GitHub repo for commit links. If None, auto-detected.

    Returns:
        (conversations, github_repo) tuple
    """
    from . import parse_session_file, detect_github_repo

    if isinstance(source, dict):
        loglines = source.get("loglines", [])
    else:
        data = parse_session_file(source)
        loglines = data.get("loglines", [])

    if github_repo is None:
        github_repo = detect_github_repo(loglines)

    conversations = extract_conversations(loglines)
    return conversations, github_repo


def count_prompts_and_messages(conversations):
    """Count prompts and messages across conversations.

    Returns:
        (prompt_count, message_count) tuple
    """
    prompt_count = sum(
        1
        for conv in conversations
        if not conv.get("is_continuation")
        and not conv["user_text"].startswith("Stop hook feedback:")
    )
    message_count = sum(len(conv["messages"]) for conv in conversations)
    return prompt_count, message_count


def generate_single_page_html(conversations):
    """Render all conversations into a single HTML string suitable for PDF.

    Returns a complete HTML document string with all content expanded
    and no JavaScript or pagination.
    """
    from . import render_message, get_template, CSS

    messages_html_parts = []
    for conv in conversations:
        is_first = True
        for log_type, message_json, timestamp in conv["messages"]:
            msg_html = render_message(log_type, message_json, timestamp)
            if msg_html:
                # For single-page, show continuation summaries expanded (no <details>)
                if is_first and conv.get("is_continuation"):
                    msg_html = f'<div class="continuation-expanded">{msg_html}</div>'
                messages_html_parts.append(msg_html)
            is_first = False

    prompt_count, message_count = count_prompts_and_messages(conversations)

    template = get_template("single_page.html")
    return template.render(
        css=CSS,
        prompt_count=prompt_count,
        message_count=message_count,
        messages_html="".join(messages_html_parts),
    )


def generate_pdf(source, output_path, github_repo=None):
    """Generate a PDF from a session file or session data dict.

    Args:
        source: Path to session file, or dict with 'loglines' key
        output_path: Path for the output PDF file
        github_repo: Optional GitHub repo for commit links
    """
    from .pdf_export import generate_pdf as _generate_pdf

    _generate_pdf(source, output_path, github_repo=github_repo)
