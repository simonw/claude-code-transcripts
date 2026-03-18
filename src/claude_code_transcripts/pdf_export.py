"""PDF export for Claude Code transcripts."""

import json
import re

import click

# A4=595pt - 2*54pt margins = 487pt; box padding 10+8+3pt border ≈ 466pt
# Courier 8pt ≈ 4.8pt/char → ~97 chars; use 95 for safety
_MAX_LINE_WIDTH = 95


def _wrap_long_lines(text):
    """Wrap long lines so Preformatted text stays within the page."""
    import textwrap

    out = []
    for line in text.split("\n"):
        if len(line) > _MAX_LINE_WIDTH:
            out.extend(
                textwrap.wrap(
                    line,
                    _MAX_LINE_WIDTH,
                    break_long_words=True,
                    break_on_hyphens=False,
                )
            )
        else:
            out.append(line)
    return "\n".join(out)


def generate_pdf(source, output_path, github_repo=None):
    """Generate a styled PDF from a Claude Code session.

    Args:
        source: Path to session file, or dict with 'loglines' key
        output_path: Path for the output PDF file
        github_repo: Optional GitHub repo string for commit links
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.colors import HexColor
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
        )
    except ImportError:
        raise click.ClickException(
            "PDF export requires reportlab. "
            "Install with: uv pip install 'claude-code-transcripts[pdf]'"
        )

    from .export_helpers import load_conversations, count_prompts_and_messages
    from . import extract_text_from_content, is_tool_result_message, COMMIT_PATTERN

    conversations, github_repo = load_conversations(source, github_repo)

    from pathlib import Path

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    # --- Styles ---

    def _escape(text):
        """Escape text for reportlab Paragraph XML."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    MAX_LINES = 55  # ~672pt frame / ~10pt per line, with padding margin

    def _truncate(text, max_len=3000):
        if len(text) > max_len:
            text = text[:max_len] + f"\n... ({len(text)} chars total)"
        text = _wrap_long_lines(text)
        lines = text.split("\n")
        if len(lines) > MAX_LINES:
            text = "\n".join(lines[:MAX_LINES]) + f"\n... ({len(lines)} lines total)"
        return text

    # Role header styles (allocated once, reused across messages)
    style_user_role = ParagraphStyle(
        "UserRole",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=HexColor("#E65100"),
        spaceBefore=12,
        spaceAfter=2,
    )
    style_user_text = ParagraphStyle(
        "UserText",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=HexColor("#333333"),
        backColor=HexColor("#FFF3E0"),
        borderPadding=8,
        spaceBefore=2,
        spaceAfter=4,
    )
    style_assistant_role = ParagraphStyle(
        "AssistantRole",
        fontName="Helvetica",
        fontSize=9,
        textColor=HexColor("#666666"),
        spaceBefore=6,
        spaceAfter=2,
    )
    style_assistant_text = ParagraphStyle(
        "AssistantText",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=HexColor("#333333"),
        spaceBefore=2,
        spaceAfter=4,
        leftIndent=10,
    )
    style_thinking = ParagraphStyle(
        "Thinking",
        fontName="Helvetica-Oblique",
        fontSize=9,
        leading=12,
        textColor=HexColor("#F57C00"),
        backColor=HexColor("#FFF8E1"),
        borderPadding=6,
        spaceBefore=2,
        spaceAfter=4,
    )
    style_tool = ParagraphStyle(
        "ToolUse",
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=HexColor("#7B1FA2"),
        backColor=HexColor("#F3E5F5"),
        borderPadding=6,
        spaceBefore=4,
        spaceAfter=4,
    )
    style_tool_result = ParagraphStyle(
        "ToolResult",
        fontName="Courier",
        fontSize=8,
        leading=10,
        textColor=HexColor("#333333"),
        backColor=HexColor("#D5ECD6"),
        borderPadding=6,
        spaceBefore=2,
        spaceAfter=4,
    )
    style_code = ParagraphStyle(
        "Code",
        fontName="Courier",
        fontSize=8,
        leading=10,
        textColor=HexColor("#E0E0E0"),
        backColor=HexColor("#1E1E1E"),
        borderPadding=6,
        spaceBefore=4,
        spaceAfter=4,
    )
    style_commit = ParagraphStyle(
        "Commit",
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=HexColor("#333333"),
        spaceBefore=2,
        spaceAfter=2,
    )
    style_tool_reply_role = ParagraphStyle(
        "ToolReplyRole",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=HexColor("#4CAF50"),
        spaceBefore=0,
        spaceAfter=2,
    )

    # --- Build story ---
    story = []

    # Title
    title_style = ParagraphStyle(
        "Title",
        fontName="Helvetica",
        fontSize=24,
        leading=30,
        textColor=HexColor("#333333"),
        spaceAfter=6,
    )
    story.append(Paragraph("Claude Code Transcript", title_style))

    prompt_count, message_count = count_prompts_and_messages(conversations)
    meta_style = ParagraphStyle(
        "Meta", fontName="Helvetica", fontSize=10, textColor=HexColor("#999999")
    )
    story.append(
        Paragraph(
            f"{prompt_count} prompts &middot; {message_count} messages", meta_style
        )
    )
    story.append(Spacer(1, 12))

    for conv in conversations:
        conv_elements = []
        for log_type, message_json, timestamp in conv["messages"]:
            message_data = json.loads(message_json)
            content = message_data.get("content", "")
            if not content:
                continue

            if log_type == "user":
                if is_tool_result_message(message_data):
                    # Build inner elements for the tool result box
                    inner = []
                    inner.append(
                        Paragraph(
                            f"<b>TOOL REPLY</b>  <font size=7 color='#757575'>{_escape(timestamp)}</font>",
                            style_tool_reply_role,
                        )
                    )
                    any_error = False
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        result_content = block.get("content", "")
                        is_error = block.get("is_error", False)
                        if is_error:
                            any_error = True
                        _add_tool_result(
                            inner,
                            result_content,
                            is_error,
                            github_repo,
                            style_tool_result,
                            style_commit,
                            _escape,
                            _truncate,
                            COMMIT_PATTERN,
                        )
                    bg = "#FFEBEE" if any_error else "#D5ECD6"
                    border = "#B71C1C" if any_error else "#4CAF50"
                    conv_elements.extend(_wrap_in_colored_box(inner, bg, border))
                else:
                    conv_elements.append(
                        Paragraph(
                            f"<b>USER</b>  <font size=7 color='#757575'>{_escape(timestamp)}</font>",
                            style_user_role,
                        )
                    )
                    text = extract_text_from_content(content)
                    if text:
                        conv_elements.append(Paragraph(_escape(text), style_user_text))

            elif log_type == "assistant":
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        block_type = block.get("type", "")

                        if block_type == "text":
                            text = block.get("text", "")
                            if text:
                                conv_elements.append(
                                    Paragraph(
                                        f"<b>ASSISTANT</b>  <font size=7 color='#757575'>{_escape(timestamp)}</font>",
                                        style_assistant_role,
                                    )
                                )
                                # Split into code blocks and text
                                _add_markdown_content(
                                    conv_elements,
                                    text,
                                    style_assistant_text,
                                    style_code,
                                    _escape,
                                )

                        elif block_type == "thinking":
                            text = block.get("thinking", "")
                            if text:
                                short = _truncate(text, 500)
                                conv_elements.append(
                                    Paragraph(
                                        f"<b><font color='#F57C00'>Thinking:</font></b> <i>{_escape(short)}</i>",
                                        style_thinking,
                                    )
                                )

                        elif block_type == "tool_use":
                            tool_name = block.get("name", "Unknown")
                            tool_input = block.get("input", {})
                            _add_tool_use(
                                conv_elements,
                                tool_name,
                                tool_input,
                                style_tool,
                                style_code,
                                _escape,
                                _truncate,
                            )

                        elif block_type == "image":
                            _add_image_block(conv_elements, block)

                        elif block_type == "tool_result":
                            result_content = block.get("content", "")
                            is_error = block.get("is_error", False)
                            inner = []
                            _add_tool_result(
                                inner,
                                result_content,
                                is_error,
                                github_repo,
                                style_tool_result,
                                style_commit,
                                _escape,
                                _truncate,
                                COMMIT_PATTERN,
                            )
                            if inner:
                                bg = "#FFEBEE" if is_error else "#D5ECD6"
                                border = "#B71C1C" if is_error else "#4CAF50"
                                conv_elements.extend(
                                    _wrap_in_colored_box(inner, bg, border)
                                )

        if conv_elements:
            story.extend(conv_elements)
            story.append(Spacer(1, 6))

    doc.build(story)


