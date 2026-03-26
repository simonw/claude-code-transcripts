"""Discover and summarize local Claude Code session files."""

import json
from pathlib import Path

from platformdirs import user_data_dir


def extract_text_from_content(content):
    """Extract plain text from message content.

    Handles both string content (older format) and array content (newer format).

    Args:
        content: Either a string or a list of content blocks like
                 [{"type": "text", "text": "..."}, {"type": "image", ...}]

    Returns:
        The extracted text as a string, or empty string if no text found.
    """
    if isinstance(content, str):
        return content.strip()
    elif isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    texts.append(text)
        return " ".join(texts).strip()
    return ""


def get_session_summary(filepath, max_length=200):
    """Extract a human-readable summary from a session file.

    Supports both JSON and JSONL formats.
    Returns a summary string or "(no summary)" if none found.
    """
    filepath = Path(filepath)
    try:
        if filepath.suffix == ".jsonl":
            return _get_jsonl_summary(filepath, max_length)
        else:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            loglines = data.get("loglines", [])
            for entry in loglines:
                if entry.get("type") == "user":
                    msg = entry.get("message", {})
                    content = msg.get("content", "")
                    text = extract_text_from_content(content)
                    if text:
                        if len(text) > max_length:
                            return text[: max_length - 3] + "..."
                        return text
            return "(no summary)"
    except Exception:
        return "(no summary)"


def _get_jsonl_summary(filepath, max_length=200):
    """Extract summary from JSONL file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("type") == "summary" and obj.get("summary"):
                        summary = obj["summary"]
                        if len(summary) > max_length:
                            return summary[: max_length - 3] + "..."
                        return summary
                except json.JSONDecodeError:
                    continue

        # Second pass: find first non-meta user message
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if (
                        obj.get("type") == "user"
                        and not obj.get("isMeta")
                        and obj.get("message", {}).get("content")
                    ):
                        content = obj["message"]["content"]
                        text = extract_text_from_content(content)
                        if text and not text.startswith("<"):
                            if len(text) > max_length:
                                return text[: max_length - 3] + "..."
                            return text
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return "(no summary)"


def find_local_sessions(folder, limit=10):
    """Find recent JSONL session files in the given folder.

    Returns a list of (Path, summary) tuples sorted by modification time.
    Excludes agent files and warmup/empty sessions.
    """
    folder = Path(folder)
    if not folder.exists():
        return []

    results = []
    for f in folder.glob("**/*.jsonl"):
        if f.name.startswith("agent-"):
            continue
        summary = get_session_summary(f)
        if summary.lower() == "warmup" or summary == "(no summary)":
            continue
        results.append((f, summary))

    results.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)
    return results[:limit]


def find_cowork_sessions(base_dir=None, limit=None):
    """Find recent Cowork session JSONL files.

    Reads session metadata from the platform-specific Claude Cowork directory:
    - macOS: ~/Library/Application Support/Claude/local-agent-mode-sessions/
    - Windows: %APPDATA%/Claude/local-agent-mode-sessions/
    - Linux: ~/.local/share/Claude/local-agent-mode-sessions/
    and locates the corresponding JSONL transcript files.

    Returns a list of dicts sorted by lastActivityAt descending, limited to `limit`.
    Each dict has: title, jsonl_path, folders, mtime.
    """
    if base_dir is None:
        base_dir = (
            Path(user_data_dir("Claude", appauthor=False, roaming=True))
            / "local-agent-mode-sessions"
        )
    base_dir = Path(base_dir)
    if not base_dir.exists():
        return []

    results = []
    for metadata_file in base_dir.glob("**/local_*.json"):
        if not metadata_file.is_file():
            continue
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        process_name = metadata.get("processName", "")
        cli_session_id = metadata.get("cliSessionId", "")
        title = metadata.get("title") or metadata.get("initialMessage", "(untitled)")
        folders = metadata.get("userSelectedFolders", [])
        last_activity_at = metadata.get("lastActivityAt", 0)

        stem = metadata_file.stem  # e.g. "local_sess-789"
        jsonl_path = (
            metadata_file.parent
            / stem
            / ".claude"
            / "projects"
            / f"-sessions-{process_name}"
            / f"{cli_session_id}.jsonl"
        )

        if not jsonl_path.exists():
            continue

        results.append(
            {
                "title": title,
                "jsonl_path": jsonl_path,
                "folders": folders,
                "mtime": last_activity_at / 1000,
            }
        )

    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results[:limit] if limit is not None else results


def get_project_display_name(folder_name):
    """Convert encoded folder name to readable project name.

    Claude Code stores projects in folders like:
    - -home-user-projects-myproject -> myproject
    - -mnt-c-Users-name-Projects-app -> app

    For nested paths under common roots (home, projects, code, Users, etc.),
    extracts the meaningful project portion.
    """
    prefixes_to_strip = [
        "-home-",
        "-mnt-c-Users-",
        "-mnt-c-users-",
        "-Users-",
    ]

    name = folder_name
    for prefix in prefixes_to_strip:
        if name.lower().startswith(prefix.lower()):
            name = name[len(prefix) :]
            break

    parts = name.split("-")

    skip_dirs = {"projects", "code", "repos", "src", "dev", "work", "documents"}

    meaningful_parts = []
    found_project = False

    for i, part in enumerate(parts):
        if not part:
            continue
        if i == 0 and not found_project:
            remaining = [p.lower() for p in parts[i + 1 :]]
            if any(d in remaining for d in skip_dirs):
                continue
        if part.lower() in skip_dirs:
            found_project = True
            continue
        meaningful_parts.append(part)
        found_project = True

    if meaningful_parts:
        return "-".join(meaningful_parts)

    for part in reversed(parts):
        if part:
            return part
    return folder_name


def find_all_sessions(folder, include_agents=False):
    """Find all sessions in a Claude projects folder, grouped by project.

    Returns a list of project dicts, each containing:
    - name: display name for the project
    - path: Path to the project folder
    - sessions: list of session dicts with path, summary, mtime, size

    Sessions are sorted by modification time (most recent first) within each project.
    Projects are sorted by their most recent session.
    """
    folder = Path(folder)
    if not folder.exists():
        return []

    projects = {}

    for session_file in folder.glob("**/*.jsonl"):
        if not include_agents and session_file.name.startswith("agent-"):
            continue

        summary = get_session_summary(session_file)
        if summary.lower() == "warmup" or summary == "(no summary)":
            continue

        project_folder = session_file.parent
        project_key = project_folder.name

        if project_key not in projects:
            projects[project_key] = {
                "name": get_project_display_name(project_key),
                "path": project_folder,
                "sessions": [],
            }

        stat = session_file.stat()
        projects[project_key]["sessions"].append(
            {
                "path": session_file,
                "summary": summary,
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            }
        )

    for project in projects.values():
        project["sessions"].sort(key=lambda s: s["mtime"], reverse=True)

    result = list(projects.values())
    result.sort(
        key=lambda p: p["sessions"][0]["mtime"] if p["sessions"] else 0, reverse=True
    )

    return result
