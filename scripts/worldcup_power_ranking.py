#!/usr/bin/env python3
"""
worldcup_power_ranking.py
Genera el vídeo "AI Power Ranking" del Mundial 2026 al estilo DAZN/ESPN.
"""

import os
import math
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from moviepy import VideoClip

# ═══════════════════════════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════════════════════════
ROOT      = Path(__file__).resolve().parent.parent
ASSETS    = ROOT / "assets"
FLAGS_DIR = ASSETS / "flags"
BG_PATH   = ASSETS / "backgrounds" / "power_ranking_bg.png"
OUTPUT    = ROOT / "output" / "worldcup_power_ranking.mp4"

# ═══════════════════════════════════════════════════════════════════════════════
# CANVAS
# ═══════════════════════════════════════════════════════════════════════════════
W, H = 1080, 1920
FPS  = 30

# ═══════════════════════════════════════════════════════════════════════════════
# RANKING DATA  (rank 1 = top, rank 10 = bottom; reveal order reversed)
# ═══════════════════════════════════════════════════════════════════════════════
RANKING = [
    {"rank":  1, "name": "BRASIL",       "code": "br",     "pct": 22},
    {"rank":  2, "name": "FRANCIA",      "code": "fr",     "pct": 18},
    {"rank":  3, "name": "ARGENTINA",    "code": "ar",     "pct": 15},
    {"rank":  4, "name": "INGLATERRA",   "code": "gb-eng", "pct": 10},
    {"rank":  5, "name": "ESPANA",       "code": "es",     "pct":  8},
    {"rank":  6, "name": "ALEMANIA",     "code": "de",     "pct":  6},
    {"rank":  7, "name": "PORTUGAL",     "code": "pt",     "pct":  5},
    {"rank":  8, "name": "PAISES BAJOS", "code": "nl",     "pct":  4},
    {"rank":  9, "name": "BELGICA",      "code": "be",     "pct":  3},
    {"rank": 10, "name": "MARRUECOS",    "code": "ma",     "pct":  2},
]
MAX_PCT = max(t["pct"] for t in RANKING)

# ═══════════════════════════════════════════════════════════════════════════════
# LAYOUT  (calibrated against the background slot positions)
# ═══════════════════════════════════════════════════════════════════════════════
ROWS_Y0  = 345    # top of row #1 slot
ROW_H    = 130    # slot height
ROW_GAP  = 8      # gap between slots
ROW_STEP = ROW_H + ROW_GAP   # = 138

RANK_X   = 18     # left edge of "#N" text
NAME_X   = 106    # left edge of country name
BAR_X    = 310    # left edge of bar track
BAR_MAXW = 530    # bar width at 100% fill  (x reaches 840)
BAR_H    = 26     # bar height
BAR_R    = 13     # corner radius
PCT_X    = 858    # left edge of "NN%" text
FLAG_X   = 946    # left edge of flag image
FLAG_W   = 118    # flag display width
FLAG_H   = 89     # flag display height  (4:3 ratio ≈ 118*3/4)

# ═══════════════════════════════════════════════════════════════════════════════
# COLOR PALETTE
# ═══════════════════════════════════════════════════════════════════════════════
C_WHITE     = (255, 255, 255)
C_OFFWHITE  = (230, 235, 245)
C_CYAN      = (80,  220, 200)    # rank numbers
C_GOLD      = (255, 215,  30)    # rank #1
C_BAR       = (40,  210,  90)    # bar fill color
C_BAR_LIT   = (100, 255, 130)    # bar color during glow pulse
C_GLOW      = (60,  240, 120)    # glow overlay
C_DIM_ROW   = (0,    20,   8, 30)  # subtle green tint on unrevealed rows

# ═══════════════════════════════════════════════════════════════════════════════
# TIMING  (seconds)
# ═══════════════════════════════════════════════════════════════════════════════
INTRO_T  = 0.6    # header settle
SLOT_T   = 1.45   # time budget per team (10 slots = 14.5 s)
OUTRO_T  = 2.9    # hold after #1 fully reveals

