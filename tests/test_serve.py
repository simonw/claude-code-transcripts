"""Tests for the serve CLI command."""

import sqlite3
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import pytest
from click.testing import CliRunner

from claude_code_transcripts import cli
from claude_code_transcripts.db import get_db, import_session
from claude_code_transcripts.serve import make_handler


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.fixture
def populated_db(db_path):
    """Create a DB with some test sessions."""
    conn = get_db(db_path)
    import_session(
        conn,
        session_id="abc123",
        project_name="project-a",
        project_key="-home-user-projects-project-a",
        summary="Hello from project A",
        session_json='{"loglines": []}',
        pages={
            "index.html": "<html><body>Session index</body></html>",
            "page-001.html": "<html><body>Page 1 content</body></html>",
        },
        meta={
            "total_pages": 1,
            "total_prompts": 1,
            "total_messages": 2,
            "total_tool_calls": 0,
            "total_commits": 0,
            "github_repo": None,
        },
        file_size=1024,
    )
    import_session(
        conn,
        session_id="def456",
        project_name="project-a",
        project_key="-home-user-projects-project-a",
        summary="Second session",
        session_json='{"loglines": []}',
        pages={
            "index.html": "<html><body>Session 2 index</body></html>",
            "page-001.html": "<html><body>Session 2 page 1</body></html>",
        },
        meta={
            "total_pages": 1,
            "total_prompts": 1,
            "total_messages": 2,
            "total_tool_calls": 0,
            "total_commits": 0,
            "github_repo": None,
        },
        file_size=512,
    )
    import_session(
        conn,
        session_id="ghi789",
        project_name="project-b",
        project_key="-home-user-projects-project-b",
        summary="Hello from project B",
        session_json='{"loglines": []}',
        pages={
            "index.html": "<html><body>Project B session</body></html>",
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
    conn.close()
    return db_path


class TestTranscriptHandler:
    """Test the HTTP handler using a real HTTP server on a random port."""

    @pytest.fixture(autouse=True)
    def setup_server(self, populated_db):
        """Start a test server on a random port."""
        from http.server import HTTPServer

        handler = make_handler(populated_db)
        self.server = HTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        yield
        self.server.shutdown()

    def _get(self, path):
        """Make a GET request and return (status_code, body)."""
        url = f"{self.base_url}{path}"
        try:
            resp = urllib.request.urlopen(url)
            return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def test_root_returns_master_index(self):
        status, body = self._get("/")
        assert status == 200
        assert "project-a" in body
        assert "project-b" in body

    def test_project_page(self):
        status, body = self._get("/project-a/")
        assert status == 200
        assert "abc123" in body
        assert "def456" in body

    def test_session_index_page(self):
        status, body = self._get("/project-a/abc123/index.html")
        assert status == 200
        assert "Session index" in body

    def test_session_page(self):
        status, body = self._get("/project-a/abc123/page-001.html")
        assert status == 200
        assert "Page 1 content" in body

    def test_session_dir_redirects_to_index(self):
        # Accessing /project/session/ should redirect to index.html
        url = f"{self.base_url}/project-a/abc123/"
        req = urllib.request.Request(url)
        # Don't follow redirects
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request("GET", "/project-a/abc123/")
        resp = conn.getresponse()
        assert resp.status in (301, 302)
        assert "index.html" in resp.getheader("Location")
        conn.close()

    def test_nonexistent_session_returns_404(self):
        status, body = self._get("/project-a/nonexistent/index.html")
        assert status == 404

    def test_nonexistent_project_returns_404(self):
        status, body = self._get("/nonexistent/")
        assert status == 404

    def test_nonexistent_page_returns_404(self):
        status, body = self._get("/project-a/abc123/page-999.html")
        assert status == 404
