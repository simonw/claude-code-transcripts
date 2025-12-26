"""Flask web server for viewing transcripts with scheduled updates."""

import os
import click
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, send_from_directory, abort
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import scoped_session, sessionmaker

from .config import Config
from .models import init_db, get_engine, Conversation
from .sync import sync_all


def create_app(config: Config):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
    app.config["CLAUDE_CONFIG"] = config

    # Initialize database
    engine = init_db(config.database_url)
    session_factory = sessionmaker(bind=engine)
    app.config["DB_SESSION"] = scoped_session(session_factory)

    # Create storage directory if it doesn't exist
    os.makedirs(config.storage_path, exist_ok=True)

    @app.route("/")
    def index():
        """Show list of all transcripts."""
        db_session = app.config["DB_SESSION"]()
        try:
            conversations = (
                db_session.query(Conversation)
                .order_by(Conversation.last_updated.desc())
                .all()
            )
            return render_template("server/index.html", conversations=conversations)
        finally:
            db_session.close()

    @app.route("/transcript/<session_id>")
    def view_transcript(session_id):
        """View a specific transcript."""
        db_session = app.config["DB_SESSION"]()
        try:
            conversation = (
                db_session.query(Conversation).filter_by(session_id=session_id).first()
            )
            if not conversation:
                abort(404)

            # Serve the index.html from the transcript's directory
            index_path = Path(conversation.html_path) / "index.html"
            if not index_path.exists():
                abort(404)

            # Read and serve the file
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Inject base URL for assets
            base_url = f"/transcript/{session_id}/assets/"
            content = content.replace('src="', f'src="{base_url}')
            content = content.replace(
                'href="page-', f'href="/transcript/{session_id}/page-'
            )

            return content
        finally:
            db_session.close()

    @app.route("/transcript/<session_id>/page-<int:page_num>.html")
    def view_page(session_id, page_num):
        """View a specific page of a transcript."""
        db_session = app.config["DB_SESSION"]()
        try:
            conversation = (
                db_session.query(Conversation).filter_by(session_id=session_id).first()
            )
            if not conversation:
                abort(404)

            page_path = Path(conversation.html_path) / f"page-{page_num:03d}.html"
            if not page_path.exists():
                abort(404)

            with open(page_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Fix navigation links
            content = content.replace(
                'href="page-', f'href="/transcript/{session_id}/page-'
            )
            content = content.replace(
                'href="index.html"', f'href="/transcript/{session_id}"'
            )

            return content
        finally:
            db_session.close()

    @app.route("/transcript/<session_id>/assets/<path:filename>")
    def serve_asset(session_id, filename):
        """Serve static assets for a transcript."""
        db_session = app.config["DB_SESSION"]()
        try:
            conversation = (
                db_session.query(Conversation).filter_by(session_id=session_id).first()
            )
            if not conversation:
                abort(404)

            return send_from_directory(conversation.html_path, filename)
        finally:
            db_session.close()

    @app.route("/sync")
    def trigger_sync():
        """Manually trigger a sync."""
        db_session = app.config["DB_SESSION"]()
        try:
            stats = sync_all(
                db_session,
                config.storage_path,
                token=config.claude_token,
                org_uuid=config.claude_org_uuid,
                github_repo=config.github_repo,
            )
            return {
                "status": "success",
                "timestamp": datetime.utcnow().isoformat(),
                "stats": stats,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}, 500
        finally:
            db_session.close()

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        """Clean up database sessions."""
        app.config["DB_SESSION"].remove()

    return app


def run_scheduled_sync(app):
    """Run scheduled sync in the background."""
    with app.app_context():
        config = app.config["CLAUDE_CONFIG"]
        db_session = app.config["DB_SESSION"]()
        try:
            print(f"Running scheduled sync at {datetime.now()}")
            stats = sync_all(
                db_session,
                config.storage_path,
                token=config.claude_token,
                org_uuid=config.claude_org_uuid,
                github_repo=config.github_repo,
            )
            print(f"Sync complete: {stats}")
        except Exception as e:
            print(f"Sync error: {e}")
        finally:
            db_session.close()


@click.command()
@click.option(
    "--host",
    default=None,
    help="Server host (default: from config or 127.0.0.1)",
)
@click.option(
    "--port",
    type=int,
    default=None,
    help="Server port (default: from config or 5000)",
)
@click.option(
    "--no-scheduler",
    is_flag=True,
    help="Disable automatic hourly updates",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Run in debug mode",
)
def main(host, port, no_scheduler, debug):
    """
    Start the Claude Code transcripts server.

    This server automatically syncs transcripts from Claude Code and Claude Web
    on an hourly basis and provides a web interface to view them.

    Configuration is done via environment variables:
    - DATABASE_URL: PostgreSQL connection string
    - STORAGE_PATH: Where to store HTML files
    - UPDATE_INTERVAL_MINUTES: How often to sync (default: 60)
    - SERVER_HOST: Server host (default: 127.0.0.1)
    - SERVER_PORT: Server port (default: 5000)
    - CLAUDE_TOKEN: Claude API token (optional, auto-detected on macOS)
    - CLAUDE_ORG_UUID: Claude org UUID (optional, auto-detected on macOS)
    - GITHUB_REPO: GitHub repo for commit links (optional)
    """
    # Load configuration
    config = Config()

    # Override from command line if provided
    if host:
        config.server_host = host
    if port:
        config.server_port = port

    # Create Flask app
    app = create_app(config)

    # Set up scheduler if not disabled
    if not no_scheduler:
        scheduler = BackgroundScheduler()
        scheduler.add_job(
            func=lambda: run_scheduled_sync(app),
            trigger=IntervalTrigger(minutes=config.update_interval_minutes),
            id="sync_transcripts",
            name="Sync Claude transcripts",
            replace_existing=True,
        )
        scheduler.start()
        print(
            f"Scheduler started. Syncing every {config.update_interval_minutes} minutes."
        )

        # Run initial sync on startup
        print("Running initial sync...")
        run_scheduled_sync(app)

    try:
        print(f"Starting server at http://{config.server_host}:{config.server_port}")
        print(f"Storage path: {config.storage_path}")
        print(f"Database: {config.database_url}")
        app.run(host=config.server_host, port=config.server_port, debug=debug)
    except KeyboardInterrupt:
        if not no_scheduler:
            scheduler.shutdown()
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
