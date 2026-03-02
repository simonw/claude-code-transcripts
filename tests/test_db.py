"""Tests for SQLite database operations."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from claude_code_transcripts.db import (
    get_db,
    session_exists,
    import_session,
    get_session_page,
    list_projects,
    list_sessions,
)


@pytest.fixture
def db_path():
    """Create a temporary database file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.fixture
def db(db_path):
    """Create and return a database connection."""
    conn = get_db(db_path)
    yield conn
    conn.close()


class TestGetDb:
    def test_creates_database_file(self, db_path):
        conn = get_db(db_path)
        assert db_path.exists()
        conn.close()

    def test_creates_sessions_table(self, db):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
        )
        assert cursor.fetchone() is not None

    def test_creates_session_pages_table(self, db):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_pages'"
        )
        assert cursor.fetchone() is not None

    def test_enables_wal_mode(self, db):
        cursor = db.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode == "wal"

    def test_idempotent(self, db_path):
        """Calling get_db twice on the same path doesn't error."""
        conn1 = get_db(db_path)
        conn1.close()
        conn2 = get_db(db_path)
        conn2.close()

    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            deep_path = Path(tmpdir) / "a" / "b" / "test.db"
            conn = get_db(deep_path)
            assert deep_path.exists()
            conn.close()


class TestSessionExists:
    def test_returns_false_for_missing_session(self, db):
        assert session_exists(db, "nonexistent") is False

    def test_returns_true_for_existing_session(self, db):
        import_session(
            db,
            session_id="abc123",
            project_name="myproject",
            project_key="-home-user-projects-myproject",
            summary="Hello world",
            session_json='{"type": "user"}',
            pages={"index.html": "<html>index</html>"},
            meta={
                "total_pages": 1,
                "total_prompts": 1,
                "total_messages": 2,
                "total_tool_calls": 0,
                "total_commits": 0,
                "github_repo": None,
            },
        )
        assert session_exists(db, "abc123") is True


class TestImportSession:
    def test_inserts_session_row(self, db):
        import_session(
            db,
            session_id="abc123",
            project_name="myproject",
            project_key="-home-user-projects-myproject",
            summary="Hello world",
            session_json='{"type": "user"}',
            pages={"index.html": "<html>index</html>"},
            meta={
                "total_pages": 1,
                "total_prompts": 1,
                "total_messages": 2,
                "total_tool_calls": 5,
                "total_commits": 1,
                "github_repo": "owner/repo",
            },
        )
        row = db.execute(
            "SELECT session_id, project_name, project_key, summary, session_json, "
            "github_repo, total_pages, total_prompts, total_messages, total_tool_calls, total_commits "
            "FROM sessions WHERE session_id = ?",
            ("abc123",),
        ).fetchone()
        assert row is not None
        assert row[0] == "abc123"
        assert row[1] == "myproject"
        assert row[2] == "-home-user-projects-myproject"
        assert row[3] == "Hello world"
        assert row[4] == '{"type": "user"}'
        assert row[5] == "owner/repo"
        assert row[6] == 1  # total_pages
        assert row[7] == 1  # total_prompts
        assert row[8] == 2  # total_messages
        assert row[9] == 5  # total_tool_calls
        assert row[10] == 1  # total_commits

    def test_inserts_page_rows(self, db):
        pages = {
            "index.html": "<html>index</html>",
            "page-001.html": "<html>page 1</html>",
            "page-002.html": "<html>page 2</html>",
        }
        import_session(
            db,
            session_id="abc123",
            project_name="myproject",
            project_key="-home-user-projects-myproject",
            summary="Hello",
            session_json="{}",
            pages=pages,
            meta={
                "total_pages": 2,
                "total_prompts": 1,
                "total_messages": 2,
                "total_tool_calls": 0,
                "total_commits": 0,
                "github_repo": None,
            },
        )
        rows = db.execute(
            "SELECT page_name, html_content FROM session_pages WHERE session_id = ? ORDER BY page_name",
            ("abc123",),
        ).fetchall()
        assert len(rows) == 3
        assert rows[0] == ("index.html", "<html>index</html>")
        assert rows[1] == ("page-001.html", "<html>page 1</html>")
        assert rows[2] == ("page-002.html", "<html>page 2</html>")

    def test_skips_duplicate_session(self, db):
        """Importing the same session_id twice should skip the second import."""
        kwargs = dict(
            session_id="abc123",
            project_name="myproject",
            project_key="-home-user-projects-myproject",
            summary="Hello",
            session_json="{}",
            pages={"index.html": "<html>v1</html>"},
            meta={
                "total_pages": 1,
                "total_prompts": 1,
                "total_messages": 2,
                "total_tool_calls": 0,
                "total_commits": 0,
                "github_repo": None,
            },
        )
        import_session(db, **kwargs)
        # Second import with different content should be skipped
        kwargs["pages"] = {"index.html": "<html>v2</html>"}
        import_session(db, **kwargs)

        # Should still have original content
        html = get_session_page(db, "abc123", "index.html")
        assert html == "<html>v1</html>"

    def test_stores_optional_metadata(self, db):
        import_session(
            db,
            session_id="abc123",
            project_name="myproject",
            project_key="key",
            summary="Hello",
            session_json="{}",
            pages={"index.html": "<html></html>"},
            meta={
                "total_pages": 1,
                "total_prompts": 1,
                "total_messages": 2,
                "total_tool_calls": 0,
                "total_commits": 0,
                "github_repo": None,
            },
            file_mtime=1704067200.0,
            file_size=1024,
            created_at="2025-01-01T10:00:00.000Z",
        )
        row = db.execute(
            "SELECT file_mtime, file_size, created_at FROM sessions WHERE session_id = ?",
            ("abc123",),
        ).fetchone()
        assert row[0] == 1704067200.0
        assert row[1] == 1024
        assert row[2] == "2025-01-01T10:00:00.000Z"


