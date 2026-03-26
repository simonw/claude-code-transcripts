"""Parse Claude Code session files (JSON and JSONL formats)."""

import json
from pathlib import Path


def parse_session_file(filepath):
    """Parse a session file and return a list of normalized logline entries.

    Supports both JSON and JSONL formats.
    """
    filepath = Path(filepath)

    if filepath.suffix == ".jsonl":
        return _parse_jsonl_file(filepath)
    else:
        # Standard JSON format
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f).get("loglines", [])


def _parse_jsonl_file(filepath):
    """Parse JSONL file and convert to standard format."""
    loglines = []

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                entry_type = obj.get("type")
                is_meta = entry_type == "user" and (
                    obj.get("isMeta", False) or obj.get("isSynthetic", False)
                )

                # Skip non-message entries
                if entry_type not in ("user", "assistant") or is_meta:
                    continue

                # Convert to standard format
                entry = {
                    "type": entry_type,
                    "timestamp": obj.get("timestamp")
                    or obj.get("_audit_timestamp", ""),
                    "message": obj.get("message", {}),
                }

                # Preserve isCompactSummary if present
                if obj.get("isCompactSummary"):
                    entry["isCompactSummary"] = True

                loglines.append(entry)
            except json.JSONDecodeError:
                continue

    return loglines
