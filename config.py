"""
config.py
Central configuration for the World Cup AI Shorts system.
All paths, dimensions, colors, timing, and upload settings live here.
"""
import sys
from pathlib import Path

# ─── Windows UTF-8 console fix (applied on import) ───────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent
ASSETS      = ROOT / "assets"
FLAGS_DIR   = ASSETS / "flags"
MUSIC_DIR   = ASSETS / "music"
BG_DIR      = ASSETS / "backgrounds"
OUTPUT_DIR  = ROOT / "output"
CREDS_DIR   = ROOT / "credentials"
SCRIPTS_DIR = ROOT / "scripts"
DATA_DIR    = ROOT / "data"

# ─── Batch pipeline (fixtures / processed-match tracking) ────────────────────
FIXTURES_FILE          = DATA_DIR / "fixtures.json"
PROCESSED_MATCHES_FILE = DATA_DIR / "processed_matches.json"
BATCH_WINDOW_HOURS     = 24   # generate Shorts for matches kicking off within this window

# ─── Elo source audit (rankings.py) ──────────────────────────────────────────
# Records which source (eloratings.net / Wikipedia / fallback) was used on
# the last refresh, plus a timestamp and how many ELO_MAP teams resolved —
# so a silent fall-back to offline data can be spotted after the fact.
ELO_SOURCE_FILE = DATA_DIR / "elo_source.json"

# ─── Fixtures fetcher ─────────────────────────────────────────────────────────
FIXTURES_FETCH_DAYS_AHEAD = 14   # how far ahead to look when fetching fixtures

# ─── Video ────────────────────────────────────────────────────────────────────
VIDEO_W   = 1080
VIDEO_H   = 1920
VIDEO_FPS = 30

# ─── Animated background (Phase 1 — "living canvas") ─────────────────────────
# ANIMATED_BACKGROUND=True draws a subtle procedural "living data" layer
# (breathing pass-network, rising bokeh particles) between the background
# plate and the content overlays, via utils.build_living_layout /
# utils.draw_living_background.
# Camera motion stays the plain utils.apply_zoom for all renderers (the
# eased zoom+pan "living canvas" camera move was tried and reverted).
# ANIMATED_BACKGROUND=False disables the living-data layer (zero regression).
ANIMATED_BACKGROUND = True

# ─── Call-to-action overlay (rotating, shown only in the final stretch) ──────
# A small rounded "pill" with a growth CTA, faded/risen in over the last
# CTA_LEAD_S seconds of every Short (utils.next_cta / utils.draw_cta). The
# messages ROTATE one-per-render (not random): utils.next_cta() cycles through
# CTA_MESSAGES in order, persisting the next index in CTA_INDEX_FILE (same
# pattern as utils.next_match_music). Called ONCE per render in each renderer's
# _make_frame_fn, never per frame. On-screen text only — no emoji (the system
# fonts render emoji as "tofu" boxes); keep emoji for the YouTube metadata.
CTA_ENABLED    = True
CTA_LEAD_S     = 2.0    # seconds before the end when the CTA fades in
CTA_FADE_S     = 0.4    # fade-in / rise duration
FS_CTA         = 34
CTA_INDEX_FILE = DATA_DIR / "cta_index.json"   # persisted rotation counter
CTA_MESSAGES   = [
    "FOLLOW FOR DAILY PREDICTIONS",
    "WHO WINS? COMMENT BELOW",
    "SUBSCRIBE FOR MORE",
    "AGREE? DROP A COMMENT",
    "FOLLOW THE ROAD TO 2026",
    "TAP FOLLOW FOR MORE",
]
# Per-format placement for the CTA pill — each format leaves a different free
# band, so the shared utils.draw_cta() takes the y (and optional max_width) per
# renderer. Power Ranking is intentionally excluded: its 10-row countdown +
# disclaimer + footer fill the whole vertical safe area, leaving no clean band
# for a pill (a CTA there would cover the #10 row), so renderer.py draws none.
#
# Match: inside the central reveal panel (MATCH_PANEL_CENTER, 540 px wide),
# just below the winner flag + "WINNER {name}"/"DRAW" label. MATCH_CTA_MAXW
# auto-shrinks longer messages so the pill never overflows the panel.
MATCH_CTA_Y    = 1095   # match_prediction: in-panel, below the winner flag/label
MATCH_CTA_MAXW = 500    # max pill width inside the 540 px center panel
GROUP_CTA_Y    = 1600   # group_prediction: open space below the AI insight