def _markdown_to_xml(text, escape_fn):
    """Convert basic markdown inline formatting to reportlab Paragraph XML.

    Handles: **bold**, *italic*, `code`, [text](url), # headers.
    Must be called on text that will go into a Paragraph (not Preformatted).
    """
    escaped = escape_fn(text)
    # Bold: **text** or __text__
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"__(.+?)__", r"<b>\1</b>", escaped)
    # Italic: *text* or _text_ (not inside words)
    escaped = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<i>\1</i>", escaped)
    escaped = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", escaped)
    # Inline code: `code`
    escaped = re.sub(
        r"`([^`]+)`",
        r"<font name='Courier' size=8 color='#C62828'>\1</font>",
        escaped,
    )
    # Links: [text](url)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r"<a href='\2' color='#1976D2'><u>\1</u></a>",
        escaped,
    )
    # Headers: # text → bold larger text
    escaped = re.sub(
        r"^(#{1,3})\s+(.+)$",
        lambda m: f"<b><font size={14 - len(m.group(1))}>{m.group(2)}</font></b>",
        escaped,
        flags=re.MULTILINE,
    )
    return escaped


def _add_markdown_content(elements, text, text_style, code_style, escape_fn):
    """Add text with code blocks separated out, rendering markdown."""
    from reportlab.platypus import Paragraph, Preformatted

    lines = text.split("\n")
    current_text = []
    in_code = False
    code_lines = []

    def flush_text():
        if current_text:
            joined = "\n".join(current_text)
            if joined.strip():
                xml = _markdown_to_xml(joined, escape_fn)
                elements.append(Paragraph(xml, text_style))
            current_text.clear()

    for line in lines:
        if line.startswith("```"):
            if in_code:
                in_code = False
                flush_text()
                code_text = _wrap_long_lines("\n".join(code_lines))
                if code_text.strip():
                    elements.append(Preformatted(code_text, code_style))
                code_lines.clear()
            else:
                in_code = True
                flush_text()
        elif in_code:
            code_lines.append(line)
        else:
            current_text.append(line)

    # Flush remaining
    if in_code and code_lines:
        elements.append(
            Preformatted(_wrap_long_lines("\n".join(code_lines)), code_style)
        )
    flush_text()


