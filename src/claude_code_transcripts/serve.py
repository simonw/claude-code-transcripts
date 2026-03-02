"""HTTP server for serving transcripts from SQLite."""

import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote

from claude_code_transcripts.db import (
    get_db,
    get_session_page,
    list_projects,
    list_sessions,
)


def _render_master_index(conn):
    """Render the master index page listing all projects."""
    from claude_code_transcripts import get_template, CSS

    projects = list_projects(conn)
    if not projects:
        return None

    template = get_template("master_index.html")

    projects_data = []
    for project in projects:
        sessions = list_sessions(conn, project["name"])
        projects_data.append(
            {
                "name": project["name"],
                "sessions": [
                    {
                        "name": s["session_id"],
                        "summary": s["summary"] or "",
                        "date": s["imported_at"] or "",
                        "size_kb": (s["file_size"] or 0) / 1024,
                    }
                    for s in sessions
                ],
            }
        )

    return template.render(
        projects=projects_data,
        total_projects=len(projects_data),
        total_sessions=sum(p["session_count"] for p in projects),
        css=CSS,
    )


def _render_project_index(conn, project_name):
    """Render the project index page listing sessions."""
    from claude_code_transcripts import get_template, CSS

    sessions = list_sessions(conn, project_name)
    if not sessions:
        return None

    template = get_template("project_index.html")

    sessions_data = []
    for s in sessions:
        sessions_data.append(
            {
                "name": s["session_id"],
                "summary": s["summary"] or "",
                "date": s["imported_at"] or "",
                "size_kb": (s["file_size"] or 0) / 1024,
            }
        )

    return template.render(
        project_name=project_name,
        sessions=sessions_data,
        session_count=len(sessions_data),
        css=CSS,
    )


def make_handler(db_path):
    """Create a request handler class bound to a specific database."""

    class TranscriptHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = unquote(self.path)

            # Strip query string
            if "?" in path:
                path = path.split("?")[0]

            # Route: / -> master index
            if path == "/" or path == "":
                conn = get_db(db_path)
                try:
                    html = _render_master_index(conn)
                finally:
                    conn.close()
                if html:
                    self._send_html(200, html)
                else:
                    self._send_html(404, "<h1>No transcripts found</h1>")
                return

            # Parse path segments
            parts = [p for p in path.strip("/").split("/") if p]

            # Route: /<project>/ -> project index
            if len(parts) == 1:
                project_name = parts[0]
                conn = get_db(db_path)
                try:
                    html = _render_project_index(conn, project_name)
                finally:
                    conn.close()
                if html:
                    self._send_html(200, html)
                else:
                    self._send_html(404, "<h1>Project not found</h1>")
                return

            # Route: /<project>/<session>/ -> redirect to index.html
            if len(parts) == 2:
                self.send_response(302)
                self.send_header("Location", f"/{parts[0]}/{parts[1]}/index.html")
                self.end_headers()
                return

            # Route: /<project>/<session>/<page>.html -> session page
            if len(parts) == 3:
                project_name, session_id, page_name = parts
                conn = get_db(db_path)
                try:
                    html = get_session_page(conn, session_id, page_name)
                finally:
                    conn.close()
                if html:
                    self._send_html(200, html)
                else:
                    self._send_html(404, "<h1>Page not found</h1>")
                return

            self._send_html(404, "<h1>Not found</h1>")

        def _send_html(self, status, content):
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            encoded = content.encode("utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format, *args):
            # Suppress default stderr logging during tests
            pass

    return TranscriptHandler
