"""
renderer.py
Animated video renderer for World Cup Shorts.

Generates vertical 1080×1920 MP4 files with animated ranking reveals,
glow effects, podium bar colors, and background music.

Public API:
    render_power_ranking(ranking, output_path=None) -> Path
"""
import math
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw

from moviepy import VideoClip, AudioArrayClip

import config
import utils
import rankings
import tournament_simulator


# ═══════════════════════════════════════════════════════════════════════════════
# TITLE-PROBABILITY RANKING (Monte Carlo, tournament_simulator)
# ═══════════════════════════════════════════════════════════════════════════════
def _build_title_ranking(fallback_ranking: list[dict]) -> tuple[list[dict], bool]:
    """
    Tries to build the Power Ranking top-10 from real World Cup title
    probabilities (tournament_simulator.get_tournament_odds()), sorted by
    descending title_pct. These percentages do NOT sum to 100 — the
    remaining probability mass belongs to the other 38 teams.

    Falls back to `fallback_ranking` (the Elo-normalized top-10 from
    rankings.get_top10()) with a [WARN] if the simulator/cache fails for any
    reason. Returns (ranking, used_title_odds).
    """
    try:
        odds = tournament_simulator.get_tournament_odds()

        display_to_code: dict[str, str] = {}
        for display, code in rankings.ELO_MAP.values():
            display_to_code.setdefault(display, code)

        top = sorted(odds.items(), key=lambda kv: -kv[1]["title_pct"])[:10]
        ranking = [
            {
                "rank": i + 1,
                "name": display,
                "code": display_to_code.get(display, ""),
                "pct":  stats["title_pct"],
            }
            for i, (display, stats) in enumerate(top)
        ]
        return ranking, True
    except Exception as exc:
        print(f"[WARN] get_tournament_odds() failed ({type(exc).__name__}: {exc}) "
              "— Power Ranking falling back to Elo-normalized probabilities")
        return fallback_ranking, False


# ═══════════════════════════════════════════════════════════════════════════════
# BAR COLOR LOGIC
# ═══════════════════════════════════════════════════════════════════════════════
def _bar_color(rank: int) -> tuple:
    """Returns the bar fill color for a given rank (1=gold, 2=silver, 3=bronze)."""
    return {
        1: config.C_GOLD_BAR,
        2: config.C_SILVER_BAR,
        3: config.C_BRONZE_BAR,
    }.get(rank, config.C_BAR_GREEN)


# ═══════════════════════════════════════════════════════════════════════════════
# ANIMATION TIMING
# ═══════════════════════════════════════════════════════════════════════════════
def build_timings(ranking: list[dict]) -> list[dict]:
    """
    Builds the per-team animation schedule.

    Reveal order: rank #10 first → rank #1 last (bottom-to-top on screen).
    screen_idx 0 = rank #1 (top row), screen_idx 9 = rank #10 (bottom row).

    Each timing dict contains timestamps (seconds) for:
        start, bar_start, bar_end, flag_start, flag_end, glow_start, glow_end
    """
    timings = []
    for screen_idx in range(len(ranking)):
        reveal_order = (len(ranking) - 1) - screen_idx
        is_top       = (screen_idx == 0)
        t0           = config.INTRO_T + reveal_order * config.SLOT_T
        bar_dur      = 1.0 if is_top else 0.68   # slower fill for rank #1 (drama)
        timings.append({
            "start":      t0,
            "bar_start":  t0 + 0.16,
            "bar_end":    t0 + 0.16 + bar_dur,
            "flag_start": t0 + 0.16 + bar_dur,
            "flag_end":   t0 + 0.16 + bar_dur + 0.40,
            "glow_start": t0 + 0.16 + bar_dur,
            "glow_end":   t0 + 0.16 + bar_dur + 0.55,
        })
    return timings


def compute_duration(timings: list[dict]) -> float:
    """Video ends OUTRO_PAD seconds after rank #1 fully reveals."""
    return timings[0]["glow_end"] + config.OUTRO_PAD