class TestGetSessionPage:
    def test_returns_html_content(self, db):
        import_session(
            db,
            session_id="abc123",
            project_name="myproject",
            project_key="key",
            summary="Hello",
            session_json="{}",
            pages={
                "index.html": "<html>index</html>",
                "page-001.html": "<html>page 1</html>",
            },
            meta={
                "total_pages": 1,
                "total_prompts": 1,
                "total_messages": 2,
                "total_tool_calls": 0,
                "total_commits": 0,
                "github_repo": None,
            },
        )
        assert get_session_page(db, "abc123", "index.html") == "<html>index</html>"
        assert get_session_page(db, "abc123", "page-001.html") == "<html>page 1</html>"

    def test_returns_none_for_missing_page(self, db):
        assert get_session_page(db, "abc123", "index.html") is None

    def test_returns_none_for_missing_session(self, db):
        assert get_session_page(db, "nonexistent", "index.html") is None


class TestListProjects:
    def test_returns_empty_for_empty_db(self, db):
        assert list_projects(db) == []

    def test_returns_projects_with_session_counts(self, db):
        for sid, pname, pkey in [
            ("s1", "project-a", "key-a"),
            ("s2", "project-a", "key-a"),
            ("s3", "project-b", "key-b"),
        ]:
            import_session(
                db,
                session_id=sid,
                project_name=pname,
                project_key=pkey,
                summary="Hello",
                session_json="{}",
                pages={"index.html": "<html></html>"},
                meta={
                    "total_pages": 1,
                    "total_prompts": 1,
                    "total_messages": 2,
                    "total_tool_calls": 0,
                    "total_commits": 0,
                    "github_repo": None,
                },
            )

        projects = list_projects(db)
        assert len(projects) == 2
        # Should be sorted by most recent import
        names = [p["name"] for p in projects]
        assert "project-a" in names
        assert "project-b" in names
        # Check session counts
        proj_a = next(p for p in projects if p["name"] == "project-a")
        proj_b = next(p for p in projects if p["name"] == "project-b")
        assert proj_a["session_count"] == 2
        assert proj_b["session_count"] == 1


class TestListSessions:
    def test_returns_empty_for_no_sessions(self, db):
        assert list_sessions(db, "nonexistent") == []

    def test_returns_sessions_for_project(self, db):
        import_session(
            db,
            session_id="s1",
            project_name="myproject",
            project_key="key",
            summary="First session",
            session_json="{}",
            pages={"index.html": "<html></html>"},
            meta={
                "total_pages": 1,
                "total_prompts": 3,
                "total_messages": 10,
                "total_tool_calls": 5,
                "total_commits": 2,
                "github_repo": "owner/repo",
            },
            file_size=2048,
        )
        import_session(
            db,
            session_id="s2",
            project_name="myproject",
            project_key="key",
            summary="Second session",
            session_json="{}",
            pages={"index.html": "<html></html>"},
            meta={
                "total_pages": 1,
                "total_prompts": 1,
                "total_messages": 4,
                "total_tool_calls": 0,
                "total_commits": 0,
                "github_repo": None,
            },
            file_size=512,
        )

        sessions = list_sessions(db, "myproject")
        assert len(sessions) == 2
        s1 = next(s for s in sessions if s["session_id"] == "s1")
        assert s1["summary"] == "First session"
        assert s1["total_prompts"] == 3
        assert s1["file_size"] == 2048

    def test_does_not_return_sessions_from_other_projects(self, db):
        import_session(
            db,
            session_id="s1",
            project_name="project-a",
            project_key="key-a",
            summary="A session",
            session_json="{}",
            pages={"index.html": "<html></html>"},
            meta={
                "total_pages": 1,
                "total_prompts": 1,
                "total_messages": 2,
                "total_tool_calls": 0,
                "total_commits": 0,
                "github_repo": None,
            },
        )
        assert list_sessions(db, "project-b") == []