# ─── Layout — mobile-safe margins ─────────────────────────────────────────────
#
# Safe area: x ∈ [62, 1016]  (64 px on each side)
#            y ∈ [350, 1720] (200 px free at bottom for TikTok/Reels UI)
#
# Horizontal distribution (960 px usable):
#   Rank   62–128  (66 px)
#   Name  140–352  (212 px)
#   Bar   360–820  (460 px)
#   Pct   828–896  (68 px)
#   Flag  904–1016 (112 × 84 px)
#
ROWS_Y0  = 350    # top of first row slot
ROW_H    = 126    # slot height
ROW_GAP  = 12     # gap between slots
ROW_STEP = ROW_H + ROW_GAP   # 138

RANK_X   = 62
NAME_X   = 140
BAR_X    = 360
BAR_MAXW = 460
BAR_H    = 24
BAR_R    = 12
PCT_X    = 828
FLAG_X   = 904
FLAG_W   = 112
FLAG_H   = 84

# ─── Colors ───────────────────────────────────────────────────────────────────
C_WHITE      = (255, 255, 255)
C_CYAN       = (80,  220, 200)
C_GOLD       = (255, 215,  30)
C_BAR_GREEN  = (40,  210,  90)   # default bar color (rank 4–10)
C_BAR_GLOW   = (60,  240, 120)   # glow overlay
C_GOLD_BAR   = (255, 200,  30)   # rank #1
C_SILVER_BAR = (192, 200, 215)   # rank #2
C_BRONZE_BAR = (200, 120,  40)   # rank #3

# ─── Font sizes ───────────────────────────────────────────────────────────────
FS_RANK       = 44    # rank numbers (#1, #10)
FS_NAME       = 34    # country name
FS_PCT        = 38    # percentage counter
FS_SUB        = 40    # subtitle
FS_FOOTER     = 30    # footer label
FS_DISCLAIMER = 22    # small "provisional bracket" disclaimer line

# ─── Audio ────────────────────────────────────────────────────────────────────
SAMPLE_RATE = 44100
MUSIC_FILE  = MUSIC_DIR / "power-rankings.mp3"

# ─── Animation timing ────────────────────────────────────────────────────────
INTRO_T   = 0.6    # seconds before first team appears
SLOT_T    = 1.45   # time budget per team
OUTRO_PAD = 1.0    # seconds held after rank #1 fully reveals

# ─── Asset files ─────────────────────────────────────────────────────────────
POWER_RANKING_BG     = BG_DIR    / "power_ranking_bg.png"
POWER_RANKING_OUTPUT = OUTPUT_DIR / "worldcup_power_ranking_1.mp4"

# ─── Power Ranking: labels ────────────────────────────────────────────────────
# Shown when renderer.render_power_ranking() successfully sources top-10 from
# tournament_simulator.get_tournament_odds() — an honest "probability of
# winning the whole tournament" (Monte Carlo over thousands of simulated
# tournaments), NOT a normalized top-10 split (the top-10 %'s do not sum to
# 100; the rest belongs to the other 38 teams).
POWER_RANKING_TITLE_LABEL = "AI WORLD CUP WINNER ODDS"

# Small on-screen disclaimer shown alongside POWER_RANKING_TITLE_LABEL — the
# 2026 draw doesn't exist yet, so the knockout bracket used by the simulator
# is a plausible seeded approximation (see tournament_simulator.py docstring).
POWER_RANKING_DISCLAIMER = "Provisional bracket - draw pending"

# Fallback label used if get_tournament_odds() fails and the Power Ranking
# falls back to the original Elo-normalized top-10 (renderer.py [WARN]).
POWER_RANKING_FALLBACK_LABEL = "AI POWER RANKING"

