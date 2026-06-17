#!/usr/bin/env python3
"""
group_cli.py
Standalone CLI for World Cup Group Qualification Prediction Shorts.

Usage:
    python group_cli.py A
    python group_cli.py A --no-upload
    python group_cli.py A --private
"""
import sys
import argparse
from pathlib import Path

import config
import group_data
import group_renderer
import uploader


def run_group_pipeline(group_letter: str,
                       output_path: Path | None = None,
                       privacy: str = "public",
                       upload: bool = True,
                       skip_render: bool = False) -> dict:
    """Runs the full group-prediction pipeline: simulate -> render -> upload."""
    result = {"group": None, "video_path": None, "video_id": None, "youtube_url": None}
    out = output_path or (config.OUTPUT_DIR / f"group_{group_letter.lower()}_prediction.mp4")
    result["video_path"] = out

    if not skip_render:
        _section("STEP 1 / 3 — GROUP SIMULATION")
        group_result = group_data.get_group_prediction(group_letter)
        result["group"] = group_result

        _section("STEP 2 / 3 — RENDER")
        result["video_path"] = group_renderer.render_group_prediction(group_result, output_path)
        print(f"\n  Video ready : {result['video_path']}")
    else:
        _section("STEP 2 / 3 — RENDER (skipped)")
        if not out.exists():
            print(f"\n  ERROR: {out} does not exist.")
            sys.exit(1)
        print(f"  Using existing file: {out}")

    if upload:
        _section("STEP 3 / 3 — UPLOAD TO YOUTUBE")
        print("  Authenticating with YouTube...")
        yt = uploader.get_upload_client()
        print()

        if result["group"] is not None:
            meta = group_data.youtube_metadata(result["group"])
        else:
            meta = {
                "title": config.YT_TITLE,
                "description": config.YT_DESCRIPTION,
                "tags": config.YT_TAGS,
            }

        video_id = uploader.upload_video(
            yt,
            video_path=result["video_path"],
            title=meta["title"],
            description=meta["description"],
            tags=meta["tags"],
            privacy=privacy,
        )
        result["video_id"] = video_id
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


def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python group_cli.py",
        description="World Cup Group Qualification Prediction Shorts",
    )
    p.add_argument("group_letter", help="Group letter, e.g. 'A'")
    p.add_argument("--private", action="store_true", help="Upload as private")
    p.add_argument("--unlisted", action="store_true", help="Upload as unlisted")
    p.add_argument("--no-upload", action="store_true", help="Skip YouTube upload")
    p.add_argument("--render-only", action="store_true", help="Same as --no-upload")
    p.add_argument("--upload-only", action="store_true",
                   help="Skip rendering, upload existing output MP4")
    p.add_argument("--output", type=Path, default=None, metavar="PATH",
                   help="Override output MP4 path")
    return p


def main() -> None:
    args = build_parser().parse_args()

    privacy = "public"
    if args.private:
        privacy = "private"
    elif args.unlisted:
        privacy = "unlisted"

    no_upload = args.no_upload or args.render_only

    run_group_pipeline(
        group_letter=args.group_letter,
        output_path=args.output,
        privacy=privacy,
        upload=not no_upload,
        skip_render=args.upload_only,
    )


if __name__ == "__main__":
    main()
