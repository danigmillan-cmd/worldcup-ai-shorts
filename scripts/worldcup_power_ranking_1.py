#!/usr/bin/env python3
"""
worldcup_power_ranking_1.py
Genera el vídeo "AI Power Ranking" del Mundial 2026.

Diferencias respecto a la v0:
  - Datos en tiempo real via World Football Elo Ratings (elo_rankings.py)
  - Musica desde assets/music/power-rankings.mp3
  - Duracion dinamica: termina 1 s despues de que #1 se revela completamente
  - Layout y estetica identicos (DAZN/ESPN style)
"""

import os
import sys
import math
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── Modulo de datos ELO ────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from elo_rankings import get_top10

# ── MoviePy 2.x ───────────────────────────────────────────────────────────────
from moviepy import VideoClip, AudioArrayClip

# ═══════════════════════════════════════════════════════════════════════════════
# RUTAS
# ═══════════════════════════════════════════════════════════════════════════════
ROOT       = Path(__file__).resolve().parent.parent
ASSETS     = ROOT / "assets"
FLAGS_DIR  = ASSETS / "flags"
BG_PATH    = ASSETS / "backgrounds" / "power_ranking_bg.png"
MUSIC_PATH = ASSETS / "music" / "power-rankings.mp3"
OUTPUT     = ROOT / "output" / "worldcup_power_ranking_1.mp4"

# ═══════════════════════════════════════════════════════════════════════════════
# CANVAS
# ═══════════════════════════════════════════════════════════════════════════════
W, H = 1080, 1920
FPS  = 30

# ═══════════════════════════════════════════════════════════════════════════════
# LAYOUT — mobile-safe margins para YouTube Shorts, TikTok e Instagram Reels
#
# Safe area horizontal: x=62 .. x=1014  (margenes laterales >=62px)
# Safe area vertical  : y=350 .. y=1720 (200px libres abajo para UI movil)
#
# Distribucion horizontal (total 960px utiles):
#   Rank  62-128  (66px)
#   Name 140-352  (212px)
#   Bar  360-820  (460px)
#   Pct  828-896  (68px)
#   Flag 904-1016 (112px x 84px)
#   Right margin: 1080-1016 = 64px
# ═══════════════════════════════════════════════════════════════════════════════
ROWS_Y0  = 350    # first slot top  (5px mas abajo para respirar en la cabecera)
ROW_H    = 126    # altura de cada slot
ROW_GAP  = 12     # separacion entre slots (mas aire)
ROW_STEP = ROW_H + ROW_GAP   # 138 (igual que antes, alineado con el fondo)

RANK_X   = 62     # margen izquierdo seguro  (era 18px)
NAME_X   = 140    # inicio del nombre de pais
BAR_X    = 360    # inicio de la barra
BAR_MAXW = 460    # anchura maxima de la barra (100%)
BAR_H    = 24     # altura de la barra (ligeramente mas compacta)
BAR_R    = 12     # radio de esquinas
PCT_X    = 828    # inicio del porcentaje
FLAG_X   = 904    # inicio de la bandera
FLAG_W   = 112    # anchura de la bandera
FLAG_H   = 84     # altura (ratio 4:3 = 112x84)

# ═══════════════════════════════════════════════════════════════════════════════
# PALETA
# ═══════════════════════════════════════════════════════════════════════════════
C_WHITE   = (255, 255, 255)
C_CYAN    = (80,  220, 200)
C_GOLD    = (255, 215,  30)
C_BAR     = (40,  210,  90)     # verde por defecto
C_BAR_LIT = (100, 255, 130)
C_GLOW    = (60,  240, 120)

# Colores de podio para las barras
C_GOLD_BAR   = (255, 200,  30)  # oro   (#1)
C_SILVER_BAR = (192, 200, 215)  # plata (#2)
C_BRONZE_BAR = (200, 120,  40)  # bronce (#3)

def _bar_color(rank: int) -> tuple:
    """Devuelve el color de la barra segun la posicion en el ranking."""
    return {1: C_GOLD_BAR, 2: C_SILVER_BAR, 3: C_BRONZE_BAR}.get(rank, C_BAR)

# ═══════════════════════════════════════════════════════════════════════════════
# TIMING
# ═══════════════════════════════════════════════════════════════════════════════
INTRO_T = 0.6    # segundos antes de que aparezca el primer equipo
SLOT_T  = 1.45   # presupuesto de tiempo por equipo
SR      = 44100  # sample rate de audio