# ─── YouTube OAuth ────────────────────────────────────────────────────────────
SCOPES_UPLOAD = ["https://www.googleapis.com/auth/youtube.upload"]
SCOPES_MANAGE = ["https://www.googleapis.com/auth/youtube"]
SCOPES_ANALYTICS = [
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
]
TOKEN_UPLOAD    = CREDS_DIR / "token.json"
TOKEN_MANAGE    = CREDS_DIR / "token_manage.json"
TOKEN_ANALYTICS = CREDS_DIR / "token_analytics.json"

# ─── Weekly analytics report ─────────────────────────────────────────────────
REPORTS_DIR            = ROOT / "reports"
ANALYTICS_HISTORY_FILE = DATA_DIR / "analytics_history.json"
REPORT_WINDOW_DAYS     = 7   # length of the reporting window (days, inclusive)
ANALYTICS_LAG_DAYS     = 3   # YouTube Analytics data lags ~2-3 days behind real time
ANALYTICS_MAX_VIDEOS   = 50  # per-video rows fetched per snapshot
REPORT_AI_TIMEOUT_S    = 300 # max seconds to wait for the Claude Code CLI analysis

# ─── Per-video upload attributes ledger (data/video_attributes.json) ─────────
# Captured at upload-confirmation time (batch_generator.run_batch) and joined
# against analytics in weekly_report.py to correlate "what we shipped" with
# "how it performed". Purely a reporting side-channel — never used for dedup
# (that's processed_matches.json) or to drive renderer/upload behavior.
VIDEO_ATTRIBUTES_FILE = DATA_DIR / "video_attributes.json"

# ─── Analytics insight-loop sample-size gate ─────────────────────────────────
# The weekly "AI Analysis" section only proposes concrete recommendations once
# the channel has enough data to support them. Below either threshold it must
# emit a "MUESTRA INSUFICIENTE" section (observations only, no advice).
MIN_VIDEOS_FOR_INSIGHTS = 15   # total videos with analytics activity in the snapshot
MIN_DAYS_FOR_INSIGHTS   = 7    # days of accumulated data since the first upload

# ─── YouTube metadata ────────────────────────────────────────────────────────
YT_TITLE = "AI Predicts The World Cup Winner \U0001f30d⚽"

YT_DESCRIPTION = """\
AI-powered World Cup 2026 power rankings based on Elo ratings and football analytics.

Which team do you think will win? Drop your prediction in the comments!

#WorldCup #WorldCup2026 #Football #Soccer #AI #PowerRanking #Shorts #FIFA #Sports"""

YT_TAGS = [
    "World Cup", "World Cup 2026", "FIFA", "Football", "Soccer",
    "AI", "Power Ranking", "Elo Rating", "Shorts", "Sports",
    "Predictions", "Analytics",
]

YT_CATEGORY    = "17"            # Sports
YT_PRIVACY     = "public"
YT_CHUNK_BYTES = 4 * 1024 * 1024  # 4 MB per resumable upload chunk

# ─── ELO probability tuning ──────────────────────────────────────────────────
ELO_TEMPERATURE = 100.0   # higher → flatter win-probability spread

# ─── Prediction engine (shared Poisson model, prediction_engine.py) ─────────
# Used by both match_data.py (Match Prediction Shorts) and group_simulator.py
# (group-stage Monte Carlo) so the two content types share one model of
# "how likely is each scoreline" — see prediction_engine.py docstring for the
# full formula.
#
# HOSTS: ELO_MAP *display* names (the uppercase values, not the input keys)
# of the 2026 World Cup host nations. Verified against rankings.ELO_MAP:
# "United States"/"USA" -> "USA", "Mexico" -> "MEXICO", "Canada" -> "CANADA".
HOSTS = {"USA", "MEXICO", "CANADA"}

# Elo bonus added to a host nation's rating before computing expected goals.
# Note: in 2026 the hosts don't play *every* match on home soil, but a flat
# bonus is a cheap, honest first-pass approximation.
HOST_ELO_BONUS = 75

# Average combined goals per international match — the two teams' expected
# goals (lambda_a + lambda_b) sum to this before any Elo-driven skew.
BASE_TOTAL_GOALS = 2.4