DURATION = INTRO_T + 10 * SLOT_T + OUTRO_T   # ≈ 18.0 s

def _build_timings():
    timings = []
    for screen_idx in range(10):        # 0 = #1 (top), 9 = #10 (bottom)
        reveal_order = 9 - screen_idx   # 0 = Morocco (first), 9 = Brazil (last)
        is_top       = (screen_idx == 0)
        t0           = INTRO_T + reveal_order * SLOT_T
        bar_dur      = 1.0 if is_top else 0.68
        timings.append({
            "start":      t0,
            "name_done":  t0 + 0.16,
            "bar_start":  t0 + 0.16,
            "bar_end":    t0 + 0.16 + bar_dur,
            "flag_start": t0 + 0.16 + bar_dur,
            "flag_end":   t0 + 0.16 + bar_dur + 0.40,
            "glow_start": t0 + 0.16 + bar_dur,
            "glow_end":   t0 + 0.16 + bar_dur + 0.55,
        })
    return timings

TIMINGS = _build_timings()

# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO SYNTHESIS
# ═══════════════════════════════════════════════════════════════════════════════
SR = 44100   # sample rate

def _ambient(dur, sr=SR):
    """Ambient drone: A1 + harmonics with slow vibrato."""
    t = np.linspace(0, dur, int(sr * dur))
    pad = (0.38 * np.sin(2*np.pi*55*t) +
           0.22 * np.sin(2*np.pi*110*t) +
           0.11 * np.sin(2*np.pi*165*t) +
           0.06 * np.sin(2*np.pi*220*t))
    pad *= 0.85 + 0.15 * np.sin(2*np.pi * 0.13 * t)
    # Rise/fall envelope
    fi = np.clip(t / 1.8, 0, 1)
    fo = np.clip((dur - t) / 1.8, 0, 1)
    pad *= fi * fo * 0.20
    return np.stack([pad, pad], axis=1).astype(np.float32)

def _tick(sr=SR, impact=False):
    """Short percussive tick sound."""
    dur  = 0.14 if impact else 0.07
    t    = np.linspace(0, dur, int(sr * dur))
    if impact:
        w   = (0.50 * np.sin(2*np.pi * 520 * t) +
               0.30 * np.sin(2*np.pi * 260 * t) +
               0.20 * np.sin(2*np.pi * 130 * t))
        env = np.exp(-t * 16)
        amp = 0.60
    else:
        w   = np.sin(2*np.pi * 1100 * t)
        env = np.exp(-t * 55)
        amp = 0.28
    result = w * env * amp
    return np.stack([result, result], axis=1).astype(np.float32)

def build_audio(duration=DURATION, sr=SR):
    n     = int(sr * duration)
    audio = _ambient(duration, sr)
    for i, tm in enumerate(TIMINGS):
        is_top = (i == 0)
        tick   = _tick(sr, impact=is_top)
        si     = int(tm["glow_start"] * sr)
        ei     = min(si + len(tick), n)
        audio[si:ei] += tick[:ei - si]
    return np.clip(audio, -1, 1).astype(np.float32)

