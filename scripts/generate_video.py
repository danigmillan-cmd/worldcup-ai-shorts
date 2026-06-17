#!/usr/bin/env python3
"""
Genera un vídeo vertical 1080×1920 estilo TikTok/Shorts
para el partido España vs Brasil con probabilidades animadas.

Requisitos: moviepy, pillow
"""

import os
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import VideoClip

# ── Configuración ──────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1080, 1920
DURATION      = 20
FPS           = 30

SPAIN_PCT  = 42
BRAZIL_PCT = 58

# Paleta
C_BG      = (8,   10,  25)
C_WHITE   = (255, 255, 255)
C_GRAY    = (145, 150, 175)
C_SPAIN   = (198,  11,  30)
C_YELLOW  = (252, 209,  22)
C_BRAZIL  = (0,   155,  58)
C_BLUE_BR = (0,    39, 118)
C_GOLD    = (255, 190,  30)
C_DIM     = (18,   20,  48)
C_LINE    = (45,   50,  85)


# ── Fuentes ────────────────────────────────────────────────────────────────────
def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    bold_paths = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    reg_paths = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in (bold_paths if bold else reg_paths):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


# ── Utilidades de dibujo ──────────────────────────────────────────────────────
def text_w(font: ImageFont.FreeTypeFont, text: str) -> int:
    bb = font.getbbox(text)
    return bb[2] - bb[0]


