"""
uploader.py
YouTube Data API v3 operations: authenticate, upload, delete, query.

Public API:
    get_upload_client()               -> YouTube API client (upload scope)
    get_manage_client()               -> YouTube API client (full scope)
    upload_video(yt, path, ...)       -> video_id (str)
    delete_video(yt, video_id)        -> bool
    get_video_info(yt, video_id)      -> dict | None
"""
import sys
import time
import random
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

import config
import utils

MAX_RETRIES      = 6
RETRIABLE_STATUS = {500, 502, 503, 504}


# ═══════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════════
def authenticate(token_file: Path, scopes: list[str],
                 api: str = "youtube", version: str = "v3",
                 allow_interactive: bool | None = None) -> object:
    """
    OAuth2 Desktop Application flow.

    - Loads token from token_file if it exists and is valid.
    - Silently refreshes expired tokens.
    - Opens browser for first-time login when no valid token exists.
    - Saves the (new or refreshed) token back to token_file.

    `allow_interactive` controls the browser-login fallback used when no valid
    token exists and the refresh token is missing/expired. Defaults to whether a
    human is attached (stdin is a TTY). Under Task Scheduler there is no TTY, so
    the interactive flow is refused and a RuntimeError is raised instead of
    blocking forever on run_local_server() waiting for a login nobody will
    complete (this is what hung the 01:00 cycle for 4h on 2026-06-17). Callers
    in the unattended pipeline catch this and fall back to render-only, retrying
    the upload next cycle once the token is restored.

    Returns an authenticated googleapiclient service object for the given
    API name/version (defaults to the YouTube Data API v3; pass
    api="youtubeAnalytics", version="v2" for the Analytics API).
    """
    if allow_interactive is None:
        allow_interactive = sys.stdin is not None and sys.stdin.isatty()

    creds: Credentials | None = None

    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), scopes)
        except Exception:
            token_file.unlink(missing_ok=True)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("  Refreshing token...")
            try:
                creds.refresh(Request())
                print("  Token refreshed.")
            except Exception:
                token_file.unlink(missing_ok=True)
                creds = None

        if not creds:
            if not allow_interactive:
                raise RuntimeError(
                    f"No valid YouTube token in {token_file.name} and the refresh "
                    "token is missing/expired. Interactive browser login is "
                    "disabled in unattended mode (no TTY). Re-authorize manually "
                    "by running the pipeline from a terminal, then the scheduled "
                    "cycles will resume. (OAuth 'Testing' apps expire refresh "
                    "tokens every 7 days — publish the app to Production to stop "
                    "this recurring.)"
                )
            secret = utils.find_client_secret()
            print(f"  Credentials : {secret.name}")
            print("  Opening browser for Google login...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(secret), scopes=scopes
            )
            creds = flow.run_local_server(
                port=0, prompt="consent", access_type="offline"
            )

        config.CREDS_DIR.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"  Token saved : {token_file.name}")

    print("  Authenticated.")
    return build(api, version, credentials=creds, cache_discovery=False)


def get_upload_client() -> object:
    """Returns a YouTube client with upload-only scope."""
    return authenticate(config.TOKEN_UPLOAD, config.SCOPES_UPLOAD)


def get_manage_client() -> object:
    """Returns a YouTube client with full management scope (upload + delete + read)."""
    return authenticate(config.TOKEN_MANAGE, config.SCOPES_MANAGE)


# ═══════════════════════════════════════════════════════════════════════════════
# UPLOAD
# ═══════════════════════════════════════════════════════════════════════════════
def upload_video(
    youtube,
    video_path: Path,
    title: str       = config.YT_TITLE,
    description: str = config.YT_DESCRIPTION,
    tags: list | None = None,
    privacy: str     = config.YT_PRIVACY,
) -> str:
    """
    Uploads a video to YouTube using resumable upload with progress display.

    Returns the YouTube video_id on success.
    Raises RuntimeError if the upload fails after MAX_RETRIES attempts.
    """
    tags      = tags or config.YT_TAGS
    size_mb   = video_path.stat().st_size / 1024 / 1024

    print(f"  File       : {video_path.name}  ({size_mb:.1f} MB)")
    print(f"  Title      : {title}")
    print(f"  Privacy    : {privacy}")
    print()

    body = {
        "snippet": {
            "title":           title,
            "description":     description,
            "tags":            tags,
            "categoryId":      config.YT_CATEGORY,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus":           privacy,
            "selfDeclaredMadeForKids": False,
            "madeForKids":             False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=config.YT_CHUNK_BYTES,
    )
    req        = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response   = None
    retry      = 0
    start_time = time.time()

    while response is None:
        try:
            status, response = req.next_chunk()
            if status:
                pct   = int(status.progress() * 100)
                speed = (status.resumable_progress /
                         max(time.time() - start_time, 0.1)) / 1024 / 1024
                done  = int(pct / 5)
                print(f"\r  [{'#'*done}{'-'*(20-done)}] {pct:3d}%  ({speed:.1f} MB/s)",
                      end="", flush=True)
            retry = 0

        except HttpError as exc:
            if exc.resp.status in RETRIABLE_STATUS and retry < MAX_RETRIES:
                wait = (2 ** retry) + random.random()
                print(f"\n  HTTP {exc.resp.status} — retrying in {wait:.1f}s...")
                time.sleep(wait)
                retry += 1
            else:
                raise RuntimeError(
                    f"Upload failed: HTTP {exc.resp.status} — {exc.reason}"
                ) from exc

        except (IOError, TimeoutError) as exc:
            if retry < MAX_RETRIES:
                wait = (2 ** retry) + random.random()
                print(f"\n  Network error — retrying in {wait:.1f}s...")
                time.sleep(wait)
                retry += 1
            else:
                raise RuntimeError(f"Upload failed after {MAX_RETRIES} retries: {exc}") from exc

    elapsed = time.time() - start_time
    print(f"\r  [{'#'*20}] 100%  (completed in {elapsed:.0f}s)")
    return response["id"]


# ═══════════════════════════════════════════════════════════════════════════════
# VIDEO METADATA
# ═══════════════════════════════════════════════════════════════════════════════
def get_video_info(youtube, video_id: str) -> dict | None:
    """
    Fetches title, channel, publish date, and privacy status for a video.
    Returns None if the video is not found or not accessible.
    """
    try:
        resp  = youtube.videos().list(part="snippet,status", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return None
        item = items[0]
        return {
            "id":        video_id,
            "title":     item["snippet"].get("title", ""),
            "channel":   item["snippet"].get("channelTitle", ""),
            "published": item["snippet"].get("publishedAt", "")[:10],
            "privacy":   item["status"].get("privacyStatus", ""),
            "url_short": f"https://www.youtube.com/shorts/{video_id}",
            "url_watch": f"https://www.youtube.com/watch?v={video_id}",
        }
    except HttpError:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# DELETE
# ═══════════════════════════════════════════════════════════════════════════════
def delete_video(youtube, video_id: str) -> bool:
    """
    Permanently deletes a video from YouTube.
    Returns True on success, False on failure.
    Requires a client with SCOPES_MANAGE (not upload-only).
    """
    try:
        youtube.videos().delete(id=video_id).execute()
        return True
    except HttpError as exc:
        status = exc.resp.status
        if status == 403:
            print(f"  Error 403: No permission to delete {video_id}.")
            print("  Make sure the video belongs to your channel.")
        elif status == 404:
            print(f"  Error 404: Video {video_id} not found (already deleted?).")
        else:
            print(f"  HTTP {status}: {exc.reason}")
        return False