# Divisor converting an effective Elo difference into an expected goal
# difference: goal_diff = elo_diff / ELO_TO_GOALS. Smaller = more decisive
# scorelines for a given Elo gap.
ELO_TO_GOALS = 180

# Truncation bound for the Poisson scoreline matrix (P(a=i, b=j) for
# i, j in 0..MAX_GOALS) — the tail mass beyond this is negligible.
MAX_GOALS = 8

# Floor for each team's expected goals (lambda), so extreme Elo gaps never
# produce a zero/negative lambda.
MIN_LAMBDA = 0.15

# HOST_ELO_BONUS / BASE_TOTAL_GOALS / ELO_TO_GOALS calibrated 2026-06-13
# against scripts/calibrate_model.py (see reports/calibration_2026-06-13.md):
# 4538 backtest matches (2010-present), Brier 0.5873 vs 0.7089 for the old
# win%-only heuristic (lower is better), accuracy 51.5% vs 50.0%.

# Display-only softening for the two match-prediction percentage bars
# (match_data.get_match_prediction). Raw p_a/p_b ratios (with the draw
# split 50/50 into each side) can look too extreme for big Elo gaps
# (e.g. 6/94). PCT_DISPLAY_SOFTEN pulls that split toward 50/50:
#   pct_a = 50 + (expected_points_share_a*100 - 50) * PCT_DISPLAY_SOFTEN
# 1.0 = no extra softening, 0.0 = always show 50/50. Purely cosmetic —
# does not affect prediction_engine, the predicted scoreline, or "winner".
PCT_DISPLAY_SOFTEN = 0.7

# ─── Tournament Monte Carlo simulator (tournament_simulator.py) ─────────────
# Number of full-tournament simulations run by simulate_tournament() when the
# cache (data/tournament_odds.json) is stale or missing. Each sim plays out
# all 12 groups + the R32-R16-QF-SF-Final knockout bracket via
# prediction_engine, so cost scales linearly with this value. ~2000 sims take
# ~1.5s on the dev machine, so 10000 (~7.5s) is comfortably viable — see the
# smoke-test timing note in MASTER_CONTEXT.md §3. The result is cached and
# only recomputed when the 48 GROUPS teams' Elo (or GROUPS itself) changes,
# so the hourly auto_matches cycle never pays this cost directly.
N_SIMS_TOURNAMENT = 10000

# Cache for simulate_tournament() output, consumed by
# tournament_simulator.get_tournament_odds(). Keyed by a state-signature
# (hash of the 48 GROUPS teams' Elo + GROUPS structure + N_SIMS_TOURNAMENT +
# TOURNAMENT_ELO_DAMPENING) — a mismatch triggers a recompute.
TOURNAMENT_ODDS_FILE = DATA_DIR / "tournament_odds.json"

# Elo-gap compression applied ONLY inside tournament_simulator (group +
# knockout matches alike) before building match matrices/seeding — does NOT
# affect prediction_engine or the Elo table used by Match Prediction/Group
# Qualification Shorts. tournament_elo = mean_elo + (elo - mean_elo) * factor.
#
# Why: prediction_engine is calibrated for single-match accuracy, where
# e.g. a ~78% win probability for the #1 team vs an average team is
# reasonable. But winning a World Cup means winning ~5-7 of those matches in
# a row, and per-match overconfidence compounds geometrically (0.78^5 ~= 29%,
# 0.78^7 ~= 18% just from the favorable early bracket alone). Real-world
# pre-tournament favorites are usually priced around 12-22% by bookmakers,
# reflecting variance (form, injuries, draws) a clean Poisson model doesn't
# capture. Compressing Elo gaps toward the field average before simulating
# brings the favorite's title_pct back into a realistic range while
# preserving the relative ORDER of contenders (an affine transform of Elo
# doesn't change who's ranked above whom).
# 1.0 = no compression (raw Elo gaps). 0.0 = every team equally likely.
TOURNAMENT_ELO_DAMPENING = 0.5