# ═══════════════════════════════════════════════════════════════════════════════
# BACKGROUND
# ═══════════════════════════════════════════════════════════════════════════════
def _prepare_bg(fonts: dict, label: str, date_str: str, show_disclaimer: bool = False,
                background: Path | None = None, sub_y: int = 295) -> Image.Image:
    bg = Image.open(background or config.POWER_RANKING_BG).convert("RGBA")
    bg = bg.resize((config.VIDEO_W, config.VIDEO_H), Image.LANCZOS)
    d  = ImageDraw.Draw(bg)
    sw  = utils.text_width(fonts["sub"], label)
    sx  = (config.VIDEO_W - sw) // 2
    # Shadow pass then color pass
    d.text((sx + 2, sub_y), label, font=fonts["sub"], fill=(0, 80, 60, 160))
    d.text((sx,     sub_y), label, font=fonts["sub"], fill=(*config.C_CYAN, 220))

    # Prediction date — small, top-right corner, unobtrusive
    date_txt = f"UPDATED {date_str}"
    dtw = utils.text_width(fonts["disclaimer"], date_txt)
    dtx = config.VIDEO_W - 62 - dtw
    dty = 110
    d.text((dtx + 1, dty + 1), date_txt, font=fonts["disclaimer"], fill=(0, 0, 0, 130))
    d.text((dtx,     dty),     date_txt, font=fonts["disclaimer"], fill=(*config.C_WHITE, 180))

    if show_disclaimer:
        disclaimer = config.POWER_RANKING_DISCLAIMER
        dw = utils.text_width(fonts["disclaimer"], disclaimer)
        dx = (config.VIDEO_W - dw) // 2
        dy = config.VIDEO_H - 240
        d.text((dx + 1, dy + 1), disclaimer, font=fonts["disclaimer"], fill=(0, 0, 0, 130))
        d.text((dx,     dy),     disclaimer, font=fonts["disclaimer"], fill=(*config.C_WHITE, 160))

    return bg


# ═══════════════════════════════════════════════════════════════════════════════
# ROW RENDERER
# ═══════════════════════════════════════════════════════════════════════════════
def _row_columns(hband: tuple[int, int] | None) -> dict:
    """Per-row horizontal column geometry (rank / name / bar / pct / flag, plus
    the active-row glow bounds).

    Default (hband=None) reproduces the original full-width layout exactly, so
    the standard Power Ranking is untouched. When `hband=(left, right)` is given
    (the knockout background's glass panel), every element is packed between
    `left` and `right` — rank flush-left, flag flush-right, bar taking the
    slack — so nothing spills outside the panel rectangle.
    """
    if hband is None:
        return {
            "rank_x": config.RANK_X, "name_x": config.NAME_X,
            "bar_x":  config.BAR_X,  "bar_maxw": config.BAR_MAXW,
            "pct_x":  config.PCT_X,  "flag_x": config.FLAG_X,
            "flag_h": config.FLAG_H, "hl_x0": 40, "hl_x1": config.VIDEO_W - 40,
        }
    left, right = hband
    flag_w  = config.FLAG_W
    rank_x  = left
    name_x  = left + 82
    flag_x  = right - flag_w
    pct_x   = flag_x - 92
    bar_x   = name_x + 232
    bar_maxw = max(120, pct_x - 24 - bar_x)
    return {
        "rank_x": rank_x, "name_x": name_x,
        "bar_x":  bar_x,  "bar_maxw": bar_maxw,
        "pct_x":  pct_x,  "flag_x": flag_x,
        "flag_h": config.FLAG_H,
        "hl_x0":  left - 16, "hl_x1": right + 16,
    }


