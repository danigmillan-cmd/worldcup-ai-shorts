"""
weekly_report.py
Generates the weekly channel report from YouTube Analytics snapshots.

Pipeline (consumer side of analytics_fetcher.py):

    data/analytics_history.json
        ↓
    build_report_data()   — latest snapshot + week-over-week deltas +
                            content-type breakdown + rule-based insights
        ↓
    format_markdown()     — human-readable report
        ↓
    reports/weekly_report_YYYY-MM-DD.md

`build_report_data()` deliberately returns a plain, JSON-serializable dict:
it is both the input to the Markdown formatter and the payload sent to the
AI analysis step — swap or extend either consumer without touching data
collection. Each video is also joined with its upload-time attributes from
data/video_attributes.json (title template used, upload hour/weekday,
description length, tag count, emoji-in-title, matchup Elo, visual flags),
when that video was uploaded after the ledger existed.

Improvement points come from two layers:
  1. Rule-based heuristics (always available, no external dependencies),
     keyed on Shorts-relevant signals: average view percentage
     (retention/loops), engagement rate, content-type performance,
     traffic sources, publish day.
  2. An optional "AI Analysis" section written by the local Claude Code
     CLI (`claude -p`, covered by the user's Claude subscription — no API
     key or extra billing). Skipped with a [WARN] if the CLI is missing
     or the call fails; the report is always written either way.

Sample-size gate: data["sample"] (see _sample_status) flags whether the
channel has >= config.MIN_VIDEOS_FOR_INSIGHTS videos AND
>= config.MIN_DAYS_FOR_INSIGHTS days of accumulated data. Below either
threshold, the AI Analysis section is an observations-only "MUESTRA
INSUFICIENTE" — no recommendations are produced until there's enough data
(see the task's "golden rule": build the infrastructure now, act later).

Public API:
    run_weekly_report(window_days=..., lag_days=..., ai=True) -> Path | None
    build_report_data(snapshot, prev=None)                    -> dict
    format_markdown(data)                                     -> str
"""
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import config
import analytics_fetcher
import processed_matches
import video_attributes

# Channel-total metrics compared week-over-week, with display labels.
WOW_METRICS = [
    ("views",                  "Views"),
    ("estimatedMinutesWatched", "Watch time (min)"),
    ("likes",                  "Likes"),
    ("comments",               "Comments"),
    ("shares",                 "Shares"),
    ("subscribersGained",      "Subscribers gained"),
]

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday",
             "Friday", "Saturday", "Sunday"]


# ═══════════════════════════════════════════════════════════════════════════════
# VIDEO ↔ CONTENT-TYPE CORRELATION (via processed_matches.json)
# ═══════════════════════════════════════════════════════════════════════════════
def _video_context_map() -> dict[str, dict]:
    """
    Builds video_id -> {"match_key", "content_type"} from
    data/processed_matches.json (video ids extracted from youtube_url).
    """
    ctx = {}
    for key, entry in processed_matches.load().items():
        url = entry.get("youtube_url") or ""
        m = re.search(r"(?:shorts/|watch\?v=)([\w-]+)", url)
        if not m:
            continue
        vp = (entry.get("video_path") or "").lower()
        if "match_prediction" in vp:
            ctype = "match_prediction"
        elif "group" in vp:
            ctype = "group_prediction"
        elif "power_ranking" in vp:
            ctype = "power_ranking"
        else:
            ctype = "other"
        ctx[m.group(1)] = {"match_key": key, "content_type": ctype}
    return ctx


def _video_attributes_map() -> dict[str, dict]:
    """
    video_id -> upload-time attributes from data/video_attributes.json
    (keyed by match_key there; re-keyed here by video_id for a direct
    join against snapshot["videos"]). Empty for videos uploaded before
    this ledger existed, or if the file is missing/corrupt.
    """
    return {
        attrs["video_id"]: attrs
        for attrs in video_attributes.load().values()
        if attrs.get("video_id")
    }