# ═══════════════════════════════════════════════════════════════════════════════
# FONT LOADER
# ═══════════════════════════════════════════════════════════════════════════════
def _font(size, prefer_impact=True):
    order = (
        ["C:/Windows/Fonts/impact.ttf",
         "C:/Windows/Fonts/arialbd.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if prefer_impact else
        ["C:/Windows/Fonts/arialbd.ttf",
         "C:/Windows/Fonts/impact.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
    )
    for p in order:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()

# ═══════════════════════════════════════════════════════════════════════════════
# DRAWING PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════════
def _tw(font, text):
    bb = font.getbbox(text)
    return bb[2] - bb[0]

def _th(font, text="Ag"):
    bb = font.getbbox(text)
    return bb[3] - bb[1]

def _rrect(draw, x, y, w, h, r, fill):
    """Filled rounded rectangle."""
    if w <= 0 or h <= 0:
        return
    r = max(0, min(r, h // 2, w // 2))
    draw.rectangle([x + r, y, x + w - r, y + h],     fill=fill)
    draw.rectangle([x, y + r, x + w, y + h - r],     fill=fill)
    draw.ellipse  ([x,         y,         x+2*r,   y+2*r  ], fill=fill)
    draw.ellipse  ([x+w-2*r,  y,         x+w,     y+2*r  ], fill=fill)
    draw.ellipse  ([x,         y+h-2*r,  x+2*r,   y+h    ], fill=fill)
    draw.ellipse  ([x+w-2*r,  y+h-2*r,  x+w,     y+h    ], fill=fill)

def _text_shadow(draw, text, font, x, y, fill, shadow=(0, 0, 0)):
    """Text with soft drop shadow."""
    for ox, oy in [(2, 2), (2, -2), (-2, 2), (-2, -2)]:
        draw.text((x + ox, y + oy), text, font=font,
                  fill=(*shadow, 120))
    draw.text((x, y), text, font=font, fill=fill)

def _ease_out(t):
    return 1 - (1 - max(0.0, min(1.0, t))) ** 3

def _ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

# ═══════════════════════════════════════════════════════════════════════════════
# BAR WITH GLOW
# ═══════════════════════════════════════════════════════════════════════════════
def _glow_bar(canvas, x, y, w, h, color, glow=0.0):
    """
    Draws a bar with optional glow halo.
    canvas: RGBA PIL Image.
    glow: 0.0 (none) to 1.0 (full pulse).
    """
    if w <= 2:
        return
    # Glow layer (blurred halo)
    if glow > 0.02:
        pad  = 14
        gw   = w + 2 * pad
        gh   = h + 2 * pad
        halo = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
        hd   = ImageDraw.Draw(halo)
        a    = int(140 * glow)
        _rrect(hd, 0, 0, gw, gh, gh // 2, (*C_GLOW, a))
        halo = halo.filter(ImageFilter.GaussianBlur(8))
        canvas.paste(halo, (x - pad, y - pad), halo)
    # Main bar
    bar = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd  = ImageDraw.Draw(bar)
    c   = C_BAR_LIT if glow > 0.3 else color
    _rrect(bd, 0, 0, w, h, h // 2, (*c, 255))
    # Highlight stripe (top 30%)
    hl_h = max(2, h * 3 // 10)
    _rrect(bd, 2, 2, w - 4, hl_h, h // 2,
           (min(255, c[0]+70), min(255, c[1]+50), min(255, c[2]+50), 140))
    canvas.paste(bar, (x, y), bar)

# ═══════════════════════════════════════════════════════════════════════════════
# ROW RENDERER
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_row(canvas, idx, t, fonts, flags):
    """
    Renders a single ranking row onto canvas (RGBA Image).
    idx 0 = #1 Brazil (top row), idx 9 = #10 Morocco (bottom row).
    """
    team   = RANKING[idx]
    tm     = TIMINGS[idx]
    row_y  = ROWS_Y0 + idx * ROW_STEP
    cy     = row_y + ROW_H // 2     # vertical center

    if t < tm["start"]:
        return

    # ── rank + country name ────────────────────────────────────────────────────
    name_p  = _ease_in_out(min(1.0, (t - tm["start"]) / 0.18))
    rank_c  = C_GOLD if team["rank"] == 1 else C_CYAN
    rank_c  = tuple(int(v * name_p) for v in rank_c)
    name_c  = tuple(int(v * name_p) for v in C_WHITE)

    lyr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld  = ImageDraw.Draw(lyr)

    rank_txt = f"#{team['rank']}"
    rh = _th(fonts["rank"])
    _text_shadow(ld, rank_txt, fonts["rank"],
                 RANK_X, cy - rh // 2,
                 fill=(*rank_c, int(255 * name_p)))

    nh = _th(fonts["name"])
    _text_shadow(ld, team["name"], fonts["name"],
                 NAME_X, cy - nh // 2,
                 fill=(*name_c, int(255 * name_p)))

    canvas.alpha_composite(lyr)

    # ── bar + counter ─────────────────────────────────────────────────────────
    if t < tm["bar_start"]:
        return

    bar_p  = _ease_out(min(1.0, (t - tm["bar_start"]) /
                            (tm["bar_end"] - tm["bar_start"])))
    fill_w = max(0, int(BAR_MAXW * (team["pct"] / MAX_PCT) * bar_p))
    bar_y  = cy - BAR_H // 2

    # Glow pulse after bar fills
    glow = 0.0
    if t >= tm["glow_start"]:
        gp    = min(1.0, (t - tm["glow_start"]) /
                         (tm["glow_end"] - tm["glow_start"]))
        glow  = math.sin(gp * math.pi) * 0.9

    _glow_bar(canvas, BAR_X, bar_y, fill_w, BAR_H, C_BAR, glow)

    # Percentage counter
    pct_now = int(team["pct"] * bar_p)
    pct_txt = f"{pct_now}%"
    ph = _th(fonts["pct"])
    pl  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd  = ImageDraw.Draw(pl)
    _text_shadow(pd, pct_txt, fonts["pct"],
                 PCT_X, cy - ph // 2 - 1, fill=C_WHITE)
    canvas.alpha_composite(pl)

    # ── flag ──────────────────────────────────────────────────────────────────
    if t < tm["flag_start"]:
        return

    flag_alpha = _ease_in_out(min(1.0, (t - tm["flag_start"]) /
                                       (tm["flag_end"] - tm["flag_start"])))
    flag_src   = flags.get(team["code"])
    if flag_src and flag_alpha > 0.01:
        fa   = int(255 * flag_alpha)
        flag = flag_src.copy()
        r, g, b, a = flag.split()
        a = a.point(lambda v: v * fa // 255)
        flag = Image.merge("RGBA", (r, g, b, a))
        fy   = cy - FLAG_H // 2
        canvas.paste(flag, (FLAG_X, fy), flag)

# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVE ROW HIGHLIGHT  (subtle glow around the currently animating row)
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_active_highlight(canvas, idx, intensity):
    if intensity < 0.01:
        return
    row_y = ROWS_Y0 + idx * ROW_STEP
    pad   = 6
    a     = int(55 * intensity)
    glow  = Image.new("RGBA", (W - 80, ROW_H + 2 * pad), (0, 0, 0, 0))
    gd    = ImageDraw.Draw(glow)
    _rrect(gd, 0, 0, W - 80, ROW_H + 2 * pad, 12, (*C_GLOW, a))
    glow  = glow.filter(ImageFilter.GaussianBlur(10))
    canvas.paste(glow, (40, row_y - pad), glow)

# ═══════════════════════════════════════════════════════════════════════════════
# BACKGROUND + SUBTITLE OVERLAY
# ═══════════════════════════════════════════════════════════════════════════════
def _prepare_bg(font_sub):
    bg = Image.open(BG_PATH).convert("RGBA").resize((W, H), Image.LANCZOS)
    # Overlay "AI POWER RANKING" subtitle (background doesn't have it)
    d   = ImageDraw.Draw(bg)
    sub = "AI POWER RANKING"
    sw  = _tw(font_sub, sub)
    sx  = (W - sw) // 2
    # Placed below the baked-in title, before the first row slot
    d.text((sx + 2, 288 + 2), sub, font=font_sub, fill=(0, 80, 60, 160))
    d.text((sx,     288),     sub, font=font_sub, fill=(*C_CYAN, 220))
    return bg

# ═══════════════════════════════════════════════════════════════════════════════
# ZOOM HELPER
# ═══════════════════════════════════════════════════════════════════════════════
def _apply_zoom(img, factor):
    if factor <= 1.001:
        return img
    nw = int(W * factor)
    nh = int(H * factor)
    z  = img.resize((nw, nh), Image.BILINEAR)
    x0 = (nw - W) // 2
    y0 = (nh - H) // 2
    return z.crop((x0, y0, x0 + W, y0 + H))

# ═══════════════════════════════════════════════════════════════════════════════
# FRAME BUILDER  (closure – heavy assets loaded once)
# ═══════════════════════════════════════════════════════════════════════════════
def make_frame_builder():
    print("Cargando assets...")

    fonts = {
        "rank":   _font(44, prefer_impact=True),
        "name":   _font(34, prefer_impact=True),
        "pct":    _font(38, prefer_impact=False),
        "sub":    _font(40, prefer_impact=False),
        "footer": _font(30, prefer_impact=False),
    }

    bg = _prepare_bg(fonts["sub"])

    flags = {}
    for team in RANKING:
        p = FLAGS_DIR / f"{team['code']}.png"
        if p.exists():
            img = Image.open(p).convert("RGBA")
            flags[team["code"]] = img.resize((FLAG_W, FLAG_H), Image.LANCZOS)
        else:
            flags[team["code"]] = Image.new("RGBA", (FLAG_W, FLAG_H), (50, 50, 50, 200))
            print(f"  [aviso] bandera no encontrada: {p}")

    print(f"Assets listos. Duracion: {DURATION:.1f}s")

    def make_frame(t):
        canvas = bg.copy()

        # Active row highlight (detect which team is currently animating)
        for idx in range(10):
            tm = TIMINGS[idx]
            if tm["start"] <= t < tm["glow_end"]:
                prog = min(1.0, (t - tm["start"]) / (tm["glow_end"] - tm["start"]))
                _draw_active_highlight(canvas, idx, math.sin(prog * math.pi) * 0.6)

        # Draw all rows
        for idx in range(10):
            _draw_row(canvas, idx, t, fonts, flags)

        # Footer label (fade in after all rows start appearing)
        if t > INTRO_T + 1.0:
            footer_a = min(1.0, (t - INTRO_T - 1.0) / 1.0)
            fl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            fd = ImageDraw.Draw(fl)
            footer_txt = "AI WORLD CUP ANALYTICS"
            fw = _tw(fonts["footer"], footer_txt)
            fd.text(((W - fw) // 2, H - 110), footer_txt,
                    font=fonts["footer"],
                    fill=(*C_CYAN, int(160 * footer_a)))
            canvas.alpha_composite(fl)

        # Slow zoom (1.0 → 1.04 over full duration)
        zoom = 1.0 + 0.04 * (t / DURATION)
        canvas = _apply_zoom(canvas, zoom)

        return np.array(canvas.convert("RGB"))

    return make_frame


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    OUTPUT.parent.mkdir(exist_ok=True)
    print(f"Generando Power Ranking {W}x{H} @ {FPS}fps, {DURATION:.1f}s")

    clip = VideoClip(make_frame_builder(), duration=DURATION)

    # Audio synthesis
    print("Sintetizando audio...")
    try:
        from moviepy import AudioArrayClip
        audio_data = build_audio()
        audio_clip = AudioArrayClip(audio_data, fps=SR)
        clip       = clip.with_audio(audio_clip)
        print("Audio OK")
    except Exception as e:
        print(f"Audio omitido: {e}")

    out = str(OUTPUT)
    print(f"Exportando: {out}")
    clip.write_videofile(
        out,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        ffmpeg_params=["-crf", "20"],
        logger="bar",
    )
    print(f"Listo: {out}")


if __name__ == "__main__":
    main()
