#!/usr/bin/env python3
"""
delete_video.py
Elimina un video de YouTube usando YouTube Data API v3.

Uso:
    python scripts/delete_video.py VIDEO_ID
    python scripts/delete_video.py Qsdg8K44u7E
    python scripts/delete_video.py Qsdg8K44u7E --yes     # sin confirmacion

Notas:
    - Primera ejecucion: abre el navegador para autorizacion (scope youtube).
    - El token se guarda en credentials/token_manage.json.
    - La eliminacion es permanente e irreversible.
"""

import sys
import time
import argparse
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Reutilizar find_client_secret del modulo de upload
sys.path.insert(0, str(Path(__file__).resolve().parent))
from upload_youtube import find_client_secret, CREDS_DIR, ROOT

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURACION
# ═══════════════════════════════════════════════════════════════════════════════

# Eliminar videos requiere el scope "youtube" (mas amplio que "youtube.upload")
SCOPES = ["https://www.googleapis.com/auth/youtube"]

# Token separado para no afectar el flujo de subida
TOKEN_JSON = CREDS_DIR / "token_manage.json"


# ═══════════════════════════════════════════════════════════════════════════════
# AUTENTICACION
# ═══════════════════════════════════════════════════════════════════════════════
def authenticate() -> object:
    """
    Autentica con scope 'youtube' (lectura + escritura + borrado).
    Guarda el token en credentials/token_manage.json.
    """
    creds = None

    if TOKEN_JSON.exists():
        print("  Cargando token guardado (token_manage.json)...")
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_JSON), SCOPES)
        except Exception as e:
            print(f"  Token invalido ({e}), se pedira nuevo login.")
            TOKEN_JSON.unlink(missing_ok=True)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("  Token expirado — refrescando...")
            try:
                creds.refresh(Request())
                print("  Token refrescado correctamente.")
            except Exception as e:
                print(f"  No se pudo refrescar ({e}). Se pedira nuevo login.")
                TOKEN_JSON.unlink(missing_ok=True)
                creds = None

        if not creds:
            client_secret = find_client_secret()
            print(f"  Credenciales : {client_secret.name}")
            print()
            print("  Abriendo navegador para autorizacion con Google...")
            print("  (Requiere permiso 'Administrar cuenta de YouTube')")
            print()
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret),
                scopes=SCOPES,
            )
            creds = flow.run_local_server(
                port=0,
                prompt="consent",
                access_type="offline",
            )

        CREDS_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_JSON, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"  Token guardado en: {TOKEN_JSON.relative_to(ROOT)}")

    print("  Autenticacion correcta.")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


# ═══════════════════════════════════════════════════════════════════════════════
# OBTENER INFO DEL VIDEO
# ═══════════════════════════════════════════════════════════════════════════════
def get_video_info(youtube, video_id: str) -> dict | None:
    """
    Obtiene titulo, canal y estado de privacidad del video.
    Retorna None si el video no existe o no pertenece al canal autenticado.
    """
    try:
        response = youtube.videos().list(
            part="snippet,status",
            id=video_id,
        ).execute()
    except HttpError as e:
        print(f"  Error al buscar el video: {e.resp.status} — {e.reason}")
        return None

    items = response.get("items", [])
    if not items:
        return None

    item    = items[0]
    snippet = item.get("snippet", {})
    status  = item.get("status", {})
    return {
        "id":            video_id,
        "title":         snippet.get("title", "(sin titulo)"),
        "channel":       snippet.get("channelTitle", "(desconocido)"),
        "published":     snippet.get("publishedAt", "")[:10],
        "privacy":       status.get("privacyStatus", "unknown"),
        "url_short":     f"https://www.youtube.com/shorts/{video_id}",
        "url_watch":     f"https://www.youtube.com/watch?v={video_id}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ELIMINAR VIDEO
# ═══════════════════════════════════════════════════════════════════════════════
def delete_video(youtube, video_id: str) -> bool:
    """
    Elimina el video. Retorna True si se elimino correctamente.
    La respuesta de la API es HTTP 204 (sin cuerpo) en caso de exito.
    """
    try:
        youtube.videos().delete(id=video_id).execute()
        return True
    except HttpError as e:
        status = e.resp.status
        if status == 403:
            print(f"  Error 403: No tienes permiso para eliminar este video.")
            print(f"  Asegurate de que el video pertenece a tu canal.")
        elif status == 404:
            print(f"  Error 404: Video no encontrado (puede que ya este eliminado).")
        else:
            print(f"  Error HTTP {status}: {e.reason}")
        return False
    except Exception as e:
        print(f"  Error inesperado: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Elimina un video de YouTube por VIDEO_ID",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Ejemplo:\n  python scripts/delete_video.py Qsdg8K44u7E",
    )
    p.add_argument(
        "video_id",
        help="ID del video a eliminar (ej: Qsdg8K44u7E)",
    )
    p.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Confirmar eliminacion sin preguntar",
    )
    p.add_argument(
        "--reauth",
        action="store_true",
        help="Forzar nuevo login (borra token_manage.json)",
    )
    return p


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    args = build_parser().parse_args()
    video_id = args.video_id.strip()

    if args.reauth and TOKEN_JSON.exists():
        TOKEN_JSON.unlink()
        print("Token eliminado. Se pedira nuevo login.\n")

    print()
    print("=" * 60)
    print("  YouTube Video Deleter  |  World Cup AI")
    print("=" * 60)

    # ── PASO 1: Autenticacion ─────────────────────────────────────────────────
    print()
    print("[1/3] AUTENTICACION")
    print("-" * 60)
    try:
        youtube = authenticate()
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    # ── PASO 2: Buscar video ──────────────────────────────────────────────────
    print()
    print("[2/3] VERIFICANDO VIDEO")
    print("-" * 60)
    print(f"  Video ID : {video_id}")

    info = get_video_info(youtube, video_id)
    if info is None:
        print()
        print("  ERROR: Video no encontrado o no pertenece a tu canal.")
        print(f"  Comprueba el ID: https://www.youtube.com/watch?v={video_id}")
        sys.exit(1)

    print(f"  Titulo   : {info['title']}")
    print(f"  Canal    : {info['channel']}")
    print(f"  Fecha    : {info['published']}")
    print(f"  Privacy  : {info['privacy']}")
    print(f"  URL      : {info['url_watch']}")

    # ── Confirmacion ──────────────────────────────────────────────────────────
    print()
    print("  ADVERTENCIA: La eliminacion es permanente e irreversible.")
    print()

    if not args.yes:
        try:
            answer = input(f"  Eliminar '{info['title']}'? [s/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n  Cancelado.")
            sys.exit(0)
        if answer not in ("s", "si", "yes", "y"):
            print("  Cancelado por el usuario.")
            sys.exit(0)

    # ── PASO 3: Eliminar ──────────────────────────────────────────────────────
    print()
    print("[3/3] ELIMINANDO VIDEO")
    print("-" * 60)
    print("  Enviando solicitud a YouTube API...")

    success = delete_video(youtube, video_id)

    print()
    if success:
        print(f"  Video eliminado correctamente.")
        print(f"  ID: {video_id}")
        print(f"  Titulo: {info['title']}")
    else:
        print("  No se pudo eliminar el video.")
        sys.exit(1)

    print()
    print("=" * 60)


if __name__ == "__main__":
    main()
