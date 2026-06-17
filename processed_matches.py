"""
processed_matches.py
Local JSON-backed tracking of fixtures that have already been rendered
and/or uploaded, to prevent duplicate processing.

Storage format (data/processed_matches.json):
    {
        "Spain_Brazil_2026-06-15": {
            "uploaded":    true,
            "youtube_url": "https://www.youtube.com/shorts/...",
            "video_path":  "C:/.../output/match_prediction_Spain_Brazil_2026-06-15.mp4",
            "timestamp":   "2026-06-14T08:00:00+00:00"
        }
    }

Public API:
    load(path=None)                       -> dict
    save(data, path=None)                 -> None
    is_processed(key, data=None)          -> bool
    mark_processed(key, uploaded, ...)    -> dict
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import config


# ═══════════════════════════════════════════════════════════════════════════════
# LOAD / SAVE
# ═══════════════════════════════════════════════════════════════════════════════
def load(path: Path | None = None) -> dict:
    """Loads the processed-matches table. Returns {} if the file is missing."""
    fp = path or config.PROCESSED_MATCHES_FILE
    if not fp.exists():
        return {}
    with open(fp, "r", encoding="utf-8") as f:
        return json.load(f)


def save(data: dict, path: Path | None = None) -> None:
    """Writes the processed-matches table back to disk."""
    fp = path or config.PROCESSED_MATCHES_FILE
    fp.parent.mkdir(parents=True, exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# QUERIES
# ═══════════════════════════════════════════════════════════════════════════════
def is_processed(key: str, data: dict | None = None) -> bool:
    """
    Returns True if `key` has already been successfully uploaded.

    A render-only entry (uploaded=False) does NOT count as processed —
    it will be retried on the next run, since the goal is to avoid
    *duplicate uploads*, not duplicate renders.
    """
    data = data if data is not None else load()
    return bool(data.get(key, {}).get("uploaded", False))


# ═══════════════════════════════════════════════════════════════════════════════
# UPDATE
# ═══════════════════════════════════════════════════════════════════════════════
def mark_processed(key: str,
                   uploaded: bool,
                   youtube_url: str | None = None,
                   video_path: str | None = None,
                   data: dict | None = None,
                   path: Path | None = None) -> dict:
    """
    Records the outcome for `key` and persists it immediately.

    Mutates and returns `data` (or a freshly loaded table if `data` is
    None) so callers can keep accumulating results across a batch run
    without re-reading the file each time.
    """
    data = data if data is not None else load()
    data[key] = {
        "uploaded":    uploaded,
        "youtube_url": youtube_url,
        "video_path":  video_path,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }
    save(data, path)
    return data
