"""SQLite database operations for storing Claude Code transcripts."""

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".claude" / "transcripts.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    project_key TEXT NOT NULL,
    summary TEXT,
    session_json TEXT NOT NULL,
    github_repo TEXT,
    total_pages INTEGER NOT NULL DEFAULT 0,
    total_prompts INTEGER NOT NULL DEFAULT 0,
    total_messages INTEGER NOT NULL DEFAULT 0,
    total_tool_calls INTEGER NOT NULL DEFAULT 0,
    total_commits INTEGER NOT NULL DEFAULT 0,
    file_mtime REAL,
    file_size INTEGER,
    created_at TEXT,
    imported_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS session_pages (
    session_id TEXT NOT NULL,
    page_name TEXT NOT NULL,
    html_content TEXT NOT NULL,
    PRIMARY KEY (session_id, page_name),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
"""


def get_db(db_path=None):
    """Open or create the SQLite database and ensure schema exists.

    Returns a sqlite3.Connection with WAL mode enabled.
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def session_exists(conn, session_id):
    """Check if a session already exists in the database."""
    cursor = conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,))
    return cursor.fetchone() is not None


def import_session(
    conn,
    session_id,
    project_name,
    project_key,
    summary,
    session_json,
    pages,
    meta,
    file_mtime=None,
    file_size=None,
    created_at=None,
):
    """Import a session and its HTML pages into the database.

    Skips if session_id already exists (dedup).

    Args:
        conn: sqlite3.Connection
        session_id: Unique session identifier (filename stem)
        project_name: Human-readable project name
        project_key: Raw folder name for the project
        summary: First user message preview
        session_json: Raw JSONL content
        pages: dict of {page_name: html_content}
        meta: dict with total_pages, total_prompts, total_messages,
              total_tool_calls, total_commits, github_repo
        file_mtime: Original file modification time (unix timestamp)
        file_size: Original file size in bytes
        created_at: Earliest timestamp from session
    """
    if session_exists(conn, session_id):
        return

    conn.execute(
        """INSERT INTO sessions
        (session_id, project_name, project_key, summary, session_json,
         github_repo, total_pages, total_prompts, total_messages,
         total_tool_calls, total_commits, file_mtime, file_size, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            project_name,
            project_key,
            summary,
            session_json,
            meta.get("github_repo"),
            meta.get("total_pages", 0),
            meta.get("total_prompts", 0),
            meta.get("total_messages", 0),
            meta.get("total_tool_calls", 0),
            meta.get("total_commits", 0),
            file_mtime,
            file_size,
            created_at,
        ),
    )

    for page_name, html_content in pages.items():
        conn.execute(
            "INSERT INTO session_pages (session_id, page_name, html_content) VALUES (?, ?, ?)",
            (session_id, page_name, html_content),
        )

    conn.commit()


def get_session_page(conn, session_id, page_name):
    """Fetch a single HTML page for a session.

    Returns the HTML content string, or None if not found.
    """
    cursor = conn.execute(
        "SELECT html_content FROM session_pages WHERE session_id = ? AND page_name = ?",
        (session_id, page_name),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def list_projects(conn):
    """List all projects with session counts.

    Returns a list of dicts with keys: name, project_key, session_count, latest_import.
    Sorted by most recent import.
    """
    cursor = conn.execute(
        """SELECT project_name, project_key, COUNT(*) as session_count,
                  MAX(imported_at) as latest_import
           FROM sessions
           GROUP BY project_name
           ORDER BY latest_import DESC"""
    )
    return [
        {
            "name": row[0],
            "project_key": row[1],
            "session_count": row[2],
            "latest_import": row[3],
        }
        for row in cursor.fetchall()
    ]


def list_sessions(conn, project_name):
    """List all sessions for a given project.

    Returns a list of dicts sorted by imported_at descending.
    """
    cursor = conn.execute(
        """SELECT session_id, summary, total_pages, total_prompts,
                  total_messages, total_tool_calls, total_commits,
                  github_repo, file_mtime, file_size, created_at, imported_at
           FROM sessions
           WHERE project_name = ?
           ORDER BY imported_at DESC""",
        (project_name,),
    )
    return [
        {
            "session_id": row[0],
            "summary": row[1],
            "total_pages": row[2],
            "total_prompts": row[3],
            "total_messages": row[4],
            "total_tool_calls": row[5],
            "total_commits": row[6],
            "github_repo": row[7],
            "file_mtime": row[8],
            "file_size": row[9],
            "created_at": row[10],
            "imported_at": row[11],
        }
        for row in cursor.fetchall()
    ]
