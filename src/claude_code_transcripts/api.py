"""Claude API access and credential management for web sessions."""

import json
import os
import platform
import re
import subprocess
from pathlib import Path

import httpx

API_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"


class CredentialsError(Exception):
    """Raised when credentials cannot be obtained."""

    pass


def get_access_token_from_keychain():
    """Get access token from macOS keychain.

    Returns the access token or None if not found.
    Raises CredentialsError with helpful message on failure.
    """
    if platform.system() != "Darwin":
        return None

    try:
        result = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a",
                os.environ.get("USER", ""),
                "-s",
                "Claude Code-credentials",
                "-w",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None

        creds = json.loads(result.stdout.strip())
        return creds.get("claudeAiOauth", {}).get("accessToken")
    except (json.JSONDecodeError, subprocess.SubprocessError):
        return None


def get_org_uuid_from_config():
    """Get organization UUID from ~/.claude.json.

    Returns the organization UUID or None if not found.
    """
    config_path = Path.home() / ".claude.json"
    if not config_path.exists():
        return None

    try:
        with open(config_path) as f:
            config = json.load(f)
        return config.get("oauthAccount", {}).get("organizationUuid")
    except (json.JSONDecodeError, IOError):
        return None


def get_api_headers(token, org_uuid):
    """Build API request headers."""
    return {
        "Authorization": f"Bearer {token}",
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
        "x-organization-uuid": org_uuid,
    }


def fetch_sessions(token, org_uuid):
    """Fetch list of sessions from the API.

    Returns the sessions data as a dict.
    Raises httpx.HTTPError on network/API errors.
    """
    headers = get_api_headers(token, org_uuid)
    response = httpx.get(f"{API_BASE_URL}/sessions", headers=headers, timeout=30.0)
    response.raise_for_status()
    return response.json()


def fetch_session(token, org_uuid, session_id):
    """Fetch a specific session from the API.

    Returns the session data as a dict.
    Raises httpx.HTTPError on network/API errors.
    """
    headers = get_api_headers(token, org_uuid)
    response = httpx.get(
        f"{API_BASE_URL}/session_ingress/session/{session_id}",
        headers=headers,
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()


def extract_repo_from_session(session):
    """Extract GitHub repo from session metadata.

    Looks in session_context.outcomes for git_info.repo,
    or parses from session_context.sources URL.

    Returns repo as "owner/name" or None.
    """
    context = session.get("session_context", {})

    outcomes = context.get("outcomes", [])
    for outcome in outcomes:
        if outcome.get("type") == "git_repository":
            git_info = outcome.get("git_info", {})
            repo = git_info.get("repo")
            if repo:
                return repo

    sources = context.get("sources", [])
    for source in sources:
        if source.get("type") == "git_repository":
            url = source.get("url", "")
            if "github.com/" in url:
                match = re.search(r"github\.com/([^/]+/[^/]+?)(?:\.git)?$", url)
                if match:
                    return match.group(1)

    return None


def enrich_sessions_with_repos(sessions, token=None, org_uuid=None, fetch_fn=None):
    """Enrich sessions with repo information from session metadata.

    Args:
        sessions: List of session dicts from the API
        token: Unused (kept for backward compatibility)
        org_uuid: Unused (kept for backward compatibility)
        fetch_fn: Unused (kept for backward compatibility)

    Returns:
        List of session dicts with 'repo' key added
    """
    enriched = []
    for session in sessions:
        session_copy = dict(session)
        session_copy["repo"] = extract_repo_from_session(session)
        enriched.append(session_copy)
    return enriched


def filter_sessions_by_repo(sessions, repo):
    """Filter sessions by repo.

    Args:
        sessions: List of session dicts with 'repo' key
        repo: Repo to filter by (owner/name), or None to return all

    Returns:
        Filtered list of sessions
    """
    if repo is None:
        return sessions
    return [s for s in sessions if s.get("repo") == repo]
