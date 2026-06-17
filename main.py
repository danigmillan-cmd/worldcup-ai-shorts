#!/usr/bin/env python3
"""
main.py
World Cup AI Shorts — single-command automation pipeline.

Usage:
    python main.py                   # fetch rankings → render → upload (default)
    python main.py --no-upload       # fetch + render only, skip upload
    python main.py --private         # upload as private (review before publishing)
    python main.py --unlisted        # upload as unlisted
    python main.py --skip-fetch      # skip live ELO fetch, use offline fallback
    python main.py --render-only     # render with offline data, no upload
    python main.py --upload-only     # upload existing output MP4, skip render
    python main.py --type power_ranking   # explicit content type (default)
    python main.py match Spain Brazil          # AI Match Prediction Short
    python main.py match Spain Brazil --no-upload
    python main.py group A                      # Group Qualification Prediction Short
    python main.py group A --no-upload
    python main.py update_fixtures             # fetch latest fixtures.json
    python main.py matches_today                # generate/upload due matches
    python main.py auto_matches                 # update fixtures + generate/upload (hourly task)
    python main.py weekly_report                # YouTube Analytics weekly report (weekly task)

Future content types (--type):
    power_ranking     — top-10 teams by Elo win probability  [implemented]
    match_prediction  — head-to-head match probability        [implemented, via `match` subcommand]
    group_prediction  — group standings + qualification odds  [implemented, via `group` subcommand]
    knockout          — bracket simulation                     [planned]
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime

import config   # side-effect: configures Windows UTF-8 console
import rankings
import renderer
import uploader
import match_cli
import group_cli
import batch_generator
import fixtures_fetcher
import weekly_report


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════
def run_pipeline(
    content_type: str  = "power_ranking",
    output_path:  Path | None = None,
    privacy:      str  = "public",
    upload:       bool = True,
    skip_fetch:   bool = False,
    skip_render:  bool = False,
) -> dict:
    """
    Full end-to-end pipeline: rankings → render → upload.

    Args:
        content_type : content format to generate (see config.CONTENT_TYPES)
        output_path  : override default output MP4 path
        privacy      : "public" | "private" | "unlisted"
        upload       : whether to upload to YouTube after rendering
        skip_fetch   : use offline fallback instead of live ELO data
        skip_render  : skip rendering and upload the existing output file

    Returns:
        {
            "ranking":     list[dict] | None,
            "video_path":  Path,
            "video_id":    str | None,
            "youtube_url": str | None,
        }
    """
    if content_type not in config.CONTENT_TYPES:
        print(f"\nERROR: Unknown content type '{content_type}'")
        print(f"Available types: {list(config.CONTENT_TYPES)}")
        sys.exit(1)

    out = output_path or config.CONTENT_TYPES[content_type]["output"]
    result = {
        "ranking":     None,
        "video_path":  out,
        "video_id":    None,
        "youtube_url": None,
    }

    # ── Step 1: Rankings ──────────────────────────────────────────────────────
    if not skip_render:
        _section("STEP 1 / 3  —  RANKINGS")

        if skip_fetch:
            print("  Offline mode — using fallback data")
            raw    = rankings.FALLBACK_TOP10
            mapped = [
                {"rank": i+1, "name": rankings.ELO_MAP[n][0],
                 "code": rankings.ELO_MAP[n][1], "elo": e, "pct": 0}
                for i, (n, e) in enumerate(raw)
            ]
            probs = rankings.elo_to_probabilities([t["elo"] for t in mapped])
            for t, p in zip(mapped, probs):
                t["pct"] = max(1, round(p))
            result["ranking"] = mapped
        else:
            result["ranking"] = rankings.get_top10()

    # ── Step 2: Render ────────────────────────────────────────────────────────
    if not skip_render:
        _section("STEP 2 / 3  —  RENDER")

        if content_type == "power_ranking":
            result["video_path"] = renderer.render_power_ranking(
                result["ranking"], output_path
            )
        else:
            # Placeholder for future content types
            print(f"  Renderer for '{content_type}' is not yet implemented.")
            sys.exit(1)

        print(f"\n  Video ready : {result['video_path']}")

    else:
        _section("STEP 2 / 3  —  RENDER  (skipped)")
        if not out.exists():
            print(f"\n  ERROR: {out} does not exist.")
            print("  Run without --upload-only first to generate the video.")
            sys.exit(1)
        print(f"  Using existing file: {out}")

    # ── Step 3: Upload ────────────────────────────────────────────────────────
    if upload:
        _section("STEP 3 / 3  —  UPLOAD TO YOUTUBE")
        print("  Authenticating with YouTube...")
        yt = uploader.get_upload_client()
        print()

        video_id = uploader.upload_video(
            yt,
            video_path = result["video_path"],
            privacy    = privacy,
        )
        result["video_id"]    = video_id
        result["youtube_url"] = f"https://www.youtube.com/shorts/{video_id}"

        _section("DONE")
        print(f"  Video ID    : {video_id}")
        print(f"  Short URL   : {result['youtube_url']}")
        print(f"  Watch URL   : https://www.youtube.com/watch?v={video_id}")
        print(f"  Studio      : https://studio.youtube.com/video/{video_id}/edit")

    else:
        _section("DONE  (no upload)")
        print(f"  Video saved : {result['video_path']}")

    print()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════
def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python main.py",
        description="World Cup AI Shorts — automated pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py                   # full pipeline\n"
            "  python main.py --no-upload       # render only\n"
            "  python main.py --private         # upload as private\n"
            "  python main.py --upload-only     # upload existing video\n"
            "  python main.py --skip-fetch      # use offline fallback data\n"
        ),
    )
    p.add_argument(
        "--type",
        default="power_ranking",
        choices=list(config.CONTENT_TYPES),
        metavar="TYPE",
        help=f"Content type to generate. Available: {list(config.CONTENT_TYPES)}",
    )
    p.add_argument("--private",     action="store_true", help="Upload as private")
    p.add_argument("--unlisted",    action="store_true", help="Upload as unlisted")
    p.add_argument("--no-upload",   action="store_true", help="Skip YouTube upload")
    p.add_argument("--skip-fetch",  action="store_true",
                   help="Skip live ELO fetch, use offline fallback")
    p.add_argument("--render-only", action="store_true",
                   help="Fetch + render only, same as --no-upload")
    p.add_argument("--upload-only", action="store_true",
                   help="Skip rendering, upload existing output MP4")
    p.add_argument(
        "--output", type=Path, default=None, metavar="PATH",
        help="Override output MP4 path",
    )

    sub = p.add_subparsers(dest="command")
    match_p = sub.add_parser(
        "match",
        help="AI Match Prediction Short for a single head-to-head matchup",
        description="AI Match Prediction Shorts — head-to-head prediction video",
    )
    match_p.add_argument("team_a", help="First team (English name, e.g. 'Spain')")
    match_p.add_argument("team_b", help="Second team (English name, e.g. 'Brazil')")
    match_p.add_argument("--private",     action="store_true", help="Upload as private")
    match_p.add_argument("--unlisted",    action="store_true", help="Upload as unlisted")
    match_p.add_argument("--no-upload",   action="store_true", help="Skip YouTube upload")
    match_p.add_argument("--render-only", action="store_true",
                          help="Same as --no-upload")
    match_p.add_argument("--upload-only", action="store_true",
                          help="Skip rendering, upload existing output MP4")
    match_p.add_argument(
        "--output", type=Path, default=None, metavar="PATH",
        help="Override output MP4 path",
    )

    group_p = sub.add_parser(
        "group",
        help="Group Qualification Prediction Short for one group (A-L)",
        description=(
            "Simulates a group's remaining fixtures with a Monte Carlo "
            "model, computes top-2 qualification probabilities, and "
            "renders an animated standings/qualification-odds Short."
        ),
    )
    group_p.add_argument("group_letter", help="Group letter, e.g. 'A'")
    group_p.add_argument("--private",     action="store_true", help="Upload as private")
    group_p.add_argument("--unlisted",    action="store_true", help="Upload as unlisted")
    group_p.add_argument("--no-upload",   action="store_true", help="Skip YouTube upload")
    group_p.add_argument("--render-only", action="store_true",
                          help="Same as --no-upload")
    group_p.add_argument("--upload-only", action="store_true",
                          help="Skip rendering, upload existing output MP4")
    group_p.add_argument(
        "--output", type=Path, default=None, metavar="PATH",
        help="Override output MP4 path",
    )

    batch_p = sub.add_parser(
        "matches_today",
        help="Generate + upload Shorts for all fixtures kicking off soon",
        description=(
            "Reads data/fixtures.json, finds matches kicking off within "
            "the next --window hours that haven't been uploaded yet "
            "(data/processed_matches.json), then renders and uploads an "
            "AI Match Prediction Short for each one."
        ),
    )
    batch_p.add_argument("--private",   action="store_true", help="Upload as private")
    batch_p.add_argument("--unlisted",  action="store_true", help="Upload as unlisted")
    batch_p.add_argument("--no-upload", action="store_true",
                          help="Render only, skip YouTube upload (matches stay unprocessed)")
    batch_p.add_argument(
        "--window", type=float, default=config.BATCH_WINDOW_HOURS, metavar="HOURS",
        help=f"Look-ahead window in hours (default: {config.BATCH_WINDOW_HOURS})",
    )

    fetch_p = sub.add_parser(
        "update_fixtures",
        help="Fetch upcoming World Cup fixtures and update data/fixtures.json",
        description=(
            "Fetches upcoming World Cup fixtures from ESPN and overwrites "
            "data/fixtures.json, which the scheduler/batch pipeline reads from."
        ),
    )
    fetch_p.add_argument(
        "--days", type=float, default=config.FIXTURES_FETCH_DAYS_AHEAD, metavar="DAYS",
        help=f"Look-ahead window in days (default: {config.FIXTURES_FETCH_DAYS_AHEAD})",
    )

    auto_p = sub.add_parser(
        "auto_matches",
        help="Full automation cycle: update fixtures, then generate/upload due Shorts",
        description=(
            "One-shot automation entrypoint, intended for Windows Task "
            "Scheduler running this every hour: updates data/fixtures.json "
            "from the live source, then generates and uploads Shorts for "
            "any fixture kicking off within --window hours that hasn't "
            "been uploaded yet. Safe to run repeatedly — fully idempotent "
            "and timing-independent."
        ),
    )
    auto_p.add_argument("--private",   action="store_true", help="Upload as private")
    auto_p.add_argument("--unlisted",  action="store_true", help="Upload as unlisted")
    auto_p.add_argument("--no-upload", action="store_true",
                         help="Render only, skip YouTube upload (matches stay unprocessed)")
    auto_p.add_argument(
        "--window", type=float, default=config.BATCH_WINDOW_HOURS, metavar="HOURS",
        help=f"Look-ahead window in hours (default: {config.BATCH_WINDOW_HOURS})",
    )
    auto_p.add_argument(
        "--days", type=float, default=config.FIXTURES_FETCH_DAYS_AHEAD, metavar="DAYS",
        help=f"Fixture fetch look-ahead in days (default: {config.FIXTURES_FETCH_DAYS_AHEAD})",
    )

    report_p = sub.add_parser(
        "weekly_report",
        help="Fetch YouTube Analytics and write the weekly channel report",
        description=(
            "Queries the YouTube Analytics API for the last reporting "
            "window (ending a few days back, to respect the ~2-3 day "
            "Analytics ingestion delay), appends the snapshot to "
            "data/analytics_history.json, and writes a Markdown report "
            "with week-over-week comparisons and rule-based improvement "
            "points to reports/weekly_report_<date>.md. Intended for a "
            "weekly Task Scheduler run."
        ),
    )
    report_p.add_argument(
        "--window", type=int, default=config.REPORT_WINDOW_DAYS, metavar="DAYS",
        help=f"Reporting window length in days (default: {config.REPORT_WINDOW_DAYS})",
    )
    report_p.add_argument(
        "--lag", type=int, default=config.ANALYTICS_LAG_DAYS, metavar="DAYS",
        help=f"Days before today the window ends (default: {config.ANALYTICS_LAG_DAYS})",
    )
    report_p.add_argument(
        "--no-ai", action="store_true",
        help="Skip the Claude Code CLI 'AI Analysis' section (heuristics only)",
    )

    return p


def main() -> None:
    args = _build_parser().parse_args()

    print()
    print("=" * 60)
    print("  World Cup AI Shorts  |  Automated Pipeline")
    print(f"  {datetime.now().strftime('%Y-%m-%d  %H:%M')}")
    print("=" * 60)

    privacy = "public"
    if args.private:
        privacy = "private"
    elif args.unlisted:
        privacy = "unlisted"

    no_upload   = args.no_upload or args.render_only
    skip_render = args.upload_only

    if args.command == "match":
        match_cli.run_match_pipeline(
            team_a      = args.team_a,
            team_b      = args.team_b,
            output_path = args.output,
            privacy     = privacy,
            upload      = not no_upload,
            skip_render = skip_render,
        )
        return

    if args.command == "group":
        group_cli.run_group_pipeline(
            group_letter = args.group_letter,
            output_path  = args.output,
            privacy      = privacy,
            upload       = not no_upload,
            skip_render  = skip_render,
        )
        return

    if args.command == "matches_today":
        batch_generator.run_batch(
            upload       = not no_upload,
            privacy      = privacy,
            window_hours = args.window,
        )
        return

    if args.command == "update_fixtures":
        fixtures_fetcher.update_fixtures_file(days_ahead=args.days)
        return

    if args.command == "weekly_report":
        weekly_report.run_weekly_report(
            window_days = args.window,
            lag_days    = args.lag,
            ai          = not args.no_ai,
        )
        return

    if args.command == "auto_matches":
        batch_generator.run_automation_cycle(
            upload           = not no_upload,
            privacy          = privacy,
            window_hours     = args.window,
            fetch_days_ahead = args.days,
        )
        return

    run_pipeline(
        content_type = args.type,
        output_path  = args.output,
        privacy      = privacy,
        upload       = not no_upload,
        skip_fetch   = args.skip_fetch,
        skip_render  = skip_render,
    )


if __name__ == "__main__":
    main()