def _infer_content_type(video: dict, ctx: dict[str, dict]) -> str:
    """Content type from processed_matches when known, else from the title."""
    known = ctx.get(video.get("video", ""))
    if known:
        return known["content_type"]
    title = (video.get("title") or "").lower()
    if " vs " in title or "prediction" in title and "group" not in title:
        return "match_prediction"
    if "group" in title:
        return "group_prediction"
    if "ranking" in title or "winner" in title:
        return "power_ranking"
    return "other"


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT DATA
# ═══════════════════════════════════════════════════════════════════════════════
def _sample_status(videos: list[dict], window_end: str) -> dict:
    """
    Evaluates whether there's enough data for the AI Analysis section to
    make recommendations (vs. observations only).

    "Enough" means both:
      - at least config.MIN_VIDEOS_FOR_INSIGHTS videos with activity, and
      - at least config.MIN_DAYS_FOR_INSIGHTS days of accumulated data,
        measured from the earliest video's publish date to the window end.

    A brand-new channel fails both checks by design — see the "golden
    rule" in the task brief: build the infrastructure now, gate
    recommendations until >= 1 week of real data exists.
    """
    total = len(videos)

    pub_dates = []
    for v in videos:
        pub = v.get("published", "")
        if pub:
            try:
                pub_dates.append(datetime.fromisoformat(pub.replace("Z", "+00:00")).date())
            except ValueError:
                pass

    if pub_dates:
        end_date  = datetime.fromisoformat(window_end).date()
        data_days = (end_date - min(pub_dates)).days + 1
    else:
        data_days = 0

    return {
        "total_videos": total,
        "data_days":    data_days,
        "min_videos":   config.MIN_VIDEOS_FOR_INSIGHTS,
        "min_days":     config.MIN_DAYS_FOR_INSIGHTS,
        "insufficient": (total < config.MIN_VIDEOS_FOR_INSIGHTS
                         or data_days < config.MIN_DAYS_FOR_INSIGHTS),
    }