# ─── Match Prediction: assets ────────────────────────────────────────────────
MATCH_BG     = BG_DIR    / "match_prediction_bg.png"
MATCH_OUTPUT = OUTPUT_DIR / "match_prediction.mp4"

# Background cross-fade: the static plate eases toward the legacy plate
# (assets/backgrounds/match_prediction_bg_legacy.png) over the clip in two
# stages — a faster initial ramp up to BG_CROSSFADE_MID by
# BG_CROSSFADE_BREAKPOINT seconds, then a slower ramp up to BG_CROSSFADE_MAX
# by the end. Only applies to the static background (skipped when an
# AI-generated plate is used).
MATCH_BG_LEGACY         = BG_DIR / "match_prediction_bg_legacy.png"
ENABLE_BG_CROSSFADE     = True
BG_CROSSFADE_BREAKPOINT = 2.0    # seconds — end of the fast initial ramp
BG_CROSSFADE_MID        = 0.40  # blend strength reached at the breakpoint
BG_CROSSFADE_MAX        = 0.65  # max blend strength toward the legacy plate by the end

# Rotating soundtrack: assets/music/match-prediction-0.mp3 .. match-prediction-9.mp3,
# cycled one per render via utils.next_match_music() (counter persisted in
# data/match_music_index.json so consecutive renders pick a different track).
MATCH_MUSIC_COUNT      = 10
MATCH_MUSIC_INDEX_FILE = DATA_DIR / "match_music_index.json"
MATCH_MUSIC_FILE       = MUSIC_DIR / "match-prediction-0.mp3"   # reference track for CONTENT_TYPES

# ─── Match Prediction: timeline (seconds) ────────────────────────────────────
MATCH_T_TITLE    = 0.0
MATCH_T_SUBTITLE = 0.7
MATCH_T_BARS     = 1.2
MATCH_T_REVEAL   = 3.0
MATCH_T_WINNER   = 4.0
MATCH_T_SCORE_CALC = 1.2                           # "calculating" score cycling starts here
MATCH_SCORE_CALC_INTERVAL = 0.08                   # seconds between cycled scoreline digits
MATCH_T_SCORE    = 5.0
MATCH_T_END      = MATCH_T_SCORE + 0.5             # 5.5s — ends shortly after the score reveal
MATCH_OUTRO_PAD  = 0.9                             # extra hold so the predicted score is visible longer
MATCH_DURATION   = MATCH_T_END + MATCH_OUTRO_PAD   # 6.4s

# ─── Match Prediction: layout (mobile-safe, x in [62, 1016]) ─────────────────
MATCH_SUB_Y        = 355   # "AI MATCH PREDICTION" subtitle
MATCH_TITLE_Y      = 420   # title row: flags + "TEAM A VS TEAM B"
MATCH_TITLE_FLAG_W = 132
MATCH_TITLE_FLAG_H = 99

# Cyan panels baked into match_prediction_bg.png: (x0, y0, x1, y1)
MATCH_PANEL_LEFT   = (104, 499, 249, 1225)   # team A vertical probability bar
MATCH_PANEL_CENTER = (270, 499, 810, 1225)   # winner-flag reveal
MATCH_PANEL_RIGHT  = (831, 499, 976, 1225)   # team B vertical probability bar

MATCH_BAR_PAD     = 18    # inner margin for vertical bars within side panels
MATCH_BAR_TOP_PAD = 70    # space reserved at panel top for the % counter

MATCH_SCORE_Y   = 1480

# ─── Match Prediction: colors ────────────────────────────────────────────────
C_TEAM_A      = (80,  170, 255)   # team A bar / accent (blue)
C_TEAM_B      = (255, 100,  70)   # team B bar / accent (red-orange)

# ─── Match Prediction: winner color-grade ────────────────────────────────────
# After the winner reveal (MATCH_T_WINNER), the whole frame eases toward the
# winning team's dominant flag color (utils.flag_dominant_color) via a subtle
# global color blend (utils.tint_image). Draws are left unchanged.
ENABLE_WINNER_COLOR_TINT   = True
MATCH_WINNER_TINT_STRENGTH = 0.18   # max blend strength toward the flag color (0-1)
MATCH_WINNER_TINT_RAMP     = 1.0    # seconds to ease the tint in after MATCH_T_WINNER