def build_timings(ranking: list[dict]) -> list[dict]:
    """
    Genera el calendario de animacion para cada fila.
    screen_idx 0 = rank #1 (arriba), 9 = rank #10 (abajo).
    Orden de revelacion: #10 primero, #1 ultimo (de abajo hacia arriba).
    """
    timings = []
    for screen_idx in range(10):
        reveal_order = 9 - screen_idx   # 0 = Marruecos, 9 = Espana
        is_top       = (screen_idx == 0)
        t0           = INTRO_T + reveal_order * SLOT_T
        bar_dur      = 1.0 if is_top else 0.68   # #1 se rellena mas lento (drama)
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
    """Duracion total: el video termina 1 s despues de que #1 completa su glow."""
    return timings[0]["glow_end"] + 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# PRIMITIVAS DE DIBUJO
# ═══════════════════════════════════════════════════════════════════════════════
def _font(size: int, prefer_impact: bool = True) -> ImageFont.FreeTypeFont:
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


def _tw(font: ImageFont.FreeTypeFont, text: str) -> int:
    bb = font.getbbox(text)
    return bb[2] - bb[0]


def _th(font: ImageFont.FreeTypeFont, text: str = "Ag") -> int:
    bb = font.getbbox(text)
    return bb[3] - bb[1]