def build_report_data(snapshot: dict, prev: dict | None = None) -> dict:
    """
    Assembles everything the report needs into one JSON-serializable dict:
    channel totals, week-over-week deltas, annotated per-video stats
    (joined with their upload-time attributes from video_attributes.json),
    content-type aggregates, traffic sources, sample-size status, and
    rule-based insights.
    """
    channel = snapshot.get("channel", {})
    ctx        = _video_context_map()
    attrs_map  = _video_attributes_map()

    videos = []
    for v in snapshot.get("videos", []):
        videos.append({
            **v,
            "content_type": _infer_content_type(v, ctx),
            "attributes":   attrs_map.get(v.get("video")),
        })

    # Week-over-week deltas
    deltas = {}
    prev_channel = (prev or {}).get("channel", {})
    for metric, _label in WOW_METRICS:
        cur = float(channel.get(metric, 0) or 0)
        old = float(prev_channel.get(metric, 0) or 0)
        deltas[metric] = {
            "current":  cur,
            "previous": old if prev else None,
            "pct":      ((cur - old) / old * 100) if (prev and old > 0) else None,
        }

    # Content-type aggregates
    by_type: dict[str, dict] = {}
    for v in videos:
        agg = by_type.setdefault(v["content_type"], {
            "count": 0, "views": 0, "retention_sum": 0.0, "likes": 0,
        })
        agg["count"]         += 1
        agg["views"]         += int(v.get("views", 0) or 0)
        agg["retention_sum"] += float(v.get("averageViewPercentage", 0) or 0)
        agg["likes"]         += int(v.get("likes", 0) or 0)
    for agg in by_type.values():
        agg["avg_retention"] = agg["retention_sum"] / agg["count"]
        del agg["retention_sum"]

    data = {
        "window": {"start": snapshot["start"], "end": snapshot["end"]},
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "channel":         channel,
        "deltas":          deltas,
        "videos":          videos,
        "by_content_type": by_type,
        "traffic_sources": snapshot.get("traffic_sources", []),
        "per_day":         snapshot.get("per_day", []),
        "sample":          _sample_status(videos, snapshot["end"]),
    }
    data["insights"] = _build_insights(data)
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# RULE-BASED INSIGHTS
# ═══════════════════════════════════════════════════════════════════════════════
def _build_insights(data: dict) -> list[str]:
    """Derives improvement points from the report data. Each rule degrades
    silently when its inputs are missing (new channel, sparse data)."""
    ins: list[str] = []
    videos  = data["videos"]
    channel = data["channel"]
    views   = float(channel.get("views", 0) or 0)

    if not videos and views == 0:
        ins.append(
            "No video activity recorded in this window. If videos were "
            "uploaded recently, remember Analytics data lags ~2-3 days."
        )
        return ins

    # 1. Week-over-week trend
    d = data["deltas"].get("views", {})
    if d.get("pct") is not None:
        if d["pct"] <= -20:
            ins.append(
                f"Views dropped {abs(d['pct']):.0f}% week-over-week "
                f"({d['previous']:.0f} -> {d['current']:.0f}). Consider raising "
                "upload frequency or refreshing TITLE_TEMPLATES — repeated "
                "patterns lose feed traction over time."
            )
        elif d["pct"] >= 20:
            ins.append(
                f"Views grew {d['pct']:.0f}% week-over-week "
                f"({d['previous']:.0f} -> {d['current']:.0f}). Keep the current "
                "cadence; double down on this week's best-performing format."
            )

    # 2. Retention / looping (avg view % — for Shorts, >100% means loops)
    rets = [float(v.get("averageViewPercentage", 0) or 0)
            for v in videos if v.get("averageViewPercentage")]
    if rets:
        avg_ret = sum(rets) / len(rets)
        if avg_ret < 70:
            ins.append(
                f"Average view percentage is {avg_ret:.0f}% — viewers swipe "
                "away before the reveal. Try moving the score/winner reveal "
                "earlier in the timeline or tightening the first ~1s hook."
            )
        elif avg_ret >= 100:
            ins.append(
                f"Average view percentage is {avg_ret:.0f}% — videos are "
                "looping, which the Shorts feed rewards. The short duration "
                "is working; keep videos under ~8s."
            )

    # 3. Engagement rate
    likes = float(channel.get("likes", 0) or 0)
    if views >= 100:
        eng = likes / views * 100
        if eng < 1.5:
            ins.append(
                f"Engagement rate is {eng:.1f}% (likes/views). Add an explicit "
                "question CTA ('Agree? Drop your score below') in titles/"
                "descriptions or a pinned comment to convert views into "
                "engagement signals."
            )

    # 4. Best/worst content type
    typed = {t: a for t, a in data["by_content_type"].items() if a["count"] > 0}
    if len(typed) >= 2:
        best  = max(typed.items(), key=lambda kv: kv[1]["views"] / kv[1]["count"])
        worst = min(typed.items(), key=lambda kv: kv[1]["views"] / kv[1]["count"])
        b_avg = best[1]["views"] / best[1]["count"]
        w_avg = worst[1]["views"] / worst[1]["count"]
        if w_avg > 0 and b_avg / w_avg >= 1.5:
            ins.append(
                f"'{best[0]}' averages {b_avg:.0f} views/video vs {w_avg:.0f} "
                f"for '{worst[0]}' ({b_avg / w_avg:.1f}x). Shift the mix "
                f"toward '{best[0]}' content."
            )

    # 5. Traffic sources
    traffic = data["traffic_sources"]
    t_total = sum(int(t.get("views", 0) or 0) for t in traffic)
    if t_total >= 100:
        shorts_views = sum(int(t.get("views", 0) or 0) for t in traffic
                           if t.get("insightTrafficSourceType") == "SHORTS")
        share = shorts_views / t_total * 100
        if share < 50:
            ins.append(
                f"Only {share:.0f}% of views come from the Shorts feed — the "
                "algorithm isn't pushing these into the feed yet. A stronger "
                "first frame (bigger flags/title at t=0) and consistent "
                "hashtags can improve feed pickup."
            )

    # 6. Best publish day (needs publish dates and some spread)
    day_views: dict[int, list[int]] = {}
    for v in videos:
        pub = v.get("published", "")
        if pub:
            try:
                wd = datetime.fromisoformat(pub.replace("Z", "+00:00")).weekday()
                day_views.setdefault(wd, []).append(int(v.get("views", 0) or 0))
            except ValueError:
                pass
    if len(day_views) >= 3 and len(videos) >= 5:
        best_wd = max(day_views.items(),
                      key=lambda kv: sum(kv[1]) / len(kv[1]))
        ins.append(
            f"Videos published on {_WEEKDAYS[best_wd[0]]} average "
            f"{sum(best_wd[1]) / len(best_wd[1]):.0f} views — when fixtures "
            "allow flexibility (e.g. group/power-ranking content), prefer "
            "that day."
        )

    # 7. Net subscribers
    gained = float(channel.get("subscribersGained", 0) or 0)
    lost   = float(channel.get("subscribersLost", 0) or 0)
    if gained or lost:
        net = gained - lost
        if net < 0:
            ins.append(
                f"Net subscribers this week: {net:+.0f} ({gained:.0f} gained, "
                f"{lost:.0f} lost). Losing subs usually signals repetitive "
                "content — vary formats across the week."
            )

    if not ins:
        ins.append("No specific issues detected this week — metrics are "
                   "within normal ranges for the current channel size.")
    return ins


