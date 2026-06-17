"""
group_renderer.py
Animated video renderer for World Cup Group Qualification Prediction Shorts.

Generates a vertical 1080x1920 MP4 for one group: title reveal, animated
standings table (flags, points, qualification bars + percentage counters),
a subtle glow on the top-2 qualifying teams, and an AI insight line.

Renders onto the existing assets/backgrounds/classification.png template —
no new background art is generated.

Public API:
    render_group_prediction(group_result, output_path=None) -> Path
"""
import math
import re
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw

from moviepy import VideoClip, AudioArrayClip

import config
import utils


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "☀-➿"
    "️"
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    """Removes emoji (no glyphs in the system fonts used for on-screen text)."""
    return _EMOJI_RE.sub("", text).strip()


def _qual_color(pct: int) -> tuple:
    """Subtle qualification-tier color: green (high) / amber (mid) / red (low)."""
    if pct >= 60:
        return config.C_QUAL_HIGH
    if pct >= 30:
        return config.C_QUAL_MID
    return config.C_QUAL_LOW


# ═══════════════════════════════════════════════════════════════════════════════
# TITLE — "GROUP A" + "AI QUALIFICATION ODDS"  (0.0s)
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_title(canvas: Image.Image, t: float, fonts: dict, group_letter: str) -> None:
    p = utils.smooth_step(min(1.0, (t - config.GROUP_T_TITLE) / 0.6))
    if p <= 0.01:
        return

    lyr = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    ld  = ImageDraw.Draw(lyr)
    rise = int(16 * (1 - p))

    f   = fonts["title"]
    txt = f"GROUP {group_letter}"
    w   = utils.text_width(f, txt)
    utils.shadow_text(ld, txt, f, (config.VIDEO_W - w) // 2, config.GROUP_TITLE_Y + rise,
                      fill=(*config.C_WHITE, int(255 * p)))

    sf  = fonts["sub"]
    sub = "AI QUALIFICATION ODDS"
    sw  = utils.text_width(sf, sub)
    utils.shadow_text(ld, sub, sf, (config.VIDEO_W - sw) // 2, config.GROUP_SUB_Y + rise,
                      fill=(*config.C_CYAN, int(220 * p)))

    canvas.alpha_composite(lyr)


