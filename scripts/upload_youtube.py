#!/usr/bin/env python3
"""
upload_youtube.py
Sube un video a YouTube Shorts usando el flujo oficial OAuth2 Desktop Application.

Primera ejecucion:
    - Abre el navegador para autenticarte con Google
    - Guarda el token en credentials/token.json (no vuelve a pedir login)

Uso:
    python scripts/upload_youtube.py                   # sube como publico
    python scripts/upload_youtube.py --private         # sube como privado
    python scripts/upload_youtube.py --unlisted        # sube como no listado
    python scripts/upload_youtube.py --file output/otro.mp4 --title "Titulo"
"""

import os
import sys
import time
import random
import argparse
from pathlib import Path

# Forzar UTF-8 en la consola de Windows para que los emojis no rompan el print
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# ── Google Auth (flujo oficial Desktop Application) ───────────────────────────
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# ═══════════════════════════════════════════════════════════════════════════════
# RUTAS
# ═══════════════════════════════════════════════════════════════════════════════
ROOT       = Path(__file__).resolve().parent.parent
CREDS_DIR  = ROOT / "credentials"
TOKEN_JSON = CREDS_DIR / "token.json"        # formato JSON estándar de Google
OUTPUT_DIR = ROOT / "output"

# ═══════════════════════════════════════════════════════════════════════════════
# METADATOS DEL VIDEO
# ═══════════════════════════════════════════════════════════════════════════════
DEFAULT_VIDEO = OUTPUT_DIR / "worldcup_power_ranking_1.mp4"

DEFAULT_TITLE = "AI Predicts The World Cup Winner \U0001f30d⚽"

DEFAULT_DESCRIPTION = """\
AI-powered World Cup 2026 power rankings based on Elo ratings and football analytics.

Which team do you think will win? Drop your prediction in the comments!

#WorldCup #WorldCup2026 #Football #Soccer #AI #PowerRanking #Shorts #FIFA #Sports"""

DEFAULT_TAGS = [
    "World Cup", "World Cup 2026", "FIFA", "Football", "Soccer",
    "AI", "Power Ranking", "Elo Rating", "Shorts", "Sports",
    "Predictions", "Analytics",
]

CATEGORY_ID = "17"   # Sports — https://developers.google.com/youtube/v3/docs/videoCategories

# ═══════════════════════════════════════════════════════════════════════════════
# OAUTH2 — scope mínimo necesario para subir videos
# ═══════════════════════════════════════════════════════════════════════════════
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Configuracion de reintentos para errores transitorios
MAX_RETRIES          = 6
RETRIABLE_STATUS     = {500, 502, 503, 504}
RETRIABLE_EXCEPTIONS = (IOError, TimeoutError)
CHUNK_SIZE           = 4 * 1024 * 1024   # 4 MB por chunk