# ═══════════════════════════════════════════════════════════════════════════════
# MARKDOWN FORMATTING
# ═══════════════════════════════════════════════════════════════════════════════
def _fmt(value, decimals: int = 0) -> str:
    """Thousands-separated number, '-' for missing."""
    if value is None:
        return "-"
    return f"{float(value):,.{decimals}f}"


def format_markdown(data: dict) -> str:
    """Renders the report data as a Markdown document."""
    w = data["window"]
    lines = [
        f"# Weekly Channel Report — {w['start']} to {w['end']}",
        "",
        f"Generated: {data['generated_at'][:16].replace('T', ' ')} UTC  ",
        f"(Analytics data lags ~{config.ANALYTICS_LAG_DAYS} days; window ends "
        f"{config.ANALYTICS_LAG_DAYS} days before the run date.)",
        "",
    ]

    s = data["sample"]
    if s["insufficient"]:
        lines.append(
            f"_Sample size: {s['total_videos']} video(s), "
            f"{s['data_days']} day(s) of data since the first upload "
            f"(thresholds for recommendations: {s['min_videos']} videos / "
            f"{s['min_days']} days) — AI Analysis below is observations-only._"
        )
        lines.append("")

    lines += [
        "## Channel totals (week-over-week)",
        "",
        "| Metric | This week | Previous week | Change |",
        "|---|---:|---:|---:|",
    ]
    for metric, label in WOW_METRICS:
        d = data["deltas"][metric]
        pct = f"{d['pct']:+.0f}%" if d["pct"] is not None else "-"
        lines.append(f"| {label} | {_fmt(d['current'])} "
                     f"| {_fmt(d['previous'])} | {pct} |")

    ch = data["channel"]
    lines += [
        "",
        f"Average view duration: {_fmt(ch.get('averageViewDuration'), 1)}s — "
        f"average view percentage: {_fmt(ch.get('averageViewPercentage'), 1)}%",
        "",
        "## Videos (by views, this window)",
        "",
    ]

    if data["videos"]:
        lines += [
            "| # | Title | Type | Views | Avg % viewed | Likes | Comments |",
            "|---:|---|---|---:|---:|---:|---:|",
        ]
        for i, v in enumerate(data["videos"], 1):
            lines.append(
                f"| {i} | {v.get('title', v.get('video', '?'))} "
                f"| {v['content_type']} "
                f"| {_fmt(v.get('views'))} "
                f"| {_fmt(v.get('averageViewPercentage'), 1)}% "
                f"| {_fmt(v.get('likes'))} "
                f"| {_fmt(v.get('comments'))} |"
            )
    else:
        lines.append("No per-video activity recorded in this window.")

    by_type = data["by_content_type"]
    if by_type:
        lines += [
            "",
            "## Content-type comparison",
            "",
            "| Type | Videos | Total views | Avg views/video | Avg % viewed |",
            "|---|---:|---:|---:|---:|",
        ]
        for ctype, agg in sorted(by_type.items(),
                                 key=lambda kv: kv[1]["views"], reverse=True):
            lines.append(
                f"| {ctype} | {agg['count']} | {_fmt(agg['views'])} "
                f"| {_fmt(agg['views'] / agg['count'])} "
                f"| {_fmt(agg['avg_retention'], 1)}% |"
            )

    traffic = data["traffic_sources"]
    if traffic:
        lines += ["", "## Traffic sources", "", "| Source | Views |", "|---|---:|"]
        for t in traffic:
            lines.append(f"| {t.get('insightTrafficSourceType', '?')} "
                         f"| {_fmt(t.get('views'))} |")

    lines += ["", "## Improvement points", ""]
    lines += [f"- {i}" for i in data["insights"]]
    lines.append("")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# AI ANALYSIS (Claude Code CLI — subscription-covered, no API key)