# ═══════════════════════════════════════════════════════════════════════════════
# STANDINGS ROW — flag, name, GF/GA, points  (1.0s, staggered per row)
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_row(canvas: Image.Image, idx: int, t: float, fonts: dict,
              flags: dict, team: dict) -> None:
    row_start = config.GROUP_T_TABLE + idx * config.GROUP_ROW_STAGGER
    p = utils.smooth_step(min(1.0, max(0.0, (t - row_start) / 0.5)))
    if p <= 0.01:
        return

    cy    = config.GROUP_ROW_Y0 + idx * config.GROUP_ROW_STEP
    alpha = int(255 * p)
    slide = int(28 * (1 - p))

    lyr = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    ld  = ImageDraw.Draw(lyr)

    # Flag
    flag = flags.get(team["code"])
    if flag is not None:
        f2 = flag
        if p < 1.0:
            r, g, b, a = f2.split()
            a = a.point(lambda v, ap=p: int(v * ap))
            f2 = Image.merge("RGBA", (r, g, b, a))
        fy = cy + (config.GROUP_ROW_H - config.GROUP_FLAG_H) // 2
        lyr.alpha_composite(f2, (config.GROUP_FLAG_X - slide, fy))

    # Team name
    name_y = cy + (config.GROUP_ROW_H // 2) - utils.text_height(fonts["name"]) - 4
    utils.shadow_text(ld, team["display"], fonts["name"], config.GROUP_NAME_X - slide, name_y,
                      fill=(*config.C_WHITE, alpha))

    # Secondary GF/GA line
    small_txt = f"GF {team['gf']} · GA {team['ga']}"
    small_y   = cy + (config.GROUP_ROW_H // 2) + 6
    utils.shadow_text(ld, small_txt, fonts["small"], config.GROUP_NAME_X - slide, small_y,
                      fill=(200, 210, 220, int(200 * p)))

    # Points
    pts = team["points"]
    pts_txt = f"{pts} pt" if pts == 1 else f"{pts} pts"
    pf = fonts["pts"]
    pw = utils.text_width(pf, pts_txt)
    pts_y = cy + (config.GROUP_ROW_H - utils.text_height(pf)) // 2
    utils.shadow_text(ld, pts_txt, pf, config.GROUP_PTS_X - pw + slide, pts_y,
                      fill=(*config.C_WHITE, alpha))

    canvas.alpha_composite(lyr)


# ═══════════════════════════════════════════════════════════════════════════════
# QUALIFICATION BAR + PERCENTAGE COUNTER  (2.0s, staggered per row)
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_bar(canvas: Image.Image, idx: int, t: float, fonts: dict, team: dict) -> None:
    row_start = config.GROUP_T_TABLE + idx * config.GROUP_ROW_STAGGER
    table_p = utils.smooth_step(min(1.0, max(0.0, (t - row_start) / 0.5)))
    if table_p <= 0.01:
        return

    cy    = config.GROUP_ROW_Y0 + idx * config.GROUP_ROW_STEP
    bar_y = cy + config.GROUP_ROW_H // 2 - config.GROUP_BAR_H // 2
    pct   = team["qualification_probability"]
    color = _qual_color(pct)

    bar_start = config.GROUP_T_BARS + idx * config.GROUP_ROW_STAGGER

    # Track (always visible once the row has faded in)
    lyr = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    ld  = ImageDraw.Draw(lyr)
    utils.rounded_rect(ld, config.GROUP_BAR_X, bar_y, config.GROUP_BAR_W, config.GROUP_BAR_H,
                       config.GROUP_BAR_H // 2, (255, 255, 255, int(35 * table_p)))
    canvas.alpha_composite(lyr)

    if t < bar_start:
        return

    raw   = (t - bar_start) / config.GROUP_BAR_FILL_DUR
    bar_p = utils.ease_out(min(1.0, raw))

    if raw < 1.0:
        glow = 0.35 + 0.15 * math.sin(t * math.pi * 1.5)
    else:
        gp   = min(1.0, max(0.0, (t - (bar_start + config.GROUP_BAR_FILL_DUR)) / 0.6))
        glow = math.sin(gp * math.pi) * 0.5 if gp < 1.0 else 0.0

    fill_w = int(config.GROUP_BAR_W * (pct / 100) * bar_p)
    utils.glow_bar(canvas, config.GROUP_BAR_X, bar_y, fill_w, config.GROUP_BAR_H, color, glow)

    # Percentage counter
    pct_now = int(pct * bar_p)
    txt = f"{pct_now}%"
    pf  = fonts["pct"]
    pct_y = cy + (config.GROUP_ROW_H - utils.text_height(pf)) // 2
    lyr2 = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    ld2  = ImageDraw.Draw(lyr2)
    utils.shadow_text(ld2, txt, pf, config.GROUP_PCT_X, pct_y, fill=config.C_WHITE)
    canvas.alpha_composite(lyr2)


# ═══════════════════════════════════════════════════════════════════════════════
# AI INSIGHT  (5.5s)
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_insight(canvas: Image.Image, t: float, fonts: dict, insight_text: str) -> None:
    if t < config.GROUP_T_INSIGHT:
        return
    p = utils.smooth_step(min(1.0, (t - config.GROUP_T_INSIGHT) / 0.5))
    if p <= 0.01:
        return

    f = fonts["insight"]
    w = utils.text_width(f, insight_text)
    lyr = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    ld  = ImageDraw.Draw(lyr)
    rise = int(10 * (1 - p))
    utils.shadow_text(ld, insight_text, f, (config.VIDEO_W - w) // 2,
                      config.GROUP_INSIGHT_Y + rise, fill=(*config.C_CYAN, int(230 * p)))
    canvas.alpha_composite(lyr)


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO
# ═══════════════════════════════════════════════════════════════════════════════
def _build_audio(duration: float) -> np.ndarray:
    n = int(config.SAMPLE_RATE * duration)

    music = utils.load_music(duration, music_path=config.GROUP_MUSIC_FILE)
    if music is not None:
        fade_s = int(config.SAMPLE_RATE * 1.5)
        fs     = max(0, n - fade_s)
        ramp   = np.linspace(1.0, 0.0, n - fs, dtype=np.float32)
        music[fs:, 0] *= ramp
        music[fs:, 1] *= ramp
        base = music * 0.8
        print("  Music      : group_stage.mp3")
    else:
        print("  Music      : not found, using ambient pad fallback")
        base = utils.gen_ambient(duration)

    sfx = np.zeros((n, 2), dtype=np.float32)

    def _add(arr: np.ndarray, start_t: float, gain: float) -> None:
        si = int(start_t * config.SAMPLE_RATE)
        if si >= n:
            return
        ei = min(si + len(arr), n)
        sfx[si:ei] += arr[:ei - si] * gain

    _add(utils.gen_whoosh(0.35),       config.GROUP_T_TITLE,   0.50)
    _add(utils.gen_tick(impact=False), config.GROUP_T_TABLE,   0.30)
    _add(utils.gen_tick(impact=False), config.GROUP_T_BARS,    0.30)
    _add(utils.gen_tick(impact=True),  config.GROUP_T_GLOW,    0.50)
    _add(utils.gen_whoosh(0.30),       config.GROUP_T_INSIGHT - 0.15, 0.35)
    _add(utils.gen_tick(impact=False), config.GROUP_T_INSIGHT, 0.30)

    return np.clip(base + sfx, -1.0, 1.0).astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════════════
# FRAME BUILDER CLOSURE
# ═══════════════════════════════════════════════════════════════════════════════
def _make_frame_fn(group_result: dict, duration: float):
    """Returns the make_frame(t) callable used by MoviePy VideoClip."""
    fonts = {
        "title":   utils.load_font(config.FS_GROUP_TITLE,   prefer_impact=True),
        "sub":     utils.load_font(config.FS_GROUP_SUB,     prefer_impact=False),
        "name":    utils.load_font(config.FS_GROUP_NAME,    prefer_impact=True),
        "small":   utils.load_font(config.FS_GROUP_SMALL,   prefer_impact=False),
        "pts":     utils.load_font(config.FS_GROUP_PTS,     prefer_impact=False),
        "pct":     utils.load_font(config.FS_GROUP_PCT,     prefer_impact=True),
        "insight": utils.load_font(config.FS_GROUP_INSIGHT, prefer_impact=False),
        "cta":     utils.load_font(config.FS_CTA,            prefer_impact=False),
    }
    cta_text = utils.next_cta()
    bg = Image.open(config.GROUP_BG).convert("RGBA")
    bg = bg.resize((config.VIDEO_W, config.VIDEO_H), Image.LANCZOS)

    standings = group_result["standings"]
    flags = utils.load_flags([{"code": s["code"]} for s in standings])

    group_letter = group_result["group"]
    insight_text = _strip_emoji(group_result["insight"])

    living_layout = None
    if config.ANIMATED_BACKGROUND:
        seed = ord(group_letter) * 17
        living_layout = utils.build_living_layout(seed)

    def make_frame(t: float) -> np.ndarray:
        canvas = bg.copy()

        if living_layout is not None:
            utils.draw_living_background(canvas, t, living_layout)

        _draw_title(canvas, t, fonts, group_letter)

        for idx, team in enumerate(standings):
            _draw_row(canvas, idx, t, fonts, flags, team)
            _draw_bar(canvas, idx, t, fonts, team)

        _draw_insight(canvas, t, fonts, insight_text)
        utils.draw_cta(canvas, t, duration, cta_text, fonts["cta"], config.GROUP_CTA_Y)

        zoom   = 1.0 + 0.04 * (t / duration)
        canvas = utils.apply_zoom(canvas, zoom)
        return np.array(canvas.convert("RGB"))

    return make_frame


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════
def render_group_prediction(group_result: dict, output_path: Path | None = None) -> Path:
    """
    Renders the Group Qualification Prediction video and saves it as MP4.

    Args:
        group_result: dict from group_data.get_group_prediction()
        output_path:  destination path
                      (default: output/group_<letter>_prediction.mp4)

    Returns:
        Path to the generated MP4 file.
    """
    letter = group_result["group"]
    out = output_path or (config.OUTPUT_DIR / f"group_{letter.lower()}_prediction.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    duration = config.GROUP_DURATION

    print(f"  Resolution : {config.VIDEO_W}x{config.VIDEO_H} @ {config.VIDEO_FPS} fps")
    print(f"  Duration   : {duration:.1f}s")
    print(f"  Group      : {letter}")
    print(f"  Output     : {out.name}")

    make_frame = _make_frame_fn(group_result, duration)
    clip = VideoClip(make_frame, duration=duration)

    print("  Building audio...")
    audio_arr = _build_audio(duration)
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
    clip.close()

    return out
