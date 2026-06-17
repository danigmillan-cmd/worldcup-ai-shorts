"""
utils.py
Shared utilities: fonts, drawing primitives, easing, audio synthesis,
flag loading, and credential helpers.

No business logic lives here — only reusable building blocks.
"""
import os
import re
import math
import subprocess
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

import config


# ═══════════════════════════════════════════════════════════════════════════════
# FONTS
# ═══════════════════════════════════════════════════════════════════════════════
def load_font(size: int, prefer_impact: bool = True) -> ImageFont.FreeTypeFont:
    """
    Load a TrueType font with a cross-platform fallback chain.
    prefer_impact=True  → Impact-style (condensed, all-caps look like Bebas Neue)
    prefer_impact=False → Arial Bold (clean numerics and body text)
    """
    if prefer_impact:
        candidates = [
            "C:/Windows/Fonts/impact.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/Library/Fonts/Impact.ttf",
        ]
    else:
        candidates = [
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/Arial Bold.ttf",
            "C:/Windows/Fonts/impact.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


# ═══════════════════════════════════════════════════════════════════════════════
# TEXT HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def text_width(font: ImageFont.FreeTypeFont, text: str) -> int:
    bb = font.getbbox(text)
    return bb[2] - bb[0]


def text_height(font: ImageFont.FreeTypeFont, text: str = "Ag") -> int:
    bb = font.getbbox(text)
    return bb[3] - bb[1]


# ═══════════════════════════════════════════════════════════════════════════════
# DRAWING PRIMITIVES
# ═══════════════════════════════════════════════════════════════════════════════
def rounded_rect(draw: ImageDraw.Draw, x: int, y: int,
                 w: int, h: int, r: int, fill: tuple) -> None:
    """Filled rounded rectangle (pure Pillow, no external deps)."""
    if w <= 0 or h <= 0:
        return
    r = max(0, min(r, h // 2, w // 2))
    draw.rectangle([x + r, y,     x + w - r, y + h    ], fill=fill)
    draw.rectangle([x,     y + r, x + w,     y + h - r], fill=fill)
    draw.ellipse([x,         y,         x + 2*r, y + 2*r], fill=fill)
    draw.ellipse([x + w-2*r, y,         x + w,   y + 2*r], fill=fill)
    draw.ellipse([x,         y + h-2*r, x + 2*r, y + h  ], fill=fill)
    draw.ellipse([x + w-2*r, y + h-2*r, x + w,   y + h  ], fill=fill)


def shadow_text(draw: ImageDraw.Draw, text: str,
                font: ImageFont.FreeTypeFont,
                x: int, y: int,
                fill: tuple, shadow_alpha: int = 110) -> None:
    """Text with a 4-direction soft shadow."""
    for ox, oy in ((2, 2), (2, -2), (-2, 2), (-2, -2)):
        draw.text((x + ox, y + oy), text, font=font,
                  fill=(0, 0, 0, shadow_alpha))
    draw.text((x, y), text, font=font, fill=fill)


def progress_pill_vertical(canvas: Image.Image,
                           x: int, y: int, w: int, h: int,
                           fill_h: int, color: tuple, glow: float = 0.0,
                           track_alpha: int = 30) -> None:
    """
    Draws ONE vertical pill (rounded-rect, radius w//2) of size (w, h) at
    top-left (x, y). The bottom `fill_h` pixels are filled with `color`
    (brightened by `glow`); the rest shows a translucent white track.
    Both regions share a single pill outline, so it reads as one bar
    filling from the bottom rather than two separate shapes.
    """
    if h <= 2 or w <= 2:
        return
    fill_h = max(0, min(h, fill_h))

    mask = Image.new("L", (w, h), 0)
    md   = ImageDraw.Draw(mask)
    rounded_rect(md, 0, 0, w, h, w // 2, 255)

    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ld    = ImageDraw.Draw(layer)
    ld.rectangle([0, 0, w, h], fill=(255, 255, 255, track_alpha))

    if fill_h > 0:
        if glow > 0.02:
            boost = int(45 * min(1.0, glow))
            c = tuple(min(255, ch + boost) for ch in color)
        else:
            c = color
        # Rounded-rect fill so the leading tip is a rounded cap, not a flat edge
        rounded_rect(ld, 0, h - fill_h, w, fill_h, w // 2, (*c, 255))

    r, g, b, a = layer.split()
    a = ImageChops.multiply(a, mask)
    layer = Image.merge("RGBA", (r, g, b, a))

    # Halo glow behind the filled region only
    if glow > 0.02 and fill_h > 4:
        pad    = 14
        halo   = Image.new("RGBA", (w + 2*pad, fill_h + 2*pad), (0, 0, 0, 0))
        hd     = ImageDraw.Draw(halo)
        glow_c = tuple(min(255, ch + 70) for ch in color)
        rounded_rect(hd, 0, 0, w + 2*pad, fill_h + 2*pad, (w + 2*pad)//2,
                     (*glow_c, int(140 * glow)))
        halo = halo.filter(ImageFilter.GaussianBlur(8))
        canvas.paste(halo, (x - pad, y + (h - fill_h) - pad), halo)

    canvas.paste(layer, (x, y), layer)


def glow_bar(canvas: Image.Image,
             x: int, y: int, w: int, h: int,
             color: tuple, glow: float = 0.0) -> None:
    """
    Draws a rounded bar with an optional colored gaussian halo.
    The bar always uses its own color (gold/silver/bronze/green) —
    the glow simply brightens it, never overrides it with green.
    """
    if w <= 2:
        return

    # Halo layer
    if glow > 0.02:
        pad    = 14
        halo   = Image.new("RGBA", (w + 2*pad, h + 2*pad), (0, 0, 0, 0))
        hd     = ImageDraw.Draw(halo)
        glow_c = tuple(min(255, ch + 70) for ch in color)
        rounded_rect(hd, 0, 0, w + 2*pad, h + 2*pad, (h + 2*pad)//2,
                     (*glow_c, int(140 * glow)))
        halo = halo.filter(ImageFilter.GaussianBlur(8))
        canvas.paste(halo, (x - pad, y - pad), halo)

    # Solid bar (brightened by glow amount)
    bar = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd  = ImageDraw.Draw(bar)
    if glow > 0.02:
        boost = int(45 * min(1.0, glow))
        c = tuple(min(255, ch + boost) for ch in color)
    else:
        c = color
    rounded_rect(bd, 0, 0, w, h, h // 2, (*c, 255))

    # Specular highlight on top third
    hl = max(2, h * 3 // 10)
    rounded_rect(bd, 2, 2, w - 4, hl, h // 2,
                 (min(255, c[0]+70), min(255, c[1]+50), min(255, c[2]+50), 130))
    canvas.paste(bar, (x, y), bar)


# ═══════════════════════════════════════════════════════════════════════════════
# CALL-TO-ACTION OVERLAY  (rotating, final-stretch pill)
# ═══════════════════════════════════════════════════════════════════════════════
def next_cta(messages: list[str] | None = None) -> str:
    """
    Returns the next call-to-action string from `messages`
    (default config.CTA_MESSAGES), ROTATING one step per call — the next index
    is persisted in config.CTA_INDEX_FILE so consecutive renders cycle through
    the pool in order (same pattern as next_match_music). Call ONCE per render
    (in the renderer's _make_frame_fn closure), never per frame. Returns "" if
    CTAs are disabled or the pool is empty; falls back to index 0 if the
    counter file is missing/corrupt or unwritable.
    """
    import json

    if not config.CTA_ENABLED:
        return ""
    pool = messages if messages is not None else config.CTA_MESSAGES
    if not pool:
        return ""

    try:
        idx = json.loads(config.CTA_INDEX_FILE.read_text())["next"]
    except Exception:
        idx = 0
    idx = idx % len(pool)

    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.CTA_INDEX_FILE.write_text(json.dumps({"next": (idx + 1) % len(pool)}))
    except Exception:
        pass

    return pool[idx]


def draw_cta(canvas: Image.Image, t: float, duration: float,
             text: str, font: ImageFont.FreeTypeFont, y: int,
             lead: float | None = None, fade: float | None = None,
             max_width: int | None = None) -> None:
    """
    Draws a centered rounded "pill" CTA (dark backing + cyan outline + white
    text) at vertical center `y`, faded and risen in over the last `lead`
    seconds of the clip (defaults config.CTA_LEAD_S / config.CTA_FADE_S).
    If `max_width` is given and the pill is wider, it is scaled down to fit
    (e.g. to stay inside the match center panel). No-op before the final
    stretch or when `text` is empty.
    """
    if not text:
        return
    lead = config.CTA_LEAD_S if lead is None else lead
    fade = config.CTA_FADE_S if fade is None else fade
    start = duration - lead
    if t < start:
        return
    p = smooth_step(min(1.0, (t - start) / max(0.001, fade)))
    if p <= 0.01:
        return

    bb = font.getbbox(text)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pad_x, pad_y = 32, 16
    pill_w = tw + pad_x * 2
    pill_h = th + pad_y * 2

    # Build the pill on its own layer so it can be scaled to fit max_width.
    pill = Image.new("RGBA", (pill_w, pill_h), (0, 0, 0, 0))
    pd   = ImageDraw.Draw(pill)
    # Cyan outline = full-size cyan pill with a slightly smaller dark pill on top.
    rounded_rect(pd, 0, 0, pill_w, pill_h, pill_h // 2, (*config.C_CYAN, int(230 * p)))
    bw = 3
    rounded_rect(pd, bw, bw, pill_w - 2 * bw, pill_h - 2 * bw,
                 (pill_h - 2 * bw) // 2, (10, 22, 26, int(205 * p)))
    # Centered text (bb offsets align the glyph bbox within the pill).
    tx = (pill_w - tw) // 2 - bb[0]
    ty = (pill_h - th) // 2 - bb[1]
    shadow_text(pd, text, font, tx, ty,
                fill=(*config.C_WHITE, int(255 * p)), shadow_alpha=int(120 * p))

    if max_width and pill_w > max_width:
        scale = max_width / pill_w
        pill  = pill.resize((max(1, int(pill_w * scale)), max(1, int(pill_h * scale))),
                            Image.BILINEAR)

    cx   = config.VIDEO_W // 2
    rise = int(14 * (1 - p))
    canvas.alpha_composite(pill, (cx - pill.width // 2, y - pill.height // 2 + rise))


# ═══════════════════════════════════════════════════════════════════════════════
# EASING
# ═══════════════════════════════════════════════════════════════════════════════
def ease_out(t: float) -> float:
    """Cubic ease-out: fast start, smooth deceleration."""
    return 1.0 - (1.0 - max(0.0, min(1.0, t))) ** 3


def smooth_step(t: float) -> float:
    """Smoothstep: gentle acceleration and deceleration."""
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def ease_overshoot(t: float) -> float:
    """'Back' ease-out: overshoots past 1.0 then settles — a snappy pop-in."""
    t = max(0.0, min(1.0, t))
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# ═══════════════════════════════════════════════════════════════════════════════
# BACKGROUND ZOOM
# ═══════════════════════════════════════════════════════════════════════════════
def apply_zoom(img: Image.Image, factor: float) -> Image.Image:
    """
    Plain slow-zoom: scale up by `factor` and center-crop back to
    (config.VIDEO_W, config.VIDEO_H).
    """
    if factor <= 1.001:
        return img
    nw = int(config.VIDEO_W * factor)
    nh = int(config.VIDEO_H * factor)
    z  = img.resize((nw, nh), Image.BILINEAR)
    x0 = (nw - config.VIDEO_W) // 2
    y0 = (nh - config.VIDEO_H) // 2
    return z.crop((x0, y0, x0 + config.VIDEO_W, y0 + config.VIDEO_H))


# ═══════════════════════════════════════════════════════════════════════════════
# LIVING DATA LAYER  (Phase 1 — procedural "broadcast vivo" overlay)
# ═══════════════════════════════════════════════════════════════════════════════
def build_living_layout(seed: int = 0) -> dict:
    """
    Precomputes a deterministic (per `seed`) layout for the living-background
    layer: pass-network nodes/edges, pre-blurred heatmap-blob glow textures,
    a pre-blurred diagonal light-sweep texture, and rising bokeh particles.

    Call once per render and pass the result to draw_living_background() every
    frame — keeps per-frame cost cheap (no Gaussian blur inside the frame loop).
    """
    rng = np.random.default_rng(seed)
    w, h = config.VIDEO_W, config.VIDEO_H

    # Pass network: scattered nodes connected in a loop + a couple of extra chords.
    n_nodes = 9
    nodes = [(int(rng.uniform(100, w - 100)), int(rng.uniform(160, h - 240)))
             for _ in range(n_nodes)]
    order = list(range(n_nodes))
    rng.shuffle(order)
    edges = [(order[i], order[(i + 1) % n_nodes]) for i in range(n_nodes)]

    # Rising bokeh particles.
    particles = [(float(rng.uniform(0, w)), float(rng.uniform(0, h)),
                  float(rng.uniform(0.5, 1.4)), float(rng.uniform(3, 7)))
                 for _ in range(14)]

    return {"nodes": nodes, "edges": edges, "particles": particles}


def draw_living_background(canvas: Image.Image, t: float, layout: dict) -> None:
    """
    Draws the subtle animated "living data" layer in-place onto `canvas`
    (a pulsing pass-network and rising bokeh particles). Intended to sit
    between the background plate and the content overlays — low alpha,
    cyan/neon tones, broadcast-y ambience rather than a video-game effect.
    """
    w, h = canvas.size

    lyr = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ld  = ImageDraw.Draw(lyr)

    # Pass network — breathing lines + nodes.
    nodes = layout["nodes"]
    for i, (a, bidx) in enumerate(layout["edges"]):
        pulse = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(t * 0.7 + i * 1.3))
        alpha = int(30 + 60 * pulse)
        ld.line([nodes[a], nodes[bidx]], fill=(*config.C_CYAN, alpha), width=3)
    for i, (nx, ny) in enumerate(nodes):
        pulse = 0.5 + 0.5 * math.sin(t * 1.0 + i * 0.8)
        r = 4 + int(3 * pulse)
        alpha = int(60 + 110 * pulse)
        ld.ellipse([nx - r, ny - r, nx + r, ny + r], fill=(*config.C_CYAN, alpha))

    # Rising bokeh particles.
    for px, py, speed, size in layout["particles"]:
        y = (py - t * speed * 16) % h
        alpha = max(10, int(30 + 30 * math.sin(t * 0.4 + px * 0.02)))
        ld.ellipse([px - size, y - size, px + size, y + size], fill=(*config.C_WHITE, alpha))

    canvas.alpha_composite(lyr)


# ═══════════════════════════════════════════════════════════════════════════════
# FLAGS
# ═══════════════════════════════════════════════════════════════════════════════
def load_flags(teams: list[dict]) -> dict[str, Image.Image | None]:
    """
    Returns a dict mapping flag_code → resized RGBA PIL Image.
    Downloads any missing flags from flagcdn.com automatically.
    """
    import requests

    config.FLAGS_DIR.mkdir(parents=True, exist_ok=True)
    flags: dict[str, Image.Image | None] = {}

    for team in teams:
        code = team["code"]
        if code in flags:
            continue

        path = config.FLAGS_DIR / f"{code}.png"
        if not path.exists():
            url = f"https://flagcdn.com/256x192/{code}.png"
            try:
                r = requests.get(url, timeout=10)
                r.raise_for_status()
                path.write_bytes(r.content)
            except Exception as e:
                print(f"  [flag] Could not download {code}: {e}")
                flags[code] = None
                continue

        try:
            img = Image.open(path).convert("RGBA")
            flags[code] = img.resize((config.FLAG_W, config.FLAG_H), Image.LANCZOS)
        except Exception as e:
            print(f"  [flag] Could not load {code}: {e}")
            flags[code] = None

    return flags


# ═══════════════════════════════════════════════════════════════════════════════
# WINNER COLOR-GRADE  (flag-driven global tint)
# ═══════════════════════════════════════════════════════════════════════════════
def flag_dominant_color(code: str) -> tuple[int, int, int] | None:
    """
    Returns the dominant non-neutral color of a team's cached flag, or None if
    the flag file is missing/unreadable. Near-white, near-black and
    low-saturation (grey) pixels are excluded so the result is a vivid color
    that reads well as a global tint.
    """
    path = config.FLAGS_DIR / f"{code}.png"
    if not path.exists():
        return None

    try:
        img = Image.open(path).convert("RGB")
        img = img.resize((32, 24), Image.NEAREST)
        pixels = list(img.getdata())
    except Exception:
        return None

    buckets: dict[tuple[int, int, int], int] = {}
    fallback_sum = [0, 0, 0]
    fallback_n   = 0

    for r, g, b in pixels:
        fallback_sum[0] += r
        fallback_sum[1] += g
        fallback_sum[2] += b
        fallback_n += 1

        mx, mn = max(r, g, b), min(r, g, b)
        if mx > 235 and mn > 215:        # near-white
            continue
        if mx < 30:                       # near-black
            continue
        if mx - mn < 30:                  # low saturation (grey)
            continue

        key = (r // 32 * 32, g // 32 * 32, b // 32 * 32)
        buckets[key] = buckets.get(key, 0) + 1

    if not buckets:
        if fallback_n == 0:
            return None
        return (fallback_sum[0] // fallback_n,
                fallback_sum[1] // fallback_n,
                fallback_sum[2] // fallback_n)

    return max(buckets, key=buckets.get)


def tint_image(img: Image.Image, color: tuple[int, int, int], strength: float) -> Image.Image:
    """
    Blends `img` (any mode) toward a flat `color`, returning an RGB image.
    `strength` is the blend factor (0 = unchanged, 1 = solid color).
    """
    rgb = img.convert("RGB")
    if strength <= 0.001:
        return rgb
    strength = min(1.0, strength)
    overlay = Image.new("RGB", rgb.size, color)
    return Image.blend(rgb, overlay, strength)


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO SYNTHESIS
# ═══════════════════════════════════════════════════════════════════════════════
def gen_tick(sr: int = config.SAMPLE_RATE, impact: bool = False) -> np.ndarray:
    """Short percussive click. impact=True gives a deeper, louder sound for rank #1."""
    dur  = 0.14 if impact else 0.07
    t    = np.linspace(0, dur, int(sr * dur))
    if impact:
        w   = (0.50 * np.sin(2*np.pi*520*t) +
               0.30 * np.sin(2*np.pi*260*t) +
               0.20 * np.sin(2*np.pi*130*t))
        env = np.exp(-t * 16)
        amp = 0.55
    else:
        w   = np.sin(2*np.pi*1100*t)
        env = np.exp(-t * 55)
        amp = 0.25
    out = (w * env * amp).astype(np.float32)
    return np.stack([out, out], axis=1)


def gen_whoosh(duration: float = 0.35, sr: int = config.SAMPLE_RATE) -> np.ndarray:
    """Filtered-noise sweep ('whoosh') for cinematic transitions."""
    n      = max(1, int(sr * duration))
    noise  = np.random.randn(n).astype(np.float32)
    brown  = np.cumsum(noise)
    peak   = np.max(np.abs(brown))
    if peak > 0:
        brown /= peak
    t   = np.linspace(0, 1, n)
    env = np.sin(np.pi * t) ** 1.5   # rises then falls
    out = (brown * env * 0.35).astype(np.float32)
    return np.stack([out, out], axis=1)


def gen_ambient(duration: float, sr: int = config.SAMPLE_RATE) -> np.ndarray:
    """Simple ambient drone pad (A1 + harmonics with slow vibrato) as audio fallback."""
    t   = np.linspace(0, duration, int(sr * duration))
    pad = (0.38 * np.sin(2*np.pi*55*t)  +
           0.22 * np.sin(2*np.pi*110*t) +
           0.11 * np.sin(2*np.pi*165*t) +
           0.06 * np.sin(2*np.pi*220*t))
    pad *= 0.85 + 0.15 * np.sin(2*np.pi * 0.13 * t)
    fi   = np.clip(t / 1.8, 0, 1)
    fo   = np.clip((duration - t) / 1.8, 0, 1)
    pad  = (pad * fi * fo * 0.20).astype(np.float32)
    return np.stack([pad, pad], axis=1)


def next_match_music() -> Path:
    """
    Returns the next match-prediction-N.mp3 track (N in 0..MATCH_MUSIC_COUNT-1),
    rotating one step per call. The next index is persisted in
    config.MATCH_MUSIC_INDEX_FILE so consecutive renders use a different track.
    Falls back to track 0 if the counter file is missing/corrupt or unwritable.
    """
    import json

    try:
        idx = json.loads(config.MATCH_MUSIC_INDEX_FILE.read_text())["next"]
    except Exception:
        idx = 0

    idx = idx % config.MATCH_MUSIC_COUNT
    path = config.MUSIC_DIR / f"match-prediction-{idx}.mp3"

    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        next_idx = (idx + 1) % config.MATCH_MUSIC_COUNT
        config.MATCH_MUSIC_INDEX_FILE.write_text(json.dumps({"next": next_idx}))
    except Exception:
        pass

    return path


def load_music(duration: float,
               music_path: Path | None = None,
               sr: int = config.SAMPLE_RATE) -> np.ndarray | None:
    """
    Loads a music file as a (n_samples, 2) float32 array trimmed to duration.
    Tries MoviePy to_soundarray() first, falls back to ffmpeg subprocess.
    Returns None if the file does not exist or both methods fail.
    """
    path = music_path or config.MUSIC_FILE
    if not path.exists():
        return None

    n = int(sr * duration)

    # Attempt 1: MoviePy
    try:
        from moviepy import AudioFileClip
        mc  = AudioFileClip(str(path))
        arr = mc.subclipped(0, min(mc.duration, duration)).to_soundarray(fps=sr)
        mc.close()
        if arr.ndim == 1:
            arr = np.stack([arr, arr], axis=1)
        elif arr.shape[1] == 1:
            arr = np.repeat(arr, 2, axis=1)
        if len(arr) < n:
            arr = np.vstack([arr, np.zeros((n - len(arr), 2), dtype=np.float32)])
        return arr[:n].astype(np.float32)
    except Exception:
        pass

    # Attempt 2: ffmpeg subprocess
    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(path),
            "-f", "f32le", "-ar", str(sr), "-ac", "2",
            "-t", str(duration), "-loglevel", "quiet", "-",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0 and result.stdout:
            arr = np.frombuffer(result.stdout, dtype=np.float32)
            arr = arr.reshape(-1, 2) if len(arr) % 2 == 0 else arr[:-1].reshape(-1, 2)
            if len(arr) < n:
                arr = np.vstack([arr, np.zeros((n - len(arr), 2), dtype=np.float32)])
            return arr[:n].astype(np.float32)
    except Exception:
        pass

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# CREDENTIALS
# ═══════════════════════════════════════════════════════════════════════════════
def find_client_secret() -> Path:
    """
    Locates the Google OAuth2 client_secret*.json in the credentials directory.
    Accepts both the short name ('client_secret.json') and the long name
    generated automatically by Google Cloud Console.
    """
    for name in ("client_secret.json", "client_secrets.json"):
        p = config.CREDS_DIR / name
        if p.exists():
            return p
    matches = sorted(config.CREDS_DIR.glob("client_secret*.json"))
    if matches:
        return matches[0]
    raise FileNotFoundError(
        f"\nNo client_secret*.json found in: {config.CREDS_DIR}\n\n"
        "Steps to obtain it:\n"
        "  1. Google Cloud Console -> APIs & Services -> Credentials\n"
        "  2. Create OAuth 2.0 Client ID (type: Desktop application)\n"
        "  3. Download the JSON and place it in credentials/\n"
        "  4. Make sure YouTube Data API v3 is enabled in your project\n"
    )
