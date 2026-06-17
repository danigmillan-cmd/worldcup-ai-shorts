"""
analytics_fetcher.py
Retrieves channel- and video-level statistics from the YouTube Analytics
API v2 and stores weekly snapshots in data/analytics_history.json.

This is the ONLY module that talks to the YouTube Analytics API. The
report generator (weekly_report.py) reads exclusively from
data/analytics_history.json — the same decoupling pattern as
fixtures_fetcher.py → fixtures.json → scheduler.

    analytics_fetcher.py
        ↓
    data/analytics_history.json
        ↓
    weekly_report.py  →  reports/weekly_report_YYYY-MM-DD.md

YouTube Analytics data lags ~2-3 days behind real time, so the reporting
window ends config.ANALYTICS_LAG_DAYS days before today (UTC) — querying
up to "today" would return zeros for the most recent days and distort
week-over-week comparisons.

Per-video rows include retention (averageViewDuration,
averageViewPercentage) — the signals that matter most for Shorts
(loop rate).

All dates are UTC.

Public API:
    report_window(window_days=..., lag_days=...)   -> (date, date)
    get_analytics_client()                         -> youtubeAnalytics v2 client
    get_data_client()                              -> youtube v3 client (read-only)
    fetch_snapshot(analytics, youtube, start, end) -> dict
    update_analytics_history(snapshot, path=None)  -> list[dict]
    load_history(path=None)                        -> list[dict]
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from googleapiclient.errors import HttpError

import config
import uploader

CHANNEL_METRICS = (
    "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
    "likes,comments,shares,subscribersGained,subscribersLost"
)
# averageViewDuration / averageViewPercentage are the retention signals that
# matter most for Shorts (loop rate); fetched per-video below.
#
# Note: impressions / impressionsClickThroughRate (Shorts feed reach) were
# evaluated for this per-video query and rejected — the Analytics API v2
# `reports.query` endpoint returns HTTP 400 for those metric names with
# dimensions=video on a channel==MINE report (that data isn't exposed via
# this API, only in YouTube Studio). Retention is fetched here instead.
VIDEO_METRICS = (
    "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
    "likes,comments,shares"
)


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENTS / WINDOW
# ═══════════════════════════════════════════════════════════════════════════════
def get_analytics_client() -> object:
    """Returns a YouTube Analytics API v2 client (read-only scopes)."""
    return uploader.authenticate(
        config.TOKEN_ANALYTICS, config.SCOPES_ANALYTICS,
        api="youtubeAnalytics", version="v2",
    )


def get_data_client() -> object:
    """Returns a YouTube Data API v3 client on the same read-only token
    (used to resolve video titles / publish dates)."""
    return uploader.authenticate(config.TOKEN_ANALYTICS, config.SCOPES_ANALYTICS)


def report_window(window_days: int = config.REPORT_WINDOW_DAYS,
                  lag_days: int = config.ANALYTICS_LAG_DAYS) -> tuple[date, date]:
    """
    Returns the (start, end) dates of the reporting window, both inclusive.
    Ends `lag_days` before today (UTC) to stay clear of the Analytics
    ingestion delay.
    """
    end = datetime.now(timezone.utc).date() - timedelta(days=lag_days)
    start = end - timedelta(days=window_days - 1)
    return start, end


# ═══════════════════════════════════════════════════════════════════════════════
# QUERIES
# ═══════════════════════════════════════════════════════════════════════════════
def _query(analytics, start: date, end: date, metrics: str,
           dimensions: str | None = None, sort: str | None = None,
           max_results: int | None = None) -> list[dict]:
    """
    Runs one Analytics API query and returns rows as a list of dicts keyed
    by column name. Returns [] on any API failure (non-fatal — one failed
    query must not abort the whole snapshot).
    """
    params = {
        "ids":       "channel==MINE",
        "startDate": start.isoformat(),
        "endDate":   end.isoformat(),
        "metrics":   metrics,
    }
    if dimensions:
        params["dimensions"] = dimensions
    if sort:
        params["sort"] = sort
    if max_results:
        params["maxResults"] = max_results

    try:
        resp = analytics.reports().query(**params).execute()
    except HttpError as exc:
        print(f"[WARN] Analytics query failed (dimensions={dimensions}): "
              f"HTTP {exc.resp.status}")
        return []
    except Exception as exc:
        print(f"[WARN] Analytics query failed (dimensions={dimensions}): {exc}")
        return []

    headers = [h["name"] for h in resp.get("columnHeaders", [])]
    return [dict(zip(headers, row)) for row in resp.get("rows") or []]


def _fetch_video_meta(youtube, video_ids: list[str]) -> dict[str, dict]:
    """
    Resolves video_id -> {"title", "published"} via the Data API.
    Returns {} on failure (titles then fall back to the bare video id).
    """
    if not video_ids:
        return {}
    try:
        resp = youtube.videos().list(
            part="snippet", id=",".join(video_ids[:50])
        ).execute()
    except Exception as exc:
        print(f"[WARN] Failed to fetch video titles: {exc}")
        return {}
    return {
        item["id"]: {
            "title":     item["snippet"].get("title", ""),
            "published": item["snippet"].get("publishedAt", ""),
        }
        for item in resp.get("items", [])
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SNAPSHOT
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_snapshot(analytics, youtube, start: date, end: date) -> dict:
    """
    Fetches one full analytics snapshot for [start, end] (both inclusive):

      - channel totals (views, watch time, retention, engagement, subs)
      - per-day views / subscribers gained
      - per-video stats (top config.ANALYTICS_MAX_VIDEOS by views), with
        title + publish date resolved via the Data API
      - traffic-source breakdown

    Individual query failures degrade to empty sections — the snapshot is
    always returned.
    """
    print(f"[INFO] Fetching analytics for {start} -> {end} (UTC)...")

    totals_rows = _query(analytics, start, end, CHANNEL_METRICS)
    channel = totals_rows[0] if totals_rows else {}

    per_day = _query(analytics, start, end, "views,subscribersGained",
                     dimensions="day", sort="day")

    videos = _query(analytics, start, end, VIDEO_METRICS,
                    dimensions="video", sort="-views",
                    max_results=config.ANALYTICS_MAX_VIDEOS)

    meta = _fetch_video_meta(youtube, [v["video"] for v in videos])
    for v in videos:
        info = meta.get(v["video"], {})
        v["title"]     = info.get("title", v["video"])
        v["published"] = info.get("published", "")

    traffic = _query(analytics, start, end, "views",
                     dimensions="insightTrafficSourceType", sort="-views")

    print(f"[INFO] Snapshot: {len(videos)} video(s) with activity, "
          f"{int(channel.get('views', 0))} total view(s)")

    return {
        "start":           start.isoformat(),
        "end":             end.isoformat(),
        "fetched_at":      datetime.now(timezone.utc).isoformat(),
        "channel":         channel,
        "per_day":         per_day,
        "videos":          videos,
        "traffic_sources": traffic,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# HISTORY (data/analytics_history.json)
# ═══════════════════════════════════════════════════════════════════════════════
def load_history(path: Path | None = None) -> list[dict]:
    """Loads the snapshot history. Returns [] if the file is missing."""
    fp = path or config.ANALYTICS_HISTORY_FILE
    if not fp.exists():
        return []
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)


def update_analytics_history(snapshot: dict, path: Path | None = None) -> list[dict]:
    """
    Appends `snapshot` to the history file, replacing any existing snapshot
    with the same [start, end] window (safe to re-run in the same week).
    Returns the full, end-date-sorted history.
    """
    fp = path or config.ANALYTICS_HISTORY_FILE
    history = load_history(fp)
    history = [s for s in history
               if not (s.get("start") == snapshot["start"]
                       and s.get("end") == snapshot["end"])]
    history.append(snapshot)
    history.sort(key=lambda s: s.get("end", ""))

    fp.parent.mkdir(parents=True, exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    print(f"[INFO] {fp.name} updated ({len(history)} snapshot(s))")
    return history
