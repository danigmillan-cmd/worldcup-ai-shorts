"""
match_renderer.py
Animated video renderer for AI Match Prediction Shorts.

Generates a vertical 1080x1920 MP4 for a single head-to-head matchup:
title reveal, AI subtitle, flags + team names, animated probability
bars, winner highlight, and a predicted-score reveal.

Public API:
    render_match_prediction(match, output_path=None) -> Path
"""
import math
import random
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw

from moviepy import VideoClip, AudioArrayClip

import config
import utils


# ═══════════════════════════════════════════════════════════════════════════════
# SUBTITLE — "AI MATCH PREDICTION"  (0.7s)
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_subtitle(canvas: Image.Image, t: float, fonts: dict) -> None:
    if t < config.MATCH_T_SUBTITLE:
        return
    p = utils.smooth_step(min(1.0, (t - config.MATCH_T_SUBTITLE) / 0.35))
    if p <= 0.01:
        return

    f   = fonts["sub"]
    txt = "AI MATCH PREDICTION"
    w   = utils.text_width(f, txt)
    lyr = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    ld  = ImageDraw.Draw(lyr)
    utils.shadow_text(ld, txt, f, (config.VIDEO_W - w) // 2, config.MATCH_SUB_Y,
                      fill=(*config.C_CYAN, int(220 * p)))
    canvas.alpha_composite(lyr)


