"""
scheduler.py
Decides which fixtures are due for Short generation right now.

A fixture is "due" when, in UTC:
    - it has not already been uploaded (processed_matches.is_processed)
    - its kickoff is still in the future (kickoff > now)
    - its kickoff is within the next `window_hours` (kickoff - now <= window)

Public API:
    get_due_matches(all_fixtures, processed=None, now=None,
                    window_hours=config.BATCH_WINDOW_HOURS) -> list[dict]
"""
from datetime import datetime, timedelta, timezone

import config
import fixtures as fixtures_mod
import processed_matches


def get_due_matches(all_fixtures: list[dict],
                    processed: dict | None = None,
                    now: datetime | None = None,
                    window_hours: float = config.BATCH_WINDOW_HOURS) -> list[dict]:
    """
    Filters `all_fixtures` (as returned by fixtures.load_fixtures()) down
    to the ones that should be generated and uploaded now.

    Each returned fixture is a copy of the input dict with an added
    "key" field (see fixtures.match_key).
    """
    now       = now or datetime.now(timezone.utc)
    processed = processed if processed is not None else processed_matches.load()
    window    = timedelta(hours=window_hours)

    # Pass 1: fixtures kicking off in the future, within the window —
    # independent of processed status, and independent of how often this
    # function is called (no reliance on exact execution timing).
    upcoming = []
    for fx in all_fixtures:
        kickoff = fx["kickoff"]
        if kickoff <= now:
            continue
        if kickoff - now > window:
            continue
        upcoming.append(fx)

    print(f"[INFO] {len(upcoming)} upcoming match(es) found")

    # Pass 2: drop the ones already uploaded.
    due = []
    for fx in upcoming:
        key = fixtures_mod.match_key(fx)
        if processed_matches.is_processed(key, processed):
            print(f"[INFO] {fx['home']} vs {fx['away']} already processed. Skipping.")
            continue

        fx_due = dict(fx)
        fx_due["key"] = key
        due.append(fx_due)
        print(f"[INFO] {fx['home']} vs {fx['away']} requires video generation")

    return due