def _wrap_in_colored_box(inner_elements, bg_color, border_color=None):
    """Wrap a list of flowables in colored Table(s) with optional left border.

    Returns a list of flowables. The heading (first element) is placed in a
    separate table with keepWithNext=True so it is never orphaned at the
    bottom of a page without content following it.
    """
    from reportlab.platypus import Table, TableStyle
    from reportlab.lib.colors import HexColor

    def _make_table(elems, space_before=0, space_after=0, extra_top=6, extra_bottom=6):
        data = [[e] for e in elems]
        t = Table(data, colWidths=["*"])
        n = len(data)
        cmds = [
            ("BACKGROUND", (0, 0), (-1, -1), HexColor(bg_color)),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]
        if n > 0:
            cmds.append(("TOPPADDING", (0, 0), (-1, 0), extra_top))
            cmds.append(("BOTTOMPADDING", (0, n - 1), (-1, n - 1), extra_bottom))
        if border_color:
            cmds.append(("LINEBEFORE", (0, 0), (0, -1), 3, HexColor(border_color)))
        t.setStyle(TableStyle(cmds))
        t.spaceBefore = space_before
        t.spaceAfter = space_after
        t.splitByRow = True
        return t

    return [_make_table(inner_elements, space_before=4, space_after=4)]


def _add_tool_use(
    elements, tool_name, tool_input, tool_style, code_style, escape_fn, truncate_fn
):
    """Add a tool use block wrapped in a purple container."""
    from reportlab.platypus import Paragraph, Preformatted
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor

    # Build inner elements for the tool use box
    # Use plain styles (no background) since the container provides it
    inner_tool_style = ParagraphStyle(
        "ToolUseInner",
        parent=tool_style,
        backColor=None,
        borderPadding=0,
        spaceBefore=0,
        spaceAfter=2,
    )
    # Table BACKGROUND paints over inner flowable backColor, so use
    # dark text on the container's light purple instead of light-on-dark
    inner_code_style = ParagraphStyle(
        "ToolCodeInner",
        parent=code_style,
        backColor=None,
        textColor=HexColor("#4A148C"),  # dark purple, readable on light purple
        spaceBefore=2,
        spaceAfter=2,
        borderPadding=0,
    )

    inner = []
    inner.append(Paragraph(f"<b>&#9881; {escape_fn(tool_name)}</b>", inner_tool_style))

    if tool_name == "Write":
        file_path = tool_input.get("file_path", "")
        if file_path:
            inner.append(
                Paragraph(
                    f"<font name='Courier' size=8>&rarr; {escape_fn(file_path)}</font>",
                    inner_tool_style,
                )
            )
        content = tool_input.get("content", "")
        if content:
            inner.append(Preformatted(truncate_fn(content, 1000), inner_code_style))

    elif tool_name == "Edit":
        file_path = tool_input.get("file_path", "")
        if file_path:
            inner.append(
                Paragraph(
                    f"<font name='Courier' size=8>&rarr; {escape_fn(file_path)}</font>",
                    inner_tool_style,
                )
            )
        old_str = tool_input.get("old_string", "")
        new_str = tool_input.get("new_string", "")
        if old_str:
            del_style = ParagraphStyle(
                "EditDel",
                parent=inner_code_style,
                textColor=HexColor("#B71C1C"),
            )
            inner.append(Preformatted("- " + truncate_fn(old_str, 500), del_style))
        if new_str:
            add_style = ParagraphStyle(
                "EditAdd",
                parent=inner_code_style,
                textColor=HexColor("#1B5E20"),
            )
            inner.append(Preformatted("+ " + truncate_fn(new_str, 500), add_style))

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        if command:
            inner.append(
                Preformatted("$ " + truncate_fn(command, 500), inner_code_style)
            )

    else:
        description = tool_input.get("description", "")
        if description:
            desc_style = ParagraphStyle(
                "ToolDesc",
                parent=inner_tool_style,
                textColor=HexColor("#757575"),
            )
            inner.append(Paragraph(f"<i>{escape_fn(description)}</i>", desc_style))
        display_input = {k: v for k, v in tool_input.items() if k != "description"}
        if display_input:
            input_text = json.dumps(display_input, indent=2, ensure_ascii=False)
            inner.append(Preformatted(truncate_fn(input_text, 500), inner_code_style))

    elements.extend(_wrap_in_colored_box(inner, "#F3E5F5", "#9C27B0"))