# ═══════════════════════════════════════════════════════════════════════════════
# Two prompt variants, selected by data["sample"]["insufficient"]:
#   - SUFFICIENT: full "expert" 4-part format with one concrete experiment.
#   - INSUFFICIENT: observations only, no recommendations — the channel is
#     new and there isn't enough data yet (see _sample_status / the task's
#     "golden rule": build the infrastructure now, gate advice on >=1 week
#     of real data).
_AI_PROMPT_SUFFICIENT = (
    "You are an expert YouTube Shorts / social-media growth analyst for an "
    "automated World Cup 2026 AI predictions channel (content types: match "
    "predictions, power rankings, group qualification odds — 5-8 second "
    "vertical videos, fully automated pipeline). Below is this week's "
    "analytics JSON: channel totals, week-over-week deltas, per-video stats "
    "(views, retention, and impressions/CTR where available), per-video "
    "upload attributes when known (title template used, upload hour/weekday, "
    "description length, tag count, emoji-in-title, the matchup's combined "
    "Elo as a proxy for built-in appeal, and active visual flags like "
    "ANIMATED_BACKGROUND), content-type aggregates, "
    "traffic sources, sample-size status, and rule-based insights already "
    "included in the report.\n"
    "\n"
    "Write the body of a '## AI Analysis' section for a Markdown report, "
    "with EXACTLY these four parts, each as a '### '-level subheading, in "
    "this order:\n"
    "\n"
    "1. Diagnosis — 2-3 lines on what happened this week, in plain terms.\n"
    "2. Hypotheses — up to 3, each citing specific numbers from the JSON "
    "below (no invented figures), about WHY this week looked the way it did.\n"
    "3. Experiment for next week — exactly ONE concrete change: what to "
    "change, on which video(s)/format, which metric validates it, and what "
    "threshold counts as success.\n"
    "4. Do not touch yet — what to deliberately leave alone this week.\n"
    "\n"
    "Hard rules:\n"
    "- Never extrapolate a pattern from only 1-2 videos.\n"
    "- Never claim a weak correlation is causal.\n"
    "- The experiment in part 3 must change exactly ONE variable at a time.\n"
    "\n"
    "Output plain Markdown only. Do not include the '## AI Analysis' heading "
    "itself, any preamble, or code fences around the whole answer.\n"
    "\n"
    "--- ANALYTICS JSON ---\n"
)

_AI_PROMPT_INSUFFICIENT = (
    "You are an expert YouTube Shorts / social-media growth analyst for an "
    "automated World Cup 2026 AI predictions channel (content types: match "
    "predictions, power rankings, group qualification odds — 5-8 second "
    "vertical videos, fully automated pipeline). The channel is new and does "
    "NOT yet have enough data for recommendations — see data.sample below "
    "(total_videos={total}, data_days={days}; thresholds for "
    "recommendations: {min_videos} videos / {min_days} days).\n"
    "\n"
    "Write the body of a '## AI Analysis' section for a Markdown report "
    "containing a single '### MUESTRA INSUFICIENTE' subheading, followed by:\n"
    "- One line stating plainly that the sample is too small/young for "
    "recommendations.\n"
    "- 2-4 neutral OBSERVATIONS only (no advice, no 'try X', no causal "
    "claims) about what the early numbers show, each citing a specific "
    "figure from the JSON below.\n"
    "\n"
    "Hard rules:\n"
    "- Do not propose any experiment or change of any kind.\n"
    "- Do not extrapolate a pattern from only 1-2 videos.\n"
    "- Do not claim a weak correlation is causal.\n"
    "\n"
    "Output plain Markdown only. Do not include the '## AI Analysis' heading "
    "itself, any preamble, or code fences around the whole answer.\n"
    "\n"
    "--- ANALYTICS JSON ---\n"
)