# ═══════════════════════════════════════════════════════════════════════════════
# TITLE ROW — "[FLAG A]  TEAM A  VS  TEAM B  [FLAG B]"  (0.0s)
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_title_row(canvas: Image.Image, t: float, fonts: dict,
                    title_flags: dict, match: dict) -> None:
    p = utils.smooth_step(min(1.0, (t - config.MATCH_T_TITLE) / 0.5))
    if p <= 0.01:
        return

    f = fonts["title"]
    seg_a, seg_vs, seg_b = match["team_a"]["name"], "  VS  ", match["team_b"]["name"]
    w_a  = utils.text_width(f, seg_a)
    w_vs = utils.text_width(f, seg_vs)
    w_b  = utils.text_width(f, seg_b)
    total_w = w_a + w_vs + w_b
    h = utils.text_height(f)

    fw, fh = config.MATCH_TITLE_FLAG_W, config.MATCH_TITLE_FLAG_H
    gap = 24
    panel_a_cx = (config.MATCH_PANEL_LEFT[0]  + config.MATCH_PANEL_LEFT[2])  // 2
    panel_b_cx = (config.MATCH_PANEL_RIGHT[0] + config.MATCH_PANEL_RIGHT[2]) // 2
    left_x   = panel_a_cx - fw // 2
    right_x  = panel_b_cx - fw // 2
    text_x0  = left_x + fw + gap
    text_x1  = right_x - gap
    text_area_w = text_x1 - text_x0

    pad   = 16
    layer = Image.new("RGBA", (total_w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    ld    = ImageDraw.Draw(layer)
    alpha = int(255 * p)
    x = pad
    utils.shadow_text(ld, seg_a,  f, x, pad, fill=(*config.C_WHITE, alpha)); x += w_a
    utils.shadow_text(ld, seg_vs, f, x, pad, fill=(*config.C_GOLD,  alpha)); x += w_vs
    utils.shadow_text(ld, seg_b,  f, x, pad, fill=(*config.C_WHITE, alpha))

    # Auto-shrink if the title text would overflow the space between the flags.
    if layer.width > text_area_w:
        scale = text_area_w / layer.width
        layer = layer.resize((int(layer.width * scale), int(layer.height * scale)), Image.BILINEAR)

    ty = config.MATCH_TITLE_Y + (fh - layer.height) // 2 - int(20 * (1 - p))
    tx = text_x0 + (text_area_w - layer.width) // 2
    canvas.paste(layer, (tx - pad, ty - pad), layer)

    # Flags slide in from off-screen on either side of the title text.
    a_p = utils.ease_out(min(1.0, max(0.0, (t - 0.2) / 0.5)))
    b_p = utils.ease_out(min(1.0, max(0.0, (t - 0.3) / 0.5)))

    def _paste_flag(flag: Image.Image | None, x0: int, slide: int, alpha_p: float) -> None:
        if flag is None or alpha_p <= 0.01:
            return
        f2 = flag
        if alpha_p < 1.0:
            r, g, b_, al = f2.split()
            al = al.point(lambda v, ap=alpha_p: int(v * ap))
            f2 = Image.merge("RGBA", (r, g, b_, al))
        offset = int(slide * (1 - alpha_p))
        canvas.alpha_composite(f2, (x0 + offset, config.MATCH_TITLE_Y))

    _paste_flag(title_flags.get("a"), left_x,  -120, a_p)
    _paste_flag(title_flags.get("b"), right_x,  120, b_p)


# ═══════════════════════════════════════════════════════════════════════════════
# VERTICAL PROBABILITY BARS — fill bottom-to-top inside the side panels
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_vertical_bar(canvas: Image.Image, t: float, fonts: dict,
                       pct: int, color: tuple, panel: tuple) -> None:
    x0, y0, x1, y1 = panel
    bar_x0 = x0 + config.MATCH_BAR_PAD
    bar_x1 = x1 - config.MATCH_BAR_PAD
    bar_w  = bar_x1 - bar_x0
    bar_bottom  = y1 - config.MATCH_BAR_PAD
    bar_top_max = y0 + config.MATCH_BAR_TOP_PAD
    max_h = bar_bottom - bar_top_max

    label_p = utils.smooth_step(min(1.0, max(0.0, (t - 0.6) / 0.4)))
    if label_p <= 0.01:
        return

    if t < config.MATCH_T_BARS:
        utils.progress_pill_vertical(canvas, bar_x0, bar_top_max, bar_w, max_h, 0, color,
                                     track_alpha=int(30 * label_p))
        return

    bar_p = utils.ease_out(min(1.0, (t - config.MATCH_T_BARS) /
                                (config.MATCH_T_REVEAL - config.MATCH_T_BARS)))
    cur_h = max(0, int(max_h * (pct / 100) * bar_p))

    if bar_p < 1.0:
        glow = 0.45 + 0.20 * math.sin(t * math.pi * 1.2)
    else:
        gp   = min(1.0, max(0.0, (t - config.MATCH_T_REVEAL) / 0.6))
        glow = math.sin(gp * math.pi) * 0.9 if gp < 1.0 else 0.0

    utils.progress_pill_vertical(canvas, bar_x0, bar_top_max, bar_w, max_h, cur_h, color, glow)

    # Percentage counter at the top of the panel
    pct_now = int(pct * bar_p)
    txt     = f"{pct_now}%"
    pf      = fonts["pct"]
    pw      = utils.text_width(pf, txt)
    cx      = (x0 + x1) // 2
    lyr = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    ld  = ImageDraw.Draw(lyr)
    utils.shadow_text(ld, txt, pf, cx - pw // 2, y0 + 12, fill=config.C_WHITE)
    canvas.alpha_composite(lyr)


def _draw_bars(canvas: Image.Image, t: float, fonts: dict, match: dict) -> None:
    _draw_vertical_bar(canvas, t, fonts, match["team_a"]["pct"], config.C_TEAM_A, config.MATCH_PANEL_LEFT)
    _draw_vertical_bar(canvas, t, fonts, match["team_b"]["pct"], config.C_TEAM_B, config.MATCH_PANEL_RIGHT)


# ═══════════════════════════════════════════════════════════════════════════════
# WINNER REVEAL — flag grows in the center panel  (4.0s)
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_winner_panel(canvas: Image.Image, t: float, fonts: dict,
                       winner_flag, match: dict) -> None:
    if t < config.MATCH_T_WINNER:
        return
    raw_p = min(1.0, (t - config.MATCH_T_WINNER) / 0.5)
    if raw_p <= 0.01:
        return

    scale   = utils.ease_overshoot(raw_p)
    alpha_p = utils.smooth_step(min(1.0, raw_p / 0.6))

    x0, y0, x1, y1 = config.MATCH_PANEL_CENTER
    pad = 40
    cx  = (x0 + x1) // 2

    def _scaled(flag: Image.Image, w: int, h: int) -> Image.Image:
        cur_w = max(1, int(w * scale))
        cur_h = max(1, int(h * scale))
        img = flag.resize((cur_w, cur_h), Image.BILINEAR)
        if alpha_p < 1.0:
            r, g, b, a = img.split()
            a = a.point(lambda v, ap=alpha_p: int(v * ap))
            img = Image.merge("RGBA", (r, g, b, a))
        return img

    if match["winner"] == "draw":
        # Two flags side by side, centered in the panel.
        gap     = 30
        avail_w = (x1 - x0) - pad * 2
        final_w = (avail_w - gap) // 2
        final_h = int(final_w * (config.FLAG_H / config.FLAG_W))
        flag_cy = y0 + 60 + final_h // 2

        flag_a, flag_b = winner_flag
        left_cx  = cx - gap // 2 - final_w // 2
        right_cx = cx + gap // 2 + final_w // 2

        for flag, target_cx in ((flag_a, left_cx), (flag_b, right_cx)):
            if flag is None:
                continue
            img = _scaled(flag, final_w, final_h)
            canvas.alpha_composite(img, (target_cx - img.width // 2, flag_cy - img.height // 2))

        txt = "DRAW"
    else:
        final_w = (x1 - x0) - pad * 2
        final_h = int(final_w * (config.FLAG_H / config.FLAG_W))
        flag_cy = y0 + 60 + final_h // 2   # fixed center: flag grows around this point

        if winner_flag is not None:
            img = _scaled(winner_flag, final_w, final_h)
            canvas.alpha_composite(img, (cx - img.width // 2, flag_cy - img.height // 2))

        winner = match["team_a"] if match["winner"] == "a" else match["team_b"]
        txt    = f"WINNER {winner['name']}"

    # Label below the flag(s)
    wf      = fonts["winner"]
    tw      = utils.text_width(wf, txt)
    label_y = y0 + 60 + final_h + 30
    lyr = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    ld  = ImageDraw.Draw(lyr)
    utils.shadow_text(ld, txt, wf, cx - tw // 2, label_y,
                      fill=(*config.C_GOLD, int(255 * alpha_p)))
    canvas.alpha_composite(lyr)


# ═══════════════════════════════════════════════════════════════════════════════
# PREDICTED SCORE REVEAL  (5.0s)
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_score(canvas: Image.Image, t: float, fonts: dict, match: dict) -> None:
    if t < config.MATCH_T_SCORE_CALC:
        return

    a, b = match["team_a"], match["team_b"]
    sf   = fonts["score"]

    if t < config.MATCH_T_SCORE:
        # "Calculating" — cycle through random scorelines, as if the AI were
        # still crunching numbers, before locking onto the final prediction.
        bucket  = int((t - config.MATCH_T_SCORE_CALC) / config.MATCH_SCORE_CALC_INTERVAL)
        rng     = random.Random(bucket)
        txt     = f"{rng.randint(0, 6)}  -  {rng.randint(0, 6)}"
        alpha_p = utils.smooth_step(min(1.0, (t - config.MATCH_T_SCORE_CALC) / 0.25))
        scale   = 1.0
        color   = (*config.C_CYAN, int(255 * alpha_p))
    else:
        raw_p   = min(1.0, (t - config.MATCH_T_SCORE) / 0.45)
        scale   = utils.ease_overshoot(raw_p)
        alpha_p = utils.smooth_step(min(1.0, raw_p / 0.6))
        txt     = f"{a['score']}  -  {b['score']}"
        color   = (*config.C_GOLD, int(255 * alpha_p))

    if alpha_p <= 0.01:
        return

    w = utils.text_width(sf, txt)
    h = utils.text_height(sf)

    pad   = 20
    layer = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    ld    = ImageDraw.Draw(layer)
    utils.shadow_text(ld, txt, sf, pad, pad, fill=color)

    nw = max(1, int(layer.width * scale))
    nh = max(1, int(layer.height * scale))
    layer = layer.resize((nw, nh), Image.BILINEAR)

    cx = config.VIDEO_W // 2
    cy = config.MATCH_SCORE_Y + h // 2
    canvas.paste(layer, (cx - nw // 2, cy - nh // 2), layer)

    # Label above the score
    lf    = fonts["sub"]
    label = "PREDICTED SCORE"
    lw    = utils.text_width(lf, label)
    lyr = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    ld2 = ImageDraw.Draw(lyr)
    utils.shadow_text(ld2, label, lf, (config.VIDEO_W - lw) // 2, config.MATCH_SCORE_Y - 60,
                      fill=(*config.C_CYAN, int(220 * alpha_p)))
    canvas.alpha_composite(lyr)


# ═══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_footer(canvas: Image.Image, t: float, fonts: dict) -> None:
    if t < 1.0:
        return
    fa  = min(1.0, (t - 1.0) / 1.0)
    txt = "AI WORLD CUP ANALYTICS"
    fw  = utils.text_width(fonts["footer"], txt)
    lyr = Image.new("RGBA", (config.VIDEO_W, config.VIDEO_H), (0, 0, 0, 0))
    ld  = ImageDraw.Draw(lyr)
    ld.text(((config.VIDEO_W - fw) // 2, config.VIDEO_H - 205), txt,
            font=fonts["footer"], fill=(*config.C_CYAN, int(160 * fa)))
    canvas.alpha_composite(lyr)


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO
# ═══════════════════════════════════════════════════════════════════════════════
def _build_audio(duration: float) -> np.ndarray:
    n = int(config.SAMPLE_RATE * duration)

    music_path = utils.next_match_music()
    music = utils.load_music(duration, music_path=music_path)
    if music is not None:
        fade_s = int(config.SAMPLE_RATE * 1.5)
        fs     = max(0, n - fade_s)
        ramp   = np.linspace(1.0, 0.0, n - fs, dtype=np.float32)
        music[fs:, 0] *= ramp
        music[fs:, 1] *= ramp
        base = music * 0.8
        print(f"  Music      : {music_path.name}")
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

    _add(utils.gen_whoosh(0.35), config.MATCH_T_TITLE,            0.50)
    _add(utils.gen_whoosh(0.25), config.MATCH_T_SUBTITLE,         0.35)
    _add(utils.gen_tick(impact=False), config.MATCH_T_BARS,       0.30)
    _add(utils.gen_tick(impact=True),  config.MATCH_T_REVEAL,     0.50)
    _add(utils.gen_tick(impact=True),  config.MATCH_T_WINNER,     0.60)
    _add(utils.gen_whoosh(0.30), config.MATCH_T_SCORE - 0.15,     0.40)
    _add(utils.gen_tick(impact=True),  config.MATCH_T_SCORE,      0.65)

    return np.clip(base + sfx, -1.0, 1.0).astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════════════
# FRAME BUILDER CLOSURE
# ═══════════════════════════════════════════════════════════════════════════════
def _load_hires_flag(code: str, w: int, h: int,
                     fallback: Image.Image | None) -> Image.Image | None:
    """Loads the original cached flag PNG and resizes it to (w, h);
    falls back to upscaling the small cached flag if unavailable."""
    path = config.FLAGS_DIR / f"{code}.png"
    if path.exists():
        try:
            return Image.open(path).convert("RGBA").resize((w, h), Image.LANCZOS)
        except Exception:
            pass
    if fallback is not None:
        return fallback.resize((w, h), Image.LANCZOS)
    return None


def _make_frame_fn(match: dict, duration: float):
    """Returns the make_frame(t) callable used by MoviePy VideoClip."""
    fonts = {
        "title":  utils.load_font(config.FS_MATCH_TITLE,  prefer_impact=True),
        "sub":    utils.load_font(config.FS_MATCH_SUB,    prefer_impact=False),
        "pct":    utils.load_font(config.FS_MATCH_PCT,    prefer_impact=False),
        "score":  utils.load_font(config.FS_MATCH_SCORE,  prefer_impact=True),
        "winner": utils.load_font(config.FS_MATCH_WINNER, prefer_impact=True),
        "footer": utils.load_font(config.FS_FOOTER,       prefer_impact=False),
        "cta":    utils.load_font(config.FS_CTA,          prefer_impact=False),
    }
    cta_text = utils.next_cta()
    bg_path = config.MATCH_BG

    bg = Image.open(bg_path).convert("RGBA")
    bg = bg.resize((config.VIDEO_W, config.VIDEO_H), Image.LANCZOS)

    legacy_bg = None
    if config.ENABLE_BG_CROSSFADE and config.MATCH_BG_LEGACY.exists():
        legacy_bg = Image.open(config.MATCH_BG_LEGACY).convert("RGBA")
        legacy_bg = legacy_bg.resize((config.VIDEO_W, config.VIDEO_H), Image.LANCZOS)

    flags = utils.load_flags([match["team_a"], match["team_b"]])

    living_layout = None
    if config.ANIMATED_BACKGROUND:
        seed = sum(ord(c) for c in match["team_a"]["code"] + match["team_b"]["code"])
        living_layout = utils.build_living_layout(seed)

    title_flags = {
        "a": _load_hires_flag(match["team_a"]["code"], config.MATCH_TITLE_FLAG_W,
                              config.MATCH_TITLE_FLAG_H, flags.get(match["team_a"]["code"])),
        "b": _load_hires_flag(match["team_b"]["code"], config.MATCH_TITLE_FLAG_W,
                              config.MATCH_TITLE_FLAG_H, flags.get(match["team_b"]["code"])),
    }

    tint_color = None
    if config.ENABLE_WINNER_COLOR_TINT and match["winner"] != "draw":
        winner_team = match["team_a"] if match["winner"] == "a" else match["team_b"]
        tint_color = utils.flag_dominant_color(winner_team["code"])

    x0, y0, x1, y1 = config.MATCH_PANEL_CENTER
    win_pad = 40
    if match["winner"] == "draw":
        gap     = 30
        avail_w = (x1 - x0) - win_pad * 2
        half_w  = (avail_w - gap) // 2
        half_h  = int(half_w * (config.FLAG_H / config.FLAG_W))
        flag_a  = _load_hires_flag(match["team_a"]["code"], half_w, half_h, flags.get(match["team_a"]["code"]))
        flag_b  = _load_hires_flag(match["team_b"]["code"], half_w, half_h, flags.get(match["team_b"]["code"]))
        winner_flag = (flag_a, flag_b)
    else:
        win_w    = (x1 - x0) - win_pad * 2
        win_h    = int(win_w * (config.FLAG_H / config.FLAG_W))
        winner   = match["team_a"] if match["winner"] == "a" else match["team_b"]
        winner_flag = _load_hires_flag(winner["code"], win_w, win_h, flags.get(winner["code"]))

    def make_frame(t: float) -> np.ndarray:
        if legacy_bg is not None:
            bp = config.BG_CROSSFADE_BREAKPOINT
            if t <= bp:
                p = utils.smooth_step(min(1.0, max(0.0, t / bp)))
                ramp = p * config.BG_CROSSFADE_MID
            else:
                remaining = max(0.001, duration - bp)
                p = utils.smooth_step(min(1.0, max(0.0, (t - bp) / remaining)))
                ramp = config.BG_CROSSFADE_MID + p * (config.BG_CROSSFADE_MAX - config.BG_CROSSFADE_MID)
            canvas = Image.blend(bg, legacy_bg, ramp)
        else:
            canvas = bg.copy()

        if living_layout is not None:
            utils.draw_living_background(canvas, t, living_layout)

        _draw_subtitle(canvas, t, fonts)
        _draw_title_row(canvas, t, fonts, title_flags, match)
        _draw_bars(canvas, t, fonts, match)
        _draw_winner_panel(canvas, t, fonts, winner_flag, match)
        _draw_score(canvas, t, fonts, match)
        _draw_footer(canvas, t, fonts)
        utils.draw_cta(canvas, t, duration, cta_text, fonts["cta"], config.MATCH_CTA_Y,
                       max_width=config.MATCH_CTA_MAXW)

        zoom   = 1.0 + 0.05 * (t / duration)
        canvas = utils.apply_zoom(canvas, zoom)

        if tint_color is not None:
            ramp = utils.smooth_step(min(1.0, max(0.0,
                (t - config.MATCH_T_WINNER) / config.MATCH_WINNER_TINT_RAMP)))
            if ramp > 0.001:
                rgb = utils.tint_image(canvas, tint_color, config.MATCH_WINNER_TINT_STRENGTH * ramp)
                return np.array(rgb)

        return np.array(canvas.convert("RGB"))

    return make_frame


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════
def render_match_prediction(match: dict, output_path: Path | None = None) -> Path:
    """
    Renders the AI Match Prediction video and saves it as MP4.

    Args:
        match      : dict from match_data.get_match_prediction()
        output_path: destination path (default: config.MATCH_OUTPUT)

    Returns:
        Path to the generated MP4 file.
    """
    out = output_path or config.MATCH_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)

    duration = config.MATCH_DURATION

    print(f"  Resolution : {config.VIDEO_W}x{config.VIDEO_H} @ {config.VIDEO_FPS} fps")
    print(f"  Duration   : {duration:.1f}s")
    print(f"  Matchup    : {match['team_a']['name']} vs {match['team_b']['name']}")
    print(f"  Output     : {out.name}")

    make_frame = _make_frame_fn(match, duration)
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
