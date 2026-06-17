"""
fixtures_fetcher.py
Retrieves upcoming FIFA World Cup fixtures from ESPN's public scoreboard
API and writes them to data/fixtures.json.

This is the ONLY module that talks to an external fixtures source. The
rest of the pipeline (scheduler, renderer, uploader) reads exclusively
from data/fixtures.json via fixtures.py — see fixtures.py / scheduler.py.

    fixtures_fetcher.py
        ↓
    fixtures.json
        ↓
    scheduler → renderer → uploader

All times are handled as timezone-aware UTC datetimes — never local time.

Public API:
    fetch_fixtures(days_ahead=config.FIXTURES_FETCH_DAYS_AHEAD) -> list[dict]
    update_fixtures_file(path=None, days_ahead=...)             -> list[dict]
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import config
import rankings


# ESPN's public soccer scoreboard endpoint (no auth required).
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"

# ESPN team display names that differ from the canonical names used in
# rankings.ELO_MAP (and therefore in match_key / processed_matches keys).
TEAM_NAME_ALIASES: dict[str, str] = {
    "Korea Republic":      "South Korea",
    "IR Iran":             "Iran",
    "Czechia":             "Czech Republic",
    "Côte d'Ivoire":       "Ivory Coast",
    "USA":                 "United States",
    "Türkiye":             "Turkey",
    "Congo DR":            "DR Congo",
    "Bosnia-Herzegovina":  "Bosnia and Herzegovina",
}


# ═══════════════════════════════════════════════════════════════════════════════
# NORMALIZATION
# ═══════════════════════════════════════════════════════════════════════════════
def _normalize_team_name(espn_name: str) -> str | None:
    """
    Maps an ESPN team display name to the canonical English name used by
    rankings.ELO_MAP (and thus by match_data / scheduler / processed_matches).

    Returns None if the team isn't recognized, so the fixture can be
    skipped rather than feeding an unknown team into the pipeline.
    """
    name = TEAM_NAME_ALIASES.get(espn_name, espn_name)
    if name in rankings.ELO_MAP:
        return name
    return next((k for k in rankings.ELO_MAP if k.lower() == name.lower()), None)


def _parse_kickoff_utc(date_str: str) -> datetime:
    """Parses an ESPN ISO-8601 timestamp (with trailing 'Z') into a
    timezone-aware UTC datetime."""
    if date_str.endswith("Z"):
        date_str = date_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(date_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════════
# FETCH
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_fixtures(days_ahead: float = config.FIXTURES_FETCH_DAYS_AHEAD) -> list[dict]:
    """
    Fetches upcoming World Cup fixtures from ESPN within the next
    `days_ahead` days.

    Returns a list of clean dicts:
        {"home": "Spain", "away": "Brazil", "kickoff_utc": "2026-06-15T02:00:00Z"}

    Only matches that:
      - haven't kicked off yet (kickoff > now, UTC)
      - involve two teams recognized in rankings.ELO_MAP
    are included. Returns [] on any network/parsing failure.
    """
    print("[INFO] Fetching latest World Cup fixtures...")

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)
    params = {"dates": f"{now:%Y%m%d}-{end:%Y%m%d}"}

    try:
        resp = requests.get(ESPN_SCOREBOARD_URL, params=params, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        print(f"[WARN] Failed to fetch fixtures: {exc}")
        return []

    events = payload.get("events", [])
    print(f"[INFO] {len(events)} matches retrieved")

    print("[INFO] Converting kickoff times to UTC...")
    fixtures = []
    skipped = 0
    for event in events:
        try:
            competitors = event["competitions"][0]["competitors"]
            home = next(c for c in competitors if c["homeAway"] == "home")
            away = next(c for c in competitors if c["homeAway"] == "away")

            home_name = _normalize_team_name(home["team"]["displayName"])
            away_name = _normalize_team_name(away["team"]["displayName"])
            if home_name is None or away_name is None:
                skipped += 1
                continue

            kickoff = _parse_kickoff_utc(event["date"])
            if kickoff <= now:
                continue

            fixtures.append({
                "home":        home_name,
                "away":        away_name,
                "kickoff_utc": kickoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
        except (KeyError, IndexError, StopIteration):
            skipped += 1
            continue

    if skipped:
        print(f"[INFO] Skipped {skipped} fixture(s) with unrecognized teams or data")

    fixtures.sort(key=lambda fx: fx["kickoff_utc"])
    return fixtures


# ═══════════════════════════════════════════════════════════════════════════════
# UPDATE fixtures.json
# ═══════════════════════════════════════════════════════════════════════════════
def update_fixtures_file(path: Path | None = None,
                         days_ahead: float = config.FIXTURES_FETCH_DAYS_AHEAD) -> list[dict]:
    """
    Fetches upcoming fixtures and overwrites data/fixtures.json with them.

    If no fixtures are retrieved (network failure or no upcoming matches
    in range), fixtures.json is left untouched.
    """
    fp = path or config.FIXTURES_FILE
    fixtures = fetch_fixtures(days_ahead)

    if not fixtures:
        print("[INFO] No upcoming fixtures retrieved. fixtures.json left unchanged.")
        return []

    fp.parent.mkdir(parents=True, exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(fixtures, f, indent=2, ensure_ascii=False)

    print(f"[INFO] {fp.name} updated successfully")
    return fixtures