def _generate_ai_analysis(data: dict) -> str | None:
    """
    Generates the AI analysis section by piping the report data into the
    local Claude Code CLI (`claude -p`). Returns the Markdown text, or
    None on any failure (CLI missing, timeout, non-zero exit) — the
    report is written without the section in that case (non-fatal,
    consistent with the unattended-automation conventions).

    Selects the prompt variant based on data["sample"]["insufficient"]
    (see _sample_status): a new/small channel gets the observations-only
    "MUESTRA INSUFICIENTE" prompt instead of the full recommendation format.
    """
    claude_bin = shutil.which("claude")
    if not claude_bin:
        print("[WARN] Claude Code CLI ('claude') not found on PATH. "
              "Skipping AI analysis.")
        return None

    sample = data["sample"]
    if sample["insufficient"]:
        prompt = _AI_PROMPT_INSUFFICIENT.format(
            total=sample["total_videos"], days=sample["data_days"],
            min_videos=sample["min_videos"], min_days=sample["min_days"],
        )
        print(f"[INFO] Sample insufficient ({sample['total_videos']} videos, "
              f"{sample['data_days']} day(s) of data) — using "
              "observations-only AI prompt")
    else:
        prompt = _AI_PROMPT_SUFFICIENT

    print("[INFO] Generating AI analysis via Claude Code CLI...")
    # Prompt + data go through stdin: `claude` resolves to an npm .cmd shim
    # on Windows, and multi-line arguments break cmd.exe's quoting.
    try:
        result = subprocess.run(
            [claude_bin, "-p"],
            input=prompt + json.dumps(data, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.REPORT_AI_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        print(f"[WARN] AI analysis timed out after "
              f"{config.REPORT_AI_TIMEOUT_S}s. Skipping.")
        return None
    except Exception as exc:
        print(f"[WARN] AI analysis failed: {exc}. Skipping.")
        return None

    if result.returncode != 0:
        err = (result.stderr or "").strip().splitlines()
        print(f"[WARN] Claude Code CLI exited with code {result.returncode}"
              f"{': ' + err[-1] if err else ''}. Skipping AI analysis.")
        return None

    text = result.stdout.strip()
    if not text:
        print("[WARN] Claude Code CLI returned empty output. "
              "Skipping AI analysis.")
        return None

    print("[INFO] AI analysis generated")
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def run_weekly_report(window_days: int = config.REPORT_WINDOW_DAYS,
                      lag_days: int = config.ANALYTICS_LAG_DAYS,
                      ai: bool = True) -> Path | None:
    """
    Full weekly-report cycle: fetch analytics snapshot → append to history →
    build report data (with week-over-week comparison) → optionally generate
    the AI analysis section (Claude Code CLI) → write the Markdown report to
    reports/weekly_report_<end-date>.md.

    Returns the report path, or None if authentication failed (non-fatal,
    consistent with the unattended-automation conventions).
    """
    print("[INFO] Starting weekly analytics report...")
    start, end = analytics_fetcher.report_window(window_days, lag_days)

    try:
        analytics = analytics_fetcher.get_analytics_client()
        youtube   = analytics_fetcher.get_data_client()
    except Exception as exc:
        print(f"[WARN] YouTube Analytics authentication failed: {exc}")
        print("[WARN] No report generated this run.")
        return None

    snapshot = analytics_fetcher.fetch_snapshot(analytics, youtube, start, end)
    history  = analytics_fetcher.update_analytics_history(snapshot)

    prevs = [s for s in history if s.get("end", "") < snapshot["end"]]
    prev  = prevs[-1] if prevs else None
    if prev:
        print(f"[INFO] Comparing against previous snapshot "
              f"({prev['start']} -> {prev['end']})")
    else:
        print("[INFO] No previous snapshot — week-over-week columns will be empty")

    data = build_report_data(snapshot, prev)
    report_md = format_markdown(data)

    if ai:
        analysis = _generate_ai_analysis(data)
        if analysis:
            report_md += f"\n## AI Analysis\n\n{analysis}\n"

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = config.REPORTS_DIR / f"weekly_report_{snapshot['end']}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"[INFO] Report written: {report_path}")
    print("[INFO] Weekly report complete")
    return report_path