def draw_centered(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont,
                  y: int, color=C_WHITE, cx: int = WIDTH // 2) -> None:
    x = cx - text_w(font, text) // 2
    draw.text((x, y), text, font=font, fill=color)


def rounded_rect(draw: ImageDraw.Draw, x: int, y: int, w: int, h: int,
                 r: int, color: tuple) -> None:
    r = max(0, min(r, h // 2, w // 2))
    draw.rectangle([x + r, y,     x + w - r, y + h    ], fill=color)
    draw.rectangle([x,     y + r, x + w,     y + h - r], fill=color)
    for ex, ey in [(x, y), (x + w - 2*r, y), (x, y + h - 2*r), (x + w - 2*r, y + h - 2*r)]:
        draw.ellipse([ex, ey, ex + 2*r, ey + 2*r], fill=color)


def divider(draw: ImageDraw.Draw, y: int, alpha: int = 60) -> None:
    c = (alpha, alpha + 5, alpha + 20)
    draw.line([(80, y), (WIDTH - 80, y)], fill=c, width=2)


# ── Banderas (dibujadas con Pillow) ───────────────────────────────────────────
def draw_spain_flag(canvas: Image.Image, x: int, y: int, w: int, h: int) -> None:
    """Bandera de España: rojo-amarillo-rojo."""
    flag = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(flag)
    q = h // 4
    d.rectangle([0, 0,       w, q],     fill=(*C_SPAIN,  255))
    d.rectangle([0, q,       w, h - q], fill=(*C_YELLOW, 255))
    d.rectangle([0, h - q,   w, h],     fill=(*C_SPAIN,  255))
    # Franja central ligeramente más intensa
    d.rectangle([0, q - 2,   w, h - q + 2], fill=(*C_YELLOW, 255))
    # Escudo simplificado
    cw, ch = w // 7, h // 3
    cx_s, cy_s = w // 2 - cw // 2, h // 2 - ch // 2
    d.rectangle([cx_s, cy_s, cx_s + cw, cy_s + ch], fill=(110, 5, 18, 230))
    canvas.paste(flag, (x, y), flag)


def draw_brazil_flag(canvas: Image.Image, x: int, y: int, w: int, h: int) -> None:
    """Bandera de Brasil: verde + rombo amarillo + círculo azul."""
    flag = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(flag)
    d.rectangle([0, 0, w, h], fill=(*C_BRAZIL, 255))
    cx, cy = w // 2, h // 2
    dw, dh = int(w * 0.82), int(h * 0.68)
    diamond = [
        (cx,        cy - dh // 2),
        (cx + dw // 2, cy),
        (cx,        cy + dh // 2),
        (cx - dw // 2, cy),
    ]
    d.polygon(diamond, fill=(*C_YELLOW, 255))
    r = int(min(w, h) * 0.265)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*C_BLUE_BR, 255))
    band = max(3, r // 5)
    d.rectangle([cx - r, cy - band, cx + r, cy + band], fill=(255, 255, 255, 160))
    canvas.paste(flag, (x, y), flag)


# ── Fondo animado ──────────────────────────────────────────────────────────────
def draw_background(img: Image.Image, t: float) -> Image.Image:
    arr = np.array(img, dtype=np.float32)
    for i in range(5):
        phase = t * 0.3 + i * (math.pi * 2 / 5)
        cy = int(HEIGHT * (0.1 + 0.18 * i) + 50 * math.sin(phase))
        brightness = 5 + 3 * math.sin(phase * 1.4)
        for dy in range(-70, 71):
            row = cy + dy
            if 0 <= row < HEIGHT:
                decay = max(0.0, 1.0 - abs(dy) / 70.0)
                arr[row] = np.clip(arr[row] + brightness * decay, 0, 255)
    # Subtle diagonal shimmer
    shimmer_x = int((WIDTH + 200) * ((t * 0.15) % 1.0)) - 100
    for dx in range(-40, 41):
        col = shimmer_x + dx
        if 0 <= col < WIDTH:
            decay = max(0.0, 1.0 - abs(dx) / 40.0)
            arr[:, col] = np.clip(arr[:, col] + 4 * decay, 0, 255)
    return Image.fromarray(arr.astype(np.uint8))


# ── Frame builder ──────────────────────────────────────────────────────────────
def make_frame_builder():
    fonts = {
        "header":  load_font(38),
        "title":   load_font(115, bold=True),
        "sub":     load_font(62,  bold=True),
        "country": load_font(60,  bold=True),
        "pct_big": load_font(115, bold=True),
        "bar_lbl": load_font(46,  bold=True),
        "stats_lbl": load_font(36),
        "stats_val": load_font(46, bold=True),
        "footer":  load_font(34),
    }

    # Posiciones fijas de los centros de cada equipo
    FLAG_W, FLAG_H = 290, 195
    SPAIN_CX  = 80  + FLAG_W // 2          # ~225
    BRAZIL_CX = WIDTH - 80 - FLAG_W // 2   # ~855

    def make_frame(t: float) -> np.ndarray:
        img = Image.new("RGB", (WIDTH, HEIGHT), C_BG)
        img = draw_background(img, t)
        draw = ImageDraw.Draw(img)

        # Animación de entrada suave (0 → 0.7 s)
        fade = min(1.0, t / 0.7)

        # ── CABECERA ───────────────────────────────────────────────────────────
        Y = 70
        draw_centered(draw, "MUNDIAL 2026  ·  IA PREDICCIÓN",
                      fonts["header"], Y, C_GRAY)
        divider(draw, Y + 56, alpha=45)

        # ── TÍTULO PRINCIPAL ───────────────────────────────────────────────────
        Y = 165
        draw_centered(draw, "España vs Brasil", fonts["title"], Y, C_WHITE)

        # ── SUBTÍTULO ──────────────────────────────────────────────────────────
        Y = 300
        draw_centered(draw, "¿Quién ganará?", fonts["sub"], Y, C_GOLD)

        divider(draw, Y + 86, alpha=55)

        # ── BANDERAS ───────────────────────────────────────────────────────────
        FLAG_Y = Y + 115
        draw_spain_flag(img,  80,              FLAG_Y, FLAG_W, FLAG_H)
        draw_brazil_flag(img, WIDTH - 80 - FLAG_W, FLAG_Y, FLAG_W, FLAG_H)

        # ── VS (pulsante) ──────────────────────────────────────────────────────
        pulse = 1.0 + 0.05 * math.sin(t * math.pi * 2.2)
        vs_color = tuple(int(min(255, c * pulse)) for c in C_GOLD)
        vs_y = FLAG_Y + FLAG_H // 2 - 48
        draw_centered(draw, "VS", fonts["sub"], vs_y, vs_color)

        # ── NOMBRES DE PAÍSES ──────────────────────────────────────────────────
        NAME_Y = FLAG_Y + FLAG_H + 22
        draw_centered(draw, "ESPAÑA", fonts["country"], NAME_Y, C_WHITE, SPAIN_CX)
        draw_centered(draw, "BRASIL", fonts["country"], NAME_Y, C_WHITE, BRAZIL_CX)

        # ── PORCENTAJES GRANDES ────────────────────────────────────────────────
        PCT_Y = NAME_Y + 72
        draw_centered(draw, f"{SPAIN_PCT}%",  fonts["pct_big"], PCT_Y, C_SPAIN,  SPAIN_CX)
        draw_centered(draw, f"{BRAZIL_PCT}%", fonts["pct_big"], PCT_Y, C_GOLD,   BRAZIL_CX)

        divider(draw, PCT_Y + 130, alpha=55)

        # ── SECCIÓN DE BARRAS ──────────────────────────────────────────────────
        BARS_Y = PCT_Y + 160
        draw_centered(draw, "PROBABILIDAD DE VICTORIA",
                      fonts["stats_lbl"], BARS_Y, C_GRAY)

        BAR_X = 80
        BAR_W = WIDTH - 160
        BAR_H = 38
        RADIUS = 19

        # Llenado animado: arranca a t=0.5 s y tarda 2.5 s en completarse
        fill = min(1.0, max(0.0, (t - 0.5) / 2.5))
        # Efecto de "rebote" al final del llenado
        if fill >= 1.0:
            bounce = 1.0 + 0.015 * math.sin((t - 3.0) * 8)
        else:
            bounce = 1.0

        # Barra España
        B1_Y = BARS_Y + 56
        draw.text((BAR_X, B1_Y - 46), "ESPAÑA",  font=fonts["bar_lbl"], fill=C_WHITE)
        e_lbl = f"{SPAIN_PCT}%"
        draw.text((BAR_X + BAR_W - text_w(fonts["bar_lbl"], e_lbl), B1_Y - 46),
                  e_lbl, font=fonts["bar_lbl"], fill=C_SPAIN)
        rounded_rect(draw, BAR_X, B1_Y, BAR_W, BAR_H, RADIUS, C_DIM)
        spain_w = max(RADIUS * 2 + 2, int(BAR_W * (SPAIN_PCT / 100) * fill * bounce))
        rounded_rect(draw, BAR_X, B1_Y, spain_w, BAR_H, RADIUS, C_SPAIN)

        # Barra Brasil
        B2_Y = B1_Y + 105
        draw.text((BAR_X, B2_Y - 46), "BRASIL",  font=fonts["bar_lbl"], fill=C_WHITE)
        b_lbl = f"{BRAZIL_PCT}%"
        draw.text((BAR_X + BAR_W - text_w(fonts["bar_lbl"], b_lbl), B2_Y - 46),
                  b_lbl, font=fonts["bar_lbl"], fill=C_GOLD)
        rounded_rect(draw, BAR_X, B2_Y, BAR_W, BAR_H, RADIUS, C_DIM)
        brazil_w = max(RADIUS * 2 + 2, int(BAR_W * (BRAZIL_PCT / 100) * fill * bounce))
        rounded_rect(draw, BAR_X, B2_Y, brazil_w, BAR_H, RADIUS, C_BRAZIL)

        divider(draw, B2_Y + 80, alpha=55)

        # ── ESTADÍSTICAS ADICIONALES ───────────────────────────────────────────
        STATS_Y = B2_Y + 110
        stats = [
            ("RANKING FIFA",      "8°",      "4°"),
            ("FORMA RECIENTE",    "W W D",   "W W W"),
            ("GOL. PROMEDIO",     "2.1",     "2.6"),
            ("POSESIÓN MEDIA",    "58%",     "54%"),
        ]
        ROW_H = 115

        for i, (label, val_e, val_b) in enumerate(stats):
            row_y = STATS_Y + i * ROW_H
            # Etiqueta centrada
            draw_centered(draw, label, fonts["stats_lbl"], row_y, C_GRAY)
            # Valores de cada equipo bajo sus banderas
            draw_centered(draw, val_e, fonts["stats_val"], row_y + 42, C_WHITE, SPAIN_CX)
            draw_centered(draw, val_b, fonts["stats_val"], row_y + 42, C_WHITE, BRAZIL_CX)
            # Línea separadora fina entre filas (excepto la última)
            if i < len(stats) - 1:
                sep_y = row_y + ROW_H - 10
                draw.line([(BAR_X, sep_y), (BAR_X + BAR_W, sep_y)],
                          fill=(25, 27, 55), width=1)

        # ── FOOTER ─────────────────────────────────────────────────────────────
        FOOTER_Y = HEIGHT - 100
        divider(draw, FOOTER_Y - 22, alpha=45)
        draw_centered(draw, "AI SPORTS ANALYTICS  |  worldcup-ai-shorts",
                      fonts["footer"], FOOTER_Y, C_GRAY)

        return np.array(img)

    return make_frame


# ── Punto de entrada ──────────────────────────────────────────────────────────
def main():
    os.makedirs("output", exist_ok=True)
    out_path = "output/test.mp4"

    print(f"Generando vídeo {WIDTH}×{HEIGHT} · {DURATION}s · {FPS}fps …")
    clip = VideoClip(make_frame_builder(), duration=DURATION)

    clip.write_videofile(
        out_path,
        fps=FPS,
        codec="libx264",
        audio=False,
        preset="medium",
        ffmpeg_params=["-crf", "22"],
        logger="bar",
    )
    print(f"\nListo! Exportado -> {out_path}")


if __name__ == "__main__":
    main()
