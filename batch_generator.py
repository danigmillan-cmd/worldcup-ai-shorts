"""
batch_generator.py
Batch pipeline for "matches_today": finds fixtures kicking off within the
next BATCH_WINDOW_HOURS, renders an AI Match Prediction Short for each,
uploads them to YouTube, and records them in processed_matches.json so
they are never generated/uploaded twice. On a confirmed upload, also logs
per-video attributes (title template used, upload time, Elo "draw power",
visual flags, etc.) to data/video_attributes.json for weekly_report.py to
correlate against Analytics performance later.

Also provides run_automation_cycle(), the entrypoint for "auto_matches":
fetch fixtures -> run_batch -> done. Designed to be triggered repeatedly
(e.g. hourly via Windows Task Scheduler) without relying on exact timing —
see scheduler.get_due_matches().

Public API:
    run_batch(upload=True, privacy="public",
              window_hours=config.BATCH_WINDOW_HOURS) -> list[dict]
    run_automation_cycle(upload=True, privacy="public",
              window_hours=config.BATCH_WINDOW_HOURS,
              fetch_days_ahead=config.FIXTURES_FETCH_DAYS_AHEAD) -> list[dict]
"""
from datetime import datetime, timezone
from pathlib import Path

import config
import fixtures as fixtures_mod
import fixtures_fetcher
import processed_matches
import rankings
import scheduler
import match_data
import match_renderer
import uploader
import video_attributes


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def _output_path(key: str) -> Path:
    return config.OUTPUT_DIR / f"match_prediction_{key}.mp4"