# ═══════════════════════════════════════════════════════════════════════════════
# PASO 1 — Buscar el archivo client_secret descargado de Google Cloud Console
# ═══════════════════════════════════════════════════════════════════════════════
def find_client_secret() -> Path:
    """
    Localiza client_secret*.json en credentials/.
    Acepta el nombre corto 'client_secret.json' o el nombre largo que genera
    Google Cloud Console automaticamente.
    """
    for name in ["client_secret.json", "client_secrets.json"]:
        p = CREDS_DIR / name
        if p.exists():
            return p

    matches = sorted(CREDS_DIR.glob("client_secret*.json"))
    if matches:
        return matches[0]

    raise FileNotFoundError(
        f"\nNo se encontro client_secret*.json en: {CREDS_DIR}\n\n"
        "Pasos para obtenerlo:\n"
        "  1. Google Cloud Console -> APIs & Services -> Credentials\n"
        "  2. Crea o selecciona OAuth 2.0 Client ID (tipo: Desktop application)\n"
        "  3. Descarga el JSON y guardalo en credentials/\n"
        "  4. Asegurate de que YouTube Data API v3 este habilitada\n"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PASO 2 — Autenticacion OAuth2 (flujo oficial InstalledAppFlow)
# ═══════════════════════════════════════════════════════════════════════════════
def authenticate() -> object:
    """
    Autentica con OAuth2 Desktop Application flow.

    - Si ya existe token.json valido: lo reutiliza (sin abrir navegador).
    - Si el token ha expirado: lo refresca automaticamente.
    - Si no existe o es invalido: abre el navegador para hacer login.

    Retorna un cliente autenticado de la YouTube Data API v3.
    """
    creds = None

    # ── Cargar token existente ────────────────────────────────────────────────
    if TOKEN_JSON.exists():
        print("  Cargando token guardado...")
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_JSON), SCOPES)
        except Exception as e:
            print(f"  Token corrupto o invalido ({e}), se pedira nuevo login.")
            TOKEN_JSON.unlink(missing_ok=True)
            creds = None

    # ── Validar / refrescar / pedir nuevo login ───────────────────────────────
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("  Token expirado — refrescando automaticamente...")
            try:
                creds.refresh(Request())
                print("  Token refrescado correctamente.")
            except Exception as e:
                print(f"  No se pudo refrescar ({e}). Se pedira nuevo login.")
                TOKEN_JSON.unlink(missing_ok=True)
                creds = None

        if not creds:
            client_secret_file = find_client_secret()
            print(f"  Credenciales: {client_secret_file.name}")
            print()
            print("  Abriendo navegador para autenticacion con Google...")
            print("  (Si no se abre, copia la URL que aparezca en la consola)")
            print()

            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret_file),
                scopes=SCOPES,
            )
            # port=0 elige un puerto libre automaticamente
            creds = flow.run_local_server(
                port=0,
                prompt="consent",
                access_type="offline",
            )

        # ── Guardar token en JSON (formato estandar de Google) ────────────────
        CREDS_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_JSON, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"  Token guardado en: {TOKEN_JSON.relative_to(ROOT)}")

    print("  Autenticacion correcta.")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