def _rrect(draw: ImageDraw.Draw, x: int, y: int,
           w: int, h: int, r: int, fill: tuple) -> None:
    """Rectangulo redondeado relleno."""
    if w <= 0 or h <= 0:
        return
    r = max(0, min(r, h // 2, w // 2))
    draw.rectangle([x + r, y, x + w - r, y + h],   fill=fill)
    draw.rectangle([x, y + r, x + w, y + h - r],   fill=fill)
    draw.ellipse  ([x,        y,        x+2*r, y+2*r], fill=fill)
    draw.ellipse  ([x+w-2*r,  y,        x+w,   y+2*r], fill=fill)
    draw.ellipse  ([x,        y+h-2*r,  x+2*r, y+h  ], fill=fill)
    draw.ellipse  ([x+w-2*r,  y+h-2*r,  x+w,   y+h  ], fill=fill)


def _shadow_text(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont,
                 x: int, y: int, fill: tuple, shadow_a: int = 110) -> None:
    """Texto con sombra difusa."""
    for ox, oy in ((2, 2), (2, -2), (-2, 2), (-2, -2)):
        draw.text((x + ox, y + oy), text, font=font, fill=(0, 0, 0, shadow_a))
    draw.text((x, y), text, font=font, fill=fill)


def _ease_out(t: float) -> float:
    return 1.0 - (1.0 - max(0.0, min(1.0, t))) ** 3


def _smooth(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


# ═══════════════════════════════════════════════════════════════════════════════
# BARRA CON GLOW
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_glow_bar(canvas: Image.Image, x: int, y: int,
                   w: int, h: int, color: tuple, glow: float = 0.0) -> None:
    """Barra con halo gaussiano opcional."""
    if w <= 2:
        return
    # Halo — usa el propio color de la barra (no verde fijo)
    if glow > 0.02:
        pad    = 14
        halo   = Image.new("RGBA", (w + 2*pad, h + 2*pad), (0, 0, 0, 0))
        hd     = ImageDraw.Draw(halo)
        glow_c = tuple(min(255, ch + 70) for ch in color)
        _rrect(hd, 0, 0, w + 2*pad, h + 2*pad, (h + 2*pad)//2,
               (*glow_c, int(140 * glow)))
        halo = halo.filter(ImageFilter.GaussianBlur(8))
        canvas.paste(halo, (x - pad, y - pad), halo)
    # Barra solida — siempre en su color real, ligeramente mas brillante si hay glow
    bar = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd  = ImageDraw.Draw(bar)
    if glow > 0.02:
        boost = int(45 * min(1.0, glow))
        c = tuple(min(255, ch + boost) for ch in color)
    else:
        c = color
    _rrect(bd, 0, 0, w, h, h // 2, (*c, 255))
    # Reflejo superior
    hl = max(2, h * 3 // 10)
    _rrect(bd, 2, 2, w - 4, hl, h // 2,
           (min(255, c[0]+70), min(255, c[1]+50), min(255, c[2]+50), 130))
    canvas.paste(bar, (x, y), bar)


# ═══════════════════════════════════════════════════════════════════════════════
# FILA DE RANKING
# ═══════════════════════════════════════════════════════════════════════════════
def _draw_row(canvas: Image.Image, idx: int, t: float,
              fonts: dict, flags: dict,
              ranking: list[dict], timings: list[dict], max_pct: int) -> None:
    """Renderiza una fila completa en su estado correspondiente al tiempo t."""
    team = ranking[idx]
    tm   = timings[idx]
    cy   = ROWS_Y0 + idx * ROW_STEP + ROW_H // 2

    if t < tm["start"]:
        return

    # ── Numero de ranking (aparece al inicio de la animacion) ────────────────
    rank_p = _smooth(min(1.0, (t - tm["start"]) / 0.18))
    is_top = (team["rank"] == 1)
    rank_c = C_GOLD if is_top else C_CYAN

    lyr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ld  = ImageDraw.Draw(lyr)

    rh = _th(fonts["rank"])
    _shadow_text(ld, f"#{team['rank']}", fonts["rank"],
                 RANK_X, cy - rh // 2,
                 fill=(*rank_c, int(255 * rank_p)))

    canvas.alpha_composite(lyr)

    # ── Barra + contador ───────────────────────────────────────────────────────
    if t < tm["bar_start"]:
        return

    bar_p  = _ease_out(min(1.0, (t - tm["bar_start"]) /
                            (tm["bar_end"] - tm["bar_start"])))
    fill_w = max(0, int(BAR_MAXW * (team["pct"] / max_pct) * bar_p))
    bar_y  = cy - BAR_H // 2

    # Glow: brilla de forma continua mientras se llena, se apaga al terminar
    filling = bar_p < 1.0
    if filling:
        # Brillo constante con respiracion muy lenta (0.4 Hz, casi imperceptible)
        glow = 0.65 + 0.15 * math.sin(t * math.pi * 0.8)
    elif t >= tm["glow_start"]:
        # Breve pulso de impacto al completarse, luego se apaga
        gp   = min(1.0, (t - tm["glow_start"]) /
                        (tm["glow_end"] - tm["glow_start"]))
        glow = math.sin(gp * math.pi) * 0.9
    else:
        glow = 0.0

    _draw_glow_bar(canvas, BAR_X, bar_y, fill_w, BAR_H, _bar_color(team["rank"]), glow)

    # Contador de porcentaje
    pct_txt = f"{int(team['pct'] * bar_p)}%"
    ph  = _th(fonts["pct"])
    pl  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pd  = ImageDraw.Draw(pl)
    _shadow_text(pd, pct_txt, fonts["pct"], PCT_X, cy - ph // 2 - 1, C_WHITE)
    canvas.alpha_composite(pl)

    # ── Bandera ────────────────────────────────────────────────────────────────
    if t < tm["flag_start"]:
        return

    flag_a = _smooth(min(1.0, (t - tm["flag_start"]) /
                              (tm["flag_end"] - tm["flag_start"])))

    # Nombre del pais: aparece junto a la bandera
    nl  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    nld = ImageDraw.Draw(nl)
    nh  = _th(fonts["name"])
    _shadow_text(nld, team["name"], fonts["name"],
                 NAME_X, cy - nh // 2,
                 fill=(*C_WHITE, int(255 * flag_a)))
    canvas.alpha_composite(nl)

    flag   = flags.get(team["code"])
    if flag and flag_a > 0.01:
        fa = int(255 * flag_a)
        f2 = flag.copy()
        r, g, b, a = f2.split()
        a = a.point(lambda v: v * fa // 255)
        f2 = Image.merge("RGBA", (r, g, b, a))
        canvas.paste(f2, (FLAG_X, cy - FLAG_H // 2), f2)


def _draw_active_highlight(canvas: Image.Image,
                           idx: int, intensity: float) -> None:
    """Resplandor sutil sobre la fila activa."""
    if intensity < 0.02:
        return
    pad  = 6
    row_y = ROWS_Y0 + idx * ROW_STEP
    glow  = Image.new("RGBA", (W - 80, ROW_H + 2*pad), (0, 0, 0, 0))
    gd    = ImageDraw.Draw(glow)
    _rrect(gd, 0, 0, W - 80, ROW_H + 2*pad, 12,
           (*C_GLOW, int(50 * intensity)))
    glow  = glow.filter(ImageFilter.GaussianBlur(12))
    canvas.paste(glow, (40, row_y - pad), glow)


# ═══════════════════════════════════════════════════════════════════════════════
# FONDO + SUBTITULO
# ═══════════════════════════════════════════════════════════════════════════════
def _prepare_bg(font_sub: ImageFont.FreeTypeFont) -> Image.Image:
    bg = Image.open(BG_PATH).convert("RGBA").resize((W, H), Image.LANCZOS)
    d  = ImageDraw.Draw(bg)
    sub = "AI POWER RANKING"
    sw  = _tw(font_sub, sub)
    sx  = (W - sw) // 2
    d.text((sx + 2, 295), sub, font=font_sub, fill=(0, 80, 60, 160))
    d.text((sx,     295), sub, font=font_sub, fill=(*C_CYAN, 220))
    return bg


# ═══════════════════════════════════════════════════════════════════════════════
# ZOOM LENTO
# ═══════════════════════════════════════════════════════════════════════════════
def _zoom(img: Image.Image, factor: float) -> Image.Image:
    if factor <= 1.001:
        return img
    nw = int(W * factor)
    nh = int(H * factor)
    z  = img.resize((nw, nh), Image.BILINEAR)
    x0 = (nw - W) // 2
    y0 = (nh - H) // 2
    return z.crop((x0, y0, x0 + W, y0 + H))


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO
# ═══════════════════════════════════════════════════════════════════════════════
def _gen_tick(sr: int = SR, impact: bool = False) -> np.ndarray:
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
    result = (w * env * amp).astype(np.float32)
    return np.stack([result, result], axis=1)


def _gen_ambient(duration: float, sr: int = SR) -> np.ndarray:
    """Pad ambiental de respaldo (si no hay archivo de musica)."""
    t   = np.linspace(0, duration, int(sr * duration))
    pad = (0.38 * np.sin(2*np.pi*55*t) +
           0.22 * np.sin(2*np.pi*110*t) +
           0.11 * np.sin(2*np.pi*165*t) +
           0.06 * np.sin(2*np.pi*220*t))
    pad *= 0.85 + 0.15 * np.sin(2*np.pi * 0.13 * t)
    fi = np.clip(t / 1.8, 0, 1)
    fo = np.clip((duration - t) / 1.8, 0, 1)
    pad = (pad * fi * fo * 0.20).astype(np.float32)
    return np.stack([pad, pad], axis=1)


def _load_music(duration: float) -> np.ndarray | None:
    """
    Carga la musica de fondo como array numpy (rapido via ffmpeg o to_soundarray).
    Retorna array float32 de forma (n_samples, 2) o None si falla.
    """
    if not MUSIC_PATH.exists():
        return None

    n = int(SR * duration)

    # Intento 1: to_soundarray() de MoviePy (disponible en v1 y algunos builds v2)
    try:
        from moviepy import AudioFileClip
        mc   = AudioFileClip(str(MUSIC_PATH))
        trim = min(mc.duration, duration)
        arr  = mc.subclipped(0, trim).to_soundarray(fps=SR)
        mc.close()
        # Asegurar estereo
        if arr.ndim == 1:
            arr = np.stack([arr, arr], axis=1)
        elif arr.shape[1] == 1:
            arr = np.repeat(arr, 2, axis=1)
        # Ajustar longitud
        if len(arr) < n:
            arr = np.vstack([arr, np.zeros((n - len(arr), 2), dtype=np.float32)])
        arr = arr[:n].astype(np.float32)
        print("  Musica cargada via to_soundarray()")
        return arr
    except Exception:
        pass

    # Intento 2: ffmpeg directo (siempre disponible si MoviePy esta instalado)
    try:
        import subprocess
        cmd = [
            "ffmpeg", "-y", "-i", str(MUSIC_PATH),
            "-f", "f32le", "-ar", str(SR), "-ac", "2",
            "-t", str(duration),
            "-loglevel", "quiet", "-",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=60)
        if result.returncode == 0 and result.stdout:
            arr = np.frombuffer(result.stdout, dtype=np.float32)
            # ffmpeg f32le interleaved → (n, 2)
            if len(arr) % 2 == 0:
                arr = arr.reshape(-1, 2)
            else:
                arr = arr[:-1].reshape(-1, 2)
            if len(arr) < n:
                arr = np.vstack([arr, np.zeros((n - len(arr), 2), dtype=np.float32)])
            arr = arr[:n].astype(np.float32)
            print("  Musica cargada via ffmpeg subprocess")
            return arr
    except Exception as e:
        print(f"  ffmpeg: {e}")

    return None


def build_audio(duration: float, timings: list[dict]) -> tuple:
    """
    Mezcla la musica de fondo con sonidos de tick en cada revelacion.
    Retorna (audio_array float32, sample_rate) o (None, None).
    """
    n = int(SR * duration)

    # ── Musica de fondo ────────────────────────────────────────────────────────
    music_arr = _load_music(duration)
    if music_arr is not None:
        # Fade out ultimos 2 s
        fade_s  = int(SR * 2.0)
        fs      = max(0, n - fade_s)
        ramp    = np.linspace(1.0, 0.0, n - fs, dtype=np.float32)
        music_arr[fs:, 0] *= ramp
        music_arr[fs:, 1] *= ramp
        base = music_arr * 0.75
        print("  Musica: power-rankings.mp3")
    else:
        print("  Musica no disponible, usando pad ambiental")
        base = _gen_ambient(duration)

    # ── Ticks por equipo ───────────────────────────────────────────────────────
    ticks = np.zeros((n, 2), dtype=np.float32)
    for i, tm in enumerate(timings):
        tick = _gen_tick(SR, impact=(i == 0))
        si   = int(tm["glow_start"] * SR)
        ei   = min(si + len(tick), n)
        if si < n:
            ticks[si:ei] += tick[:ei - si] * 0.40

    audio = np.clip(base + ticks, -1.0, 1.0).astype(np.float32)
    return audio, SR


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTRUCTOR DE FRAMES  (closure — carga assets una sola vez)
# ═══════════════════════════════════════════════════════════════════════════════
def make_frame_builder(ranking: list[dict],
                       max_pct: int,
                       timings: list[dict],
                       duration: float):
    """Retorna make_frame(t) listo para VideoClip."""
    print("Cargando assets visuales...")

    fonts = {
        "rank":   _font(44, prefer_impact=True),
        "name":   _font(34, prefer_impact=True),
        "pct":    _font(38, prefer_impact=False),
        "sub":    _font(40, prefer_impact=False),
        "footer": _font(30, prefer_impact=False),
    }

    bg = _prepare_bg(fonts["sub"])

    flags: dict[str, Image.Image | None] = {}
    for team in ranking:
        p = FLAGS_DIR / f"{team['code']}.png"
        if p.exists():
            img = Image.open(p).convert("RGBA")
            flags[team["code"]] = img.resize((FLAG_W, FLAG_H), Image.LANCZOS)
        else:
            flags[team["code"]] = None
            print(f"  [aviso] bandera no encontrada: {p.name}")

    def make_frame(t: float) -> np.ndarray:
        canvas = bg.copy()

        # Highlight de la fila activa
        for idx in range(10):
            tm = timings[idx]
            if tm["start"] <= t < tm["glow_end"]:
                prog = min(1.0, (t - tm["start"]) / (tm["glow_end"] - tm["start"]))
                _draw_active_highlight(canvas, idx, math.sin(prog * math.pi) * 0.6)

        # Todas las filas
        for idx in range(10):
            _draw_row(canvas, idx, t, fonts, flags, ranking, timings, max_pct)

        # Footer
        if t > INTRO_T + 1.0:
            fa   = min(1.0, (t - INTRO_T - 1.0) / 1.0)
            fl   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            fd   = ImageDraw.Draw(fl)
            ftxt = "AI WORLD CUP ANALYTICS"
            fw   = _tw(fonts["footer"], ftxt)
            fd.text(((W - fw)//2, H - 205), ftxt,
                    font=fonts["footer"], fill=(*C_CYAN, int(160 * fa)))
            canvas.alpha_composite(fl)

        # Zoom lento (1.0x → 1.04x)
        z = 1.0 + 0.04 * (t / duration)
        canvas = _zoom(canvas, z)

        return np.array(canvas.convert("RGB"))

    return make_frame


# ═══════════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    OUTPUT.parent.mkdir(exist_ok=True)

    # 1. Datos ELO
    ranking = get_top10(flags_dir=FLAGS_DIR)
    max_pct = max(t["pct"] for t in ranking)
    timings = build_timings(ranking)
    duration = compute_duration(timings)

    print(f"\nDuracion calculada: {duration:.1f} s")
    print(f"Resolucion: {W}x{H}  FPS: {FPS}\n")

    # 2. Video
    make_frame = make_frame_builder(ranking, max_pct, timings, duration)
    clip = VideoClip(make_frame, duration=duration)

    # 3. Audio
    print("Construyendo audio...")
    audio_arr, sr = build_audio(duration, timings)
    if audio_arr is not None:
        try:
            audio_clip = AudioArrayClip(audio_arr, fps=sr)
            clip = clip.with_audio(audio_clip)
            print("  Audio OK")
        except Exception as e:
            print(f"  Audio omitido: {e}")

    # 4. Exportar
    out = str(OUTPUT)
    print(f"\nExportando: {out}")
    clip.write_videofile(
        out,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        ffmpeg_params=["-crf", "20"],
        logger="bar",
    )
    print(f"\nListo: {out}")
    print(f"Tamano: {OUTPUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
