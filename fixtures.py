"""
fixtures.py
Loads upcoming match fixtures from a local JSON file.

All kickoff times are parsed and compared as timezone-aware UTC
datetimes — never local time.

Public API:
    load_fixtures(path=None) -> list[dict]
    match_key(fixture)       -> str
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import config


# ═══════════════════════════════════════════════════════════════════════════════
# LOADING
# ═══════════════════════════════════════════════════════════════════════════════
def load_fixtures(path: Path | None = None) -> list[dict]:
    """
    Loads fixtures from data/fixtures.json.

    Each entry in the JSON file looks like:
        {"home": "Spain", "away": "Brazil", "kickoff_utc": "2026-06-15T02:00:00Z"}

    Returns a list of dicts with the original fields plus a parsed
    "kickoff" datetime (timezone-aware, UTC). Returns an empty list if
    the file does not exist.
    """
    fp = path or config.FIXTURES_FILE
    print("[INFO] Loading fixtures...")
    if not fp.exists():
        print(f"[INFO] No fixtures file found at {fp}")
        return []

    with open(fp, "r", encoding="utf-8") as f:
        raw = json.load(f)

    fixtures = []
    for item in raw:
        fixtures.append({
            "home":        item["home"],
            "away":        item["away"],
            "kickoff_utc": item["kickoff_utc"],
            "kickoff":     _parse_utc(item["kickoff_utc"]),
        })
    return fixtures


def _parse_utc(value: str) -> datetime:
    """Parses an ISO-8601 timestamp (accepts a trailing 'Z') into a
    timezone-aware UTC datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════════
# IDENTITY
# ═══════════════════════════════════════════════════════════════════════════════
def match_key(fixture: dict) -> str:
    """
    Builds a stable identifier for a fixture: "Home_Away_YYYY-MM-DD"
    (UTC date of kickoff). Used to track processed matches and to name
    rendered output files.
    """
    home = fixture["home"].replace(" ", "")
    away = fixture["away"].replace(" ", "")
    date_str = fixture["kickoff"].strftime("%Y-%m-%d")
    return f"{home}_{away}_{date_str}"