# ─── Match Prediction: font sizes ────────────────────────────────────────────
FS_MATCH_TITLE  = 60
FS_MATCH_SUB    = 38
FS_MATCH_PCT    = 46
FS_MATCH_SCORE  = 140
FS_MATCH_WINNER = 40

# ─── Group Prediction: assets ────────────────────────────────────────────────
GROUP_BG         = BG_DIR    / "classification.png"
GROUP_OUTPUT     = OUTPUT_DIR / "group_prediction.mp4"   # generic default (per-group: group_<letter>_prediction.mp4)
GROUP_MUSIC_FILE = MUSIC_DIR / "group_stage.mp3"

# ─── Group Prediction: timeline (seconds) ────────────────────────────────────
GROUP_T_TITLE   = 0.0    # group title fades in
GROUP_T_TABLE   = 1.0    # standings table (names, flags, points) fades in
GROUP_T_BARS    = 2.0    # qualification bars start filling
GROUP_T_COUNT   = 3.5    # bars / percentage counters finish
GROUP_T_GLOW    = 4.5    # subtle audio accent before the AI insight
GROUP_T_INSIGHT = 5.5    # AI insight text fades in
GROUP_T_END     = 7.5    # hold to end
GROUP_DURATION  = GROUP_T_END

GROUP_ROW_STAGGER  = 0.15   # per-row delay for table fade-in / bar fill start
GROUP_BAR_FILL_DUR = 1.3    # per-row bar fill duration

# ─── Group Prediction: layout (within the classification.png glass panel) ────
GROUP_PANEL  = (60, 80, 1020, 1020)   # central glass panel (reference only)
GROUP_TITLE_Y = 130
GROUP_SUB_Y   = 210

GROUP_ROW_Y0   = 290
GROUP_ROW_H    = 160
GROUP_ROW_GAP  = 22
GROUP_ROW_STEP = GROUP_ROW_H + GROUP_ROW_GAP

GROUP_FLAG_X = 100
GROUP_FLAG_W = 92
GROUP_FLAG_H = 64
GROUP_NAME_X = 230
GROUP_PTS_X  = 560
GROUP_BAR_X  = 650
GROUP_BAR_W  = 230
GROUP_BAR_H  = 22
GROUP_PCT_X  = 900

GROUP_INSIGHT_Y = 1060

# ─── Group Prediction: qualification-tier colors (subtle, not neon) ─────────
C_QUAL_HIGH = (90,  200, 120)   # green  — strong qualification chance
C_QUAL_MID  = (235, 195,  80)   # amber  — borderline
C_QUAL_LOW  = (220,  90,  90)   # red    — unlikely

# ─── Group Prediction: font sizes ────────────────────────────────────────────
FS_GROUP_TITLE   = 64
FS_GROUP_SUB     = 28
FS_GROUP_NAME    = 36
FS_GROUP_SMALL   = 22
FS_GROUP_PTS     = 32
FS_GROUP_PCT     = 34
FS_GROUP_INSIGHT = 34

# ─── Extensibility: registered content types ─────────────────────────────────
# New types (knockout, etc.) can be added here and wired
# into renderer.py + main.py without touching the rest of the system.
CONTENT_TYPES = {
    "power_ranking": {
        "description": "Top-10 teams by Elo-based World Cup win probability",
        "output":      POWER_RANKING_OUTPUT,
        "background":  POWER_RANKING_BG,
        "music":       MUSIC_FILE,
    },
    "match_prediction": {
        "description": "Head-to-head AI win probability and score prediction for one match",
        "output":      MATCH_OUTPUT,
        "background":  MATCH_BG,
        "music":       MATCH_MUSIC_FILE,
    },
    "group_prediction": {
        "description": "Group-stage standings, qualification odds and AI insight for one group",
        "output":      GROUP_OUTPUT,
        "background":  GROUP_BG,
        "music":       GROUP_MUSIC_FILE,
    },
    # "knockout": { ... },
}
