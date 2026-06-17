"""
video_attributes.py
Local JSON-backed ledger of per-video attributes captured at upload time,
for later correlation with YouTube Analytics performance.

Storage format (data/video_attributes.json), keyed by match_key (same
convention as processed_matches.json):
    {
        "Spain_Brazil_2026-06-15": {
            "video_id":                  "...",
            "youtube_url":               "https://www.youtube.com/shorts/...",
            "content_type":              "match_prediction",
            "duration_s":                6.4,
            "title":                     "...",
            "title_template_index":      2,
            "description_length":        312,
            "tag_count":                 12,
            "title_has_emoji":           true,
            "upload_hour_utc":           14,
            "upload_weekday_utc":        "Wednesday",
            "team_a":                    "Spain",
            "team_b":                    "Brazil",
            "elo_a":                     1900,
            "elo_b":                     1850,
            "elo_sum":                   3750,
            "elo_avg":                   1875.0,
            "animated_background":       true,
            "recorded_at":               "2026-06-15T08:00:00+00:00"
        }
    }

Populated where the upload is confirmed (batch_generator.run_batch,
alongside processed_matches.mark_processed). Purely a reporting
side-channel for weekly_report.py — never used for dedup or to drive
renderer/upload behavior, and a failure here must never fail the upload
that triggered it (see record()).

Public API:
    load(path=None)                              -> dict
    save(data, path=None)                        -> None
    record(key, attributes, data=None, path=None) -> dict
    title_has_emoji(title)                       -> bool
"""
import json
import os
import re
from pathlib import Path

import config

_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "☀-➿"
    "️"
    "]+",
    flags=re.UNICODE,
)


def title_has_emoji(title: str) -> bool:
    """Returns True if `title` contains any emoji characters."""
    return bool(_EMOJI_RE.search(title))


# ═══════════════════════════════════════════════════════════════════════════════
# LOAD / SAVE
# ═══════════════════════════════════════════════════════════════════════════════
def load(path: Path | None = None) -> dict:
    """
    Loads the attributes ledger. Returns {} if the file is missing.

    If the file exists but is corrupt, logs [WARN] and returns {} — the
    next save() rewrites the file from scratch rather than crashing the
    caller (this ledger is non-critical reporting data).
    """
    fp = path or config.VIDEO_ATTRIBUTES_FILE
    if not fp.exists():
        return {}
    try:
        with open(fp, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[WARN] {fp.name} is corrupt ({exc}) — starting fresh")
        return {}


def save(data: dict, path: Path | None = None) -> None:
    """Writes the attributes ledger back to disk atomically (write to a
    temp file, then replace) so an interrupted write can't corrupt it."""
    fp = path or config.VIDEO_ATTRIBUTES_FILE
    fp.parent.mkdir(parents=True, exist_ok=True)
    tmp = fp.with_suffix(fp.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, fp)


# ═══════════════════════════════════════════════════════════════════════════════
# UPDATE
# ═══════════════════════════════════════════════════════════════════════════════
def record(key: str, attributes: dict,
          data: dict | None = None, path: Path | None = None) -> dict:
    """
    Stores `attributes` under `key` and persists immediately.

    Non-fatal by design: any failure (disk error, bad data) is caught,
    logged as [WARN], and swallowed — an upload must never fail because
    of attribute logging.

    Mutates and returns `data` (or a freshly loaded ledger if `data` is
    None) so callers can keep accumulating results across a batch run
    without re-reading the file each time.
    """
    data = data if data is not None else load(path)
    try:
        data[key] = attributes
        save(data, path)
        print(f"[INFO] video_attributes.json updated for {key}")
    except Exception as exc:
        print(f"[WARN] Failed to record video attributes for {key}: {exc}")
    return data