def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _record_video_attributes(key: str, match: dict, meta: dict,
                             video_id: str, youtube_url: str) -> None:
    """
    Logs per-video attributes to data/video_attributes.json at the moment
    the upload is confirmed, for later correlation with Analytics
    performance (see weekly_report.py). Non-fatal: video_attributes.record
    already catches its own errors, but the attribute dict is built
    defensively here too — a bad attribute must never fail the upload.
    """
    try:
        now = datetime.now(timezone.utc)
        a, b = match["team_a"], match["team_b"]
        video_attributes.record(key, {
            "video_id":                  video_id,
            "youtube_url":               youtube_url,
            "content_type":              "match_prediction",
            "duration_s":                config.MATCH_DURATION,
            "title":                     meta["title"],
            "title_template_index":      meta["title_template_index"],
            "description_length":        len(meta["description"]),
            "tag_count":                 len(meta["tags"]),
            "title_has_emoji":           video_attributes.title_has_emoji(meta["title"]),
            "upload_hour_utc":           now.hour,
            "upload_weekday_utc":        now.strftime("%A"),
            "team_a":                    a["name"],
            "team_b":                    b["name"],
            "elo_a":                     a["elo"],
            "elo_b":                     b["elo"],
            "elo_sum":                   a["elo"] + b["elo"],
            "elo_avg":                   (a["elo"] + b["elo"]) / 2,
            "animated_background":       config.ANIMATED_BACKGROUND,
            "recorded_at":               now.isoformat(),
        })
    except Exception as exc:
        print(f"[WARN] Failed to build video attributes for {key}: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
# BATCH PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════
def run_batch(upload: bool = True,
              privacy: str = "public",
              window_hours: float = config.BATCH_WINDOW_HOURS) -> list[dict]:
    """
    Generates (and optionally uploads) AI Match Prediction Shorts for
    every fixture due within `window_hours`.

    Returns a list of per-match result dicts:
        {
            "key", "fixture", "match",
            "video_path", "video_id", "youtube_url", "error",
        }
    """
    all_fixtures = fixtures_mod.load_fixtures()
    processed    = processed_matches.load()
    due          = scheduler.get_due_matches(all_fixtures, processed, window_hours=window_hours)

    _section("MATCH DETECTION")
    print(f"  Fixtures loaded : {len(all_fixtures)}")
    print(f"  Window          : next {window_hours:.0f}h")
    print(f"  Due for upload  : {len(due)}")

    results: list[dict] = []
    if not due:
        print("\n  Nothing to do.")
        return results

    for fx in due:
        print(f"    - {fx['home']} vs {fx['away']}  (kickoff {fx['kickoff_utc']})")

    print("\n  Fetching Elo ratings...")
    elo_table = rankings.get_elo_table()

    yt = None
    if upload:
        _section("YOUTUBE AUTH")
        print("  Authenticating with YouTube...")
        try:
            yt = uploader.get_upload_client()
        except Exception as exc:
            print(f"  ERROR: YouTube authentication failed: {exc}")
            print("  Continuing in render-only mode for this cycle.")
            upload = False

    for fx in due:
        key = fx["key"]
        result = {
            "key": key, "fixture": fx, "match": None,
            "video_path": None, "video_id": None,
            "youtube_url": None, "error": None,
        }

        _section(f"{fx['home']} vs {fx['away']}  —  {key}")
        try:
            print("[INFO] Generating probabilities...")
            match = match_data.get_match_prediction(fx["home"], fx["away"], elo_table)
            result["match"] = match

            print("[INFO] Rendering video...")
            out = _output_path(key)
            video_path = match_renderer.render_match_prediction(match, out)
            result["video_path"] = video_path
            print(f"\n  Video ready : {video_path}")

            uploaded = False
            if upload:
                print("[INFO] Uploading to YouTube...")
                meta = match_data.youtube_metadata(match)
                video_id = uploader.upload_video(
                    yt,
                    video_path  = video_path,
                    title       = meta["title"],
                    description = meta["description"],
                    tags        = meta["tags"],
                    privacy     = privacy,
                )
                result["video_id"]    = video_id
                result["youtube_url"] = f"https://www.youtube.com/shorts/{video_id}"
                uploaded = True
                print("[INFO] Upload successful")
                print(f"  Uploaded    : {result['youtube_url']}")

                _record_video_attributes(key, match, meta, video_id, result["youtube_url"])

            processed_matches.mark_processed(
                key,
                uploaded    = uploaded,
                youtube_url = result["youtube_url"],
                video_path  = str(video_path),
                data        = processed,
            )
            print("[INFO] Match marked as processed")

        except Exception as exc:
            result["error"] = str(exc)
            print(f"  ERROR: {exc}")

        results.append(result)

    _section("BATCH SUMMARY")
    for r in results:
        status = r["youtube_url"] or ("error: " + r["error"] if r["error"] else "rendered (no upload)")
        print(f"  {r['key']:<30} {status}")
    print()

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# AUTOMATION ENTRYPOINT  ("auto_matches")
# ═══════════════════════════════════════════════════════════════════════════════
def run_automation_cycle(upload: bool = True,
                         privacy: str = "public",
                         window_hours: float = config.BATCH_WINDOW_HOURS,
                         fetch_days_ahead: float = config.FIXTURES_FETCH_DAYS_AHEAD) -> list[dict]:
    """
    Full automation cycle, intended to be triggered repeatedly (e.g. hourly
    via Windows Task Scheduler):

        1. Update fixtures.json from the live source
        2. Detect upcoming matches (kickoff in (now, now + window_hours])
        3. Skip already-uploaded matches
        4. Generate + upload Shorts for the rest
        5. Mark them as processed

    Idempotent and timing-independent: every match still due gets picked up
    regardless of how long it's been since the last run.
    """
    print("[INFO] Starting automation cycle...")

    print("[INFO] Updating fixtures...")
    try:
        fixtures_fetcher.update_fixtures_file(days_ahead=fetch_days_ahead)
    except Exception as exc:
        print(f"[WARN] Fixture update failed: {exc}")
        print("[INFO] Continuing with existing fixtures.json")

    results = run_batch(upload=upload, privacy=privacy, window_hours=window_hours)

    print("[INFO] Automation cycle complete")
    return results