# ═══════════════════════════════════════════════════════════════════════════════
# PASO 3 — Subida con progreso y reintentos exponenciales
# ═══════════════════════════════════════════════════════════════════════════════
def upload_video(
    youtube,
    video_path: Path,
    title: str,
    description: str,
    tags: list,
    privacy: str,
) -> str:
    """
    Sube el video a YouTube usando upload resumable con progreso en tiempo real.
    Aplica backoff exponencial ante errores transitorios del servidor.

    Retorna el video_id del video subido.
    Lanza una excepcion si la subida falla definitivamente.
    """
    file_size_mb = video_path.stat().st_size / 1024 / 1024

    print(f"  Archivo  : {video_path.name}  ({file_size_mb:.1f} MB)")
    print(f"  Titulo   : {title}")
    print(f"  Privacy  : {privacy}")
    print()

    body = {
        "snippet": {
            "title":           title,
            "description":     description,
            "tags":            tags,
            "categoryId":      CATEGORY_ID,
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
        chunksize=CHUNK_SIZE,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    # ── Bucle de subida con barra de progreso ─────────────────────────────────
    response   = None
    retry      = 0
    start_time = time.time()

    print("  Subiendo", end="", flush=True)

    while response is None:
        try:
            status, response = request.next_chunk()

            if status:
                pct     = int(status.progress() * 100)
                elapsed = max(time.time() - start_time, 0.1)
                speed   = (status.resumable_progress / elapsed) / 1024 / 1024
                done    = int(pct / 5)
                bar     = "#" * done + "-" * (20 - done)
                print(f"\r  [{bar}] {pct:3d}%  ({speed:.1f} MB/s)", end="", flush=True)

            retry = 0   # reset tras chunk exitoso

        except HttpError as exc:
            status_code = exc.resp.status
            if status_code in RETRIABLE_STATUS and retry < MAX_RETRIES:
                wait = (2 ** retry) + random.random()
                print(f"\n  Error HTTP {status_code} — reintentando en {wait:.1f}s...")
                time.sleep(wait)
                retry += 1
            else:
                raise RuntimeError(
                    f"Error HTTP {status_code}: {exc.reason}\n"
                    f"Detalle: {exc.error_details}"
                ) from exc

        except RETRIABLE_EXCEPTIONS as exc:
            if retry < MAX_RETRIES:
                wait = (2 ** retry) + random.random()
                print(f"\n  Error de red ({exc}) — reintentando en {wait:.1f}s...")
                time.sleep(wait)
                retry += 1
            else:
                raise RuntimeError(f"Demasiados errores de red: {exc}") from exc

    elapsed_total = time.time() - start_time
    print(f"\r  [####################] 100%  (completado en {elapsed_total:.0f}s)")

    return response["id"]


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Sube un video a YouTube Shorts (OAuth2 Desktop App flow)"
    )
    p.add_argument(
        "--file", type=Path, default=DEFAULT_VIDEO,
        metavar="VIDEO",
        help="Ruta al archivo .mp4 (default: output/worldcup_power_ranking_1.mp4)",
    )
    p.add_argument("--title",    default=DEFAULT_TITLE,       help="Titulo del video")
    p.add_argument("--desc",     default=DEFAULT_DESCRIPTION, help="Descripcion del video")
    p.add_argument("--private",  action="store_true", help="Subir como privado")
    p.add_argument("--unlisted", action="store_true", help="Subir como no listado")
    p.add_argument("--reauth",   action="store_true", help="Forzar nuevo login (borra el token)")
    return p


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    args = build_parser().parse_args()

    # Borrar token si se pide re-autenticacion
    if args.reauth and TOKEN_JSON.exists():
        TOKEN_JSON.unlink()
        print("Token eliminado. Se pedira nuevo login.\n")

    # Determinar privacidad
    if args.private:
        privacy = "private"
    elif args.unlisted:
        privacy = "unlisted"
    else:
        privacy = "public"

    # Verificar que el video existe
    video_path = Path(args.file)
    if not video_path.exists():
        print(f"ERROR: No se encontro el archivo de video: {video_path}")
        print(f"       Ejecuta primero: python scripts/worldcup_power_ranking_1.py")
        sys.exit(1)

    # ── Cabecera ──────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  YouTube Shorts Uploader  |  World Cup AI 2026")
    print("=" * 60)

    # ── PASO 1: Autenticacion ─────────────────────────────────────────────────
    print()
    print("[1/3] AUTENTICACION")
    print("-" * 60)
    try:
        youtube = authenticate()
    except FileNotFoundError as exc:
        print(exc)
        sys.exit(1)
    except Exception as exc:
        print(f"  ERROR durante autenticacion: {exc}")
        sys.exit(1)

    # ── PASO 2: Subida ────────────────────────────────────────────────────────
    print()
    print("[2/3] SUBIDA DEL VIDEO")
    print("-" * 60)
    try:
        video_id = upload_video(
            youtube,
            video_path  = video_path,
            title       = args.title,
            description = args.desc,
            tags        = DEFAULT_TAGS,
            privacy     = privacy,
        )
    except RuntimeError as exc:
        print(f"\n  ERROR en la subida:\n  {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n  Subida cancelada por el usuario.")
        sys.exit(1)

    # ── PASO 3: Resultado ─────────────────────────────────────────────────────
    print()
    print("[3/3] RESULTADO")
    print("-" * 60)
    short_url  = f"https://www.youtube.com/shorts/{video_id}"
    watch_url  = f"https://www.youtube.com/watch?v={video_id}"
    studio_url = f"https://studio.youtube.com/video/{video_id}/edit"

    print()
    print(f"  Video subido correctamente!")
    print()
    print(f"  Video ID    : {video_id}")
    print(f"  Short URL   : {short_url}")
    print(f"  Watch URL   : {watch_url}")
    print(f"  YouTube Studio: {studio_url}")
    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