def _draw_row(canvas: Image.Image, idx: int, t: float,
              fonts: dict, flags: dict,
              ranking: list[dict], timings: list[dict], max_pct: int,
              rows_y0: int, row_step: int, cols: dict) -> None:
    """Renders a single ranking row at animation time t."""
    team = ranking[idx]
    tm   = timings[idx]
    cy   = rows_y0 + idx * row_step + config.ROW_H // 2

    if t < tm["start"]:
        return

    # ── Rank number (appears first, fades in fast) ────────────────────────────
    rank_p  = utils.smooth_step(min(1.0, (t - tm["start"]) / 0.18))
    rank_c  = config.C_GOLD if (team["rank"] == 1) else config.C_CYAN

    lyr = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    ld  = ImageDraw.Draw(lyr)
    rh  = utils.text_height(fonts["rank"])
    utils.shadow_text(ld, f"#{team['rank']}", fonts["rank"],
                      cols["rank_x"], cy - rh // 2,
                      fill=(*rank_c, int(255 * rank_p)))
    canvas.alpha_composite(lyr)

    if t < tm["bar_start"]:
        return

    # ── Bar + animated percentage counter ────────────────────────────────────
    bar_p  = utils.ease_out(
        min(1.0, (t - tm["bar_start"]) / (tm["bar_end"] - tm["bar_start"]))
    )
    fill_w = max(0, int(cols["bar_maxw"] * (team["pct"] / max_pct) * bar_p))
    bar_y  = cy - config.BAR_H // 2

    # Glow: continuous breathing while filling, one-time pulse when complete
    if bar_p < 1.0:
        glow = 0.65 + 0.15 * math.sin(t * math.pi * 0.8)
    elif t >= tm["glow_start"]:
        gp   = min(1.0, (t - tm["glow_start"]) / (tm["glow_end"] - tm["glow_start"]))
        glow = math.sin(gp * math.pi) * 0.9
    else:
        glow = 0.0

    utils.glow_bar(canvas, cols["bar_x"], bar_y, fill_w, config.BAR_H,
                   _bar_color(team["rank"]), glow)

    pct_txt = f"{round(team['pct'] * bar_p)}%"
    ph  = utils.text_height(fonts["pct"])
    pl  = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    pd  = ImageDraw.Draw(pl)
    utils.shadow_text(pd, pct_txt, fonts["pct"],
                      cols["pct_x"], cy - ph // 2 - 1, config.C_WHITE)
    canvas.alpha_composite(pl)

    if t < tm["flag_start"]:
        return

    # ── Country name + flag (appear together after bar fills) ─────────────────
    flag_a = utils.smooth_step(
        min(1.0, (t - tm["flag_start"]) / (tm["flag_end"] - tm["flag_start"]))
    )
    nl  = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    nld = ImageDraw.Draw(nl)
    nh  = utils.text_height(fonts["name"])
    utils.shadow_text(nld, team["name"], fonts["name"],
                      cols["name_x"], cy - nh // 2,
                      fill=(*config.C_WHITE, int(255 * flag_a)))
    canvas.alpha_composite(nl)

    flag = flags.get(team["code"])
    if flag and flag_a > 0.01:
        fa      = int(255 * flag_a)
        f2      = flag.copy()
        r, g, b, a = f2.split()
        a       = a.point(lambda v: v * fa // 255)
        f2      = Image.merge("RGBA", (r, g, b, a))
        canvas.paste(f2, (cols["flag_x"], cy - cols["flag_h"] // 2), f2)


def _draw_active_highlight(canvas: Image.Image, idx: int, intensity: float,
                           rows_y0: int, row_step: int, cols: dict) -> None:
    """Subtle green glow behind the currently animating row."""
    if intensity < 0.02:
        return
    from PIL import ImageFilter
    pad   = 6
    row_y = rows_y0 + idx * row_step
    hl_x0, hl_x1 = cols["hl_x0"], cols["hl_x1"]
    w     = hl_x1 - hl_x0
    glow  = Image.new("RGBA", (w, config.ROW_H + 2*pad), (0, 0, 0, 0))
    gd    = ImageDraw.Draw(glow)
    utils.rounded_rect(gd, 0, 0, w, config.ROW_H + 2*pad, 12,
                       (*config.C_BAR_GLOW, int(50 * intensity)))
    glow  = glow.filter(ImageFilter.GaussianBlur(12))
    canvas.paste(glow, (hl_x0, row_y - pad), glow)


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO
# ═══════════════════════════════════════════════════════════════════════════════
def _build_audio(duration: float, timings: list[dict]) -> np.ndarray:
    n = int(config.SAMPLE_RATE * duration)

    music = utils.load_music(duration)
    if music is not None:
        # Fade out the last 2 seconds
        fade_s = int(config.SAMPLE_RATE * 2.0)
        fs     = max(0, n - fade_s)
        ramp   = np.linspace(1.0, 0.0, n - fs, dtype=np.float32)
        music[fs:, 0] *= ramp
        music[fs:, 1] *= ramp
        base = music * 0.75
        print("  Music      : power-rankings.mp3")
    else:
        print("  Music      : not found, using ambient pad fallback")
        base = utils.gen_ambient(duration)

    ticks = np.zeros((n, 2), dtype=np.float32)
    for i, tm in enumerate(timings):
        tick = utils.gen_tick(config.SAMPLE_RATE, impact=(i == 0))
        si   = int(tm["glow_start"] * config.SAMPLE_RATE)
        ei   = min(si + len(tick), n)
        if si < n:
            ticks[si:ei] += tick[:ei - si] * 0.40

    return np.clip(base + ticks, -1.0, 1.0).astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════════════
# FRAME BUILDER CLOSURE
# ═══════════════════════════════════════════════════════════════════════════════
def _make_frame_fn(ranking: list[dict], max_pct: float,
                   timings: list[dict], duration: float,
                   label: str, date_str: str, show_disclaimer: bool,
                   rows_y0: int, row_step: int, cols: dict,
                   background: Path | None = None, sub_y: int = 295):
    """Returns the make_frame(t) callable used by MoviePy VideoClip."""
    fonts = {
        "rank":       utils.load_font(config.FS_RANK,       prefer_impact=True),
        "name":       utils.load_font(config.FS_NAME,       prefer_impact=True),
        "pct":        utils.load_font(config.FS_PCT,        prefer_impact=False),
        "sub":        utils.load_font(config.FS_SUB,        prefer_impact=False),
        "footer":     utils.load_font(config.FS_FOOTER,     prefer_impact=False),
        "disclaimer": utils.load_font(config.FS_DISCLAIMER, prefer_impact=False),
    }
    bg    = _prepare_bg(fonts, label, date_str, show_disclaimer, background, sub_y)
    flags = utils.load_flags(ranking)

    living_layout = None
    if config.ANIMATED_BACKGROUND:
        seed = sum(ord(c) for c in ranking[0]["code"]) * 31 + len(ranking)
        living_layout = utils.build_living_layout(seed)

    def make_frame(t: float) -> np.ndarray:
        canvas = bg.copy()

        if living_layout is not None:
            utils.draw_living_background(canvas, t, living_layout)

        # Highlight the currently animating row
        for idx in range(len(ranking)):
            tm = timings[idx]
            if tm["start"] <= t < tm["glow_end"]:
                prog = min(1.0, (t - tm["start"]) / (tm["glow_end"] - tm["start"]))
                _draw_active_highlight(canvas, idx, math.sin(prog * math.pi) * 0.6,
                                       rows_y0, row_step, cols)

        # Render each row
        for idx in range(len(ranking)):
            _draw_row(canvas, idx, t, fonts, flags, ranking, timings, max_pct,
                      rows_y0, row_step, cols)

        # Footer (within bottom safe area, y < VIDEO_H - 200)
        if t > config.INTRO_T + 1.0:
            fa   = min(1.0, (t - config.INTRO_T - 1.0) / 1.0)
            fl   = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
            fd   = ImageDraw.Draw(fl)
            ftxt = "AI WORLD CUP ANALYTICS"
            fw   = utils.text_width(fonts["footer"], ftxt)
            fd.text(((config.VIDEO_W - fw) // 2, config.VIDEO_H - 205), ftxt,
                    font=fonts["footer"],
                    fill=(*config.C_CYAN, int(160 * fa)))
            canvas.alpha_composite(fl)

        # Slow zoom: 1.0x -> 1.04x over the full duration
        zoom   = 1.0 + 0.04 * (t / duration)
        canvas = utils.apply_zoom(canvas, zoom)
        return np.array(canvas.convert("RGB"))

    return make_frame


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════
def render_power_ranking(ranking: list[dict],
                          output_path: Path | None = None,
                          *,
                          use_title_odds: bool = True,
                          label: str | None = None,
                          show_disclaimer: bool | None = None,
                          background: Path | None = None,
                          sub_y: int = 295,
                          band: tuple[int, int] | None = None,
                          hband: tuple[int, int] | None = None) -> Path:
    """
    Renders the animated power ranking video and saves it as MP4.

    Args:
        ranking        : list of team dicts (each needs "rank", "name", "code",
                         "pct").
                         With use_title_odds=True (default, the weekly Power
                         Ranking) this is a FALLBACK only — the top-10 normally
                         comes from tournament_simulator.get_tournament_odds()
                         (title probabilities that do NOT sum to 100). If that
                         fails, this Elo-normalized `ranking` is used, [WARN].
                         With use_title_odds=False (the knockout ranking) the
                         `ranking` is used VERBATIM — no simulator override.
        output_path    : destination path (default: config.POWER_RANKING_OUTPUT)
        use_title_odds : re-derive the top-10 from tournament_simulator. Set
                         False to render a pre-built ranking as-is.
        label          : subtitle override (defaults per source below).
        show_disclaimer: force the "provisional bracket" disclaimer on/off
                         (defaults per source below).

    Returns:
        Path to the generated MP4 file.
    """
    out = output_path or config.POWER_RANKING_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)

    if use_title_odds:
        ranking, used_title_odds = _build_title_ranking(ranking)
        if used_title_odds:
            auto_label, auto_disc = config.POWER_RANKING_TITLE_LABEL, True
            print("  Source     : Monte Carlo title odds (tournament_simulator)")
        else:
            auto_label, auto_disc = config.POWER_RANKING_FALLBACK_LABEL, False
            print("  Source     : Elo-normalized top-10 (fallback)")
    else:
        # Pre-built ranking (knockout_ranking — odds from the REAL remaining
        # bracket). Used verbatim, and it's the real bracket so no disclaimer.
        auto_label, auto_disc = config.POWER_RANKING_TITLE_LABEL, False
        print("  Source     : pre-built ranking (real remaining bracket)")

    label           = label if label is not None else auto_label
    show_disclaimer = auto_disc if show_disclaimer is None else show_disclaimer

    max_pct  = max(t["pct"] for t in ranking)
    timings  = build_timings(ranking)
    duration = compute_duration(timings)
    date_str = datetime.now(timezone.utc).strftime("%d %b %Y").upper()

    # Vertically center the block of rows within the content band, shrinking
    # the row pitch if the team count wouldn't otherwise fit. Default band is
    # the full safe area [ROWS_Y0, VIDEO_H-200] (a 10-row ranking is unchanged);
    # the knockout background passes its glass-panel band so 8/4-team boards
    # stay inside the panel instead of spilling onto the stadium.
    n_rows   = len(ranking)
    if band is None:
        band_top, band_bottom = config.ROWS_Y0, config.VIDEO_H - 200
        row_step = config.ROW_STEP
    else:
        band_top, band_bottom = band
        row_step = min(config.ROW_STEP, (band_bottom - band_top) // n_rows)
    rows_y0  = int(band_top + max(0, (band_bottom - band_top - n_rows * row_step) / 2))
    cols     = _row_columns(hband)

    print(f"  Resolution : {config.VIDEO_W}x{config.VIDEO_H} @ {config.VIDEO_FPS} fps")
    print(f"  Duration   : {duration:.1f}s")
    print(f"  Date       : {date_str}")
    print(f"  Output     : {out.name}")

    make_frame = _make_frame_fn(ranking, max_pct, timings, duration, label, date_str,
                                show_disclaimer, rows_y0, row_step, cols, background, sub_y)
    clip = VideoClip(make_frame, duration=duration)

    print("  Building audio...")
    audio_arr = _build_audio(duration, timings)
    try:
        clip = clip.with_audio(AudioArrayClip(audio_arr, fps=config.SAMPLE_RATE))
        print("  Audio      : OK")
    except Exception as e:
        print(f"  Audio      : skipped ({e})")

    clip.write_videofile(
        str(out),
        fps=config.VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        ffmpeg_params=["-crf", "20"],
        logger="bar",
    )

    return out