_CHUNK_LINES = 20  # Split Preformatted into chunks of this many lines


def _add_preformatted_chunks(elements, text, style):
    """Add text as multiple Preformatted blocks so table rows can split."""
    from reportlab.platypus import Preformatted

    lines = text.split("\n")
    if len(lines) <= _CHUNK_LINES:
        elements.append(Preformatted(text, style))
        return
    for i in range(0, len(lines), _CHUNK_LINES):
        chunk = "\n".join(lines[i : i + _CHUNK_LINES])
        elements.append(Preformatted(chunk, style))


def _add_tool_result(
    elements,
    result_content,
    is_error,
    github_repo,
    result_style,
    commit_style,
    escape_fn,
    truncate_fn,
    commit_pattern,
):
    """Add a tool result block (content only, container handles background)."""
    from reportlab.platypus import Paragraph, Preformatted
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor

    # Use plain styles since the outer container provides background
    plain_result = ParagraphStyle(
        "ToolResultPlain",
        parent=result_style,
        backColor=None,
        borderPadding=0,
        spaceBefore=2,
        spaceAfter=2,
    )

    if isinstance(result_content, str):
        commits = list(commit_pattern.finditer(result_content))
        if commits:
            last_end = 0
            for match in commits:
                before = result_content[last_end : match.start()].strip()
                if before:
                    _add_preformatted_chunks(
                        elements, truncate_fn(before, 1000), plain_result
                    )
                commit_hash = match.group(1)
                commit_msg = match.group(2)
                hash_display = escape_fn(commit_hash[:7])
                if github_repo:
                    link = f"https://github.com/{github_repo}/commit/{commit_hash}"
                    hash_part = f"<a href='{link}' color='#E65100'><font name='Courier'><b>{hash_display}</b></font></a>"
                else:
                    hash_part = f"<font name='Courier' color='#E65100'><b>{hash_display}</b></font>"
                elements.append(
                    Paragraph(
                        f"{hash_part} {escape_fn(commit_msg)}",
                        commit_style,
                    )
                )
                last_end = match.end()
            after = result_content[last_end:].strip()
            if after:
                _add_preformatted_chunks(
                    elements, truncate_fn(after, 1000), plain_result
                )
        else:
            text = truncate_fn(result_content, 1000)
            if text.strip():
                if is_error:
                    err_style = ParagraphStyle(
                        "ErrorResult",
                        parent=plain_result,
                        textColor=HexColor("#B71C1C"),
                    )
                    _add_preformatted_chunks(elements, text, err_style)
                else:
                    _add_preformatted_chunks(elements, text, plain_result)
    elif isinstance(result_content, list):
        for item in result_content:
            if isinstance(item, dict):
                text = item.get("text", "")
                if text:
                    _add_preformatted_chunks(
                        elements, truncate_fn(text, 1000), plain_result
                    )


def _add_image_block(elements, block):
    """Add an image block placeholder."""
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.colors import HexColor

    img_style = ParagraphStyle(
        "ImagePlaceholder",
        fontName="Helvetica-Oblique",
        fontSize=9,
        textColor=HexColor("#999999"),
    )
    source_type = block.get("source", {}).get("type", "unknown")
    elements.append(Paragraph(f"[Image: {source_type}]", img_style))
