#!/usr/bin/env python3
"""
Flag manager para el generador de YouTube Shorts del Mundial 2026.
Descarga banderas PNG desde flagcdn.com y las cachea en assets/flags/.
"""

import os
import sys
import requests
from pathlib import Path

# ── Rutas ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLAGS_DIR    = PROJECT_ROOT / "assets" / "flags"
BASE_URL     = "https://flagcdn.com/256x192/{code}.png"
TIMEOUT      = 10  # segundos

# ── Catálogo de países ─────────────────────────────────────────────────────────
COUNTRY_CODES = {
    "Alemania":                        "de",
    "Arabia Saudita":                  "sa",
    "Argelia":                         "dz",
    "Argentina":                       "ar",
    "Australia":                       "au",
    "Austria":                         "at",
    "Bosnia y Herzegovina":            "ba",
    "Brasil":                          "br",
    "Bélgica":                         "be",
    "Cabo Verde":                      "cv",
    "Canadá":                          "ca",
    "Catar":                           "qa",
    "Colombia":                        "co",
    "Corea del Sur":                   "kr",
    "Costa de Marfil":                 "ci",
    "Croacia":                         "hr",
    "Curazao":                         "cw",
    "Ecuador":                         "ec",
    "Egipto":                          "eg",
    "Escocia":                         "gb-sct",
    "España":                          "es",
    "Estados Unidos":                  "us",
    "Francia":                         "fr",
    "Ghana":                           "gh",
    "Haiti":                           "ht",
    "Irak":                            "iq",
    "Iran":                            "ir",
    "Inglaterra":                      "gb-eng",
    "Japon":                           "jp",
    "Jordania":                        "jo",
    "Marruecos":                       "ma",
    "Mexico":                          "mx",
    "Noruega":                         "no",
    "Nueva Zelanda":                   "nz",
    "Paises Bajos":                    "nl",
    "Panama":                          "pa",
    "Paraguay":                        "py",
    "Portugal":                        "pt",
    "Republica Checa":                 "cz",
    "Republica Democratica del Congo": "cd",
    "Senegal":                         "sn",
    "Sudafrica":                       "za",
    "Suiza":                           "ch",
    "Suecia":                          "se",
    "Tunez":                           "tn",
    "Turquia":                         "tr",
    "Uruguay":                         "uy",
    "Uzbekistan":                      "uz",
    # Aliases con tildes (normalización automática devuelve las mismas claves)
    "Haití":                           "ht",
    "Irán":                            "ir",
    "Japón":                           "jp",
    "México":                          "mx",
    "Países Bajos":                    "nl",
    "Panamá":                          "pa",
    "República Checa":                 "cz",
    "República Democrática del Congo": "cd",
    "Sudáfrica":                       "za",
    "Túnez":                           "tn",
    "Turquía":                         "tr",
    "Bélgica":                         "be",
    "Canadá":                          "ca",
}


# ── Núcleo ─────────────────────────────────────────────────────────────────────
def _ensure_flags_dir() -> None:
    FLAGS_DIR.mkdir(parents=True, exist_ok=True)


def _local_path(code: str) -> Path:
    return FLAGS_DIR / f"{code}.png"


def _download(code: str, dest: Path) -> bool:
    url = BASE_URL.format(code=code)
    print(f"  [descarga] {url}")
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        if "image" not in resp.headers.get("Content-Type", ""):
            print(f"  [error]    La respuesta no es una imagen ({url})")
            return False
        dest.write_bytes(resp.content)
        print(f"  [ok]       Guardado en {dest}")
        return True
    except requests.exceptions.Timeout:
        print(f"  [error]    Timeout descargando {url}")
    except requests.exceptions.HTTPError as e:
        print(f"  [error]    HTTP {e.response.status_code} para {url}")
    except requests.exceptions.RequestException as e:
        print(f"  [error]    {e}")
    return False


def get_flag(country_name: str) -> Path | None:
    """
    Devuelve la ruta local del PNG de la bandera.
    Si no existe en disco la descarga primero.
    Retorna None si el país no está en el catálogo o la descarga falla.
    """
    _ensure_flags_dir()

    code = COUNTRY_CODES.get(country_name)
    if code is None:
        print(f"  [aviso]    '{country_name}' no encontrado en el catalogo.")
        return None

    dest = _local_path(code)
    if dest.exists():
        return dest

    print(f"  [bandera]  '{country_name}' ({code}) no en cache, descargando...")
    success = _download(code, dest)
    return dest if success else None


def get_flag_pil(country_name: str):
    """
    Comodín para MoviePy/Pillow: devuelve un objeto PIL Image o None.
    """
    from PIL import Image
    path = get_flag(country_name)
    if path is None:
        return None
    return Image.open(path).convert("RGBA")


def download_all(skip_existing: bool = True) -> dict[str, bool]:
    """
    Descarga todas las banderas del catálogo.
    Devuelve un dict {country: success}.
    """
    _ensure_flags_dir()
    seen_codes: set[str] = set()
    results: dict[str, bool] = {}

    for country, code in COUNTRY_CODES.items():
        if code in seen_codes:
            results[country] = True  # alias ya procesado
            continue
        seen_codes.add(code)

        dest = _local_path(code)
        if skip_existing and dest.exists():
            print(f"  [cache]    {country} ({code})")
            results[country] = True
            continue

        print(f"  [bandera]  {country} ({code})")
        results[country] = _download(code, dest)

    return results


# ── CLI ────────────────────────────────────────────────────────────────────────
def _print_summary(results: dict[str, bool]) -> None:
    ok  = sum(v for v in results.values())
    err = len(results) - ok
    print(f"\nResumen: {ok} OK  |  {err} errores  |  {len(results)} total")
    if err:
        failed = [c for c, v in results.items() if not v]
        print("Fallaron:", ", ".join(failed))


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Gestor de banderas para el Mundial 2026"
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("all",  help="Descarga todas las banderas")
    sub.add_parser("list", help="Lista los paises del catalogo")

    get_p = sub.add_parser("get", help="Obtiene la bandera de un pais")
    get_p.add_argument("country", help='Nombre del pais, ej: "España"')

    args = parser.parse_args()

    if args.cmd == "all":
        print(f"Descargando {len(set(COUNTRY_CODES.values()))} banderas...\n")
        results = download_all()
        _print_summary(results)

    elif args.cmd == "list":
        print(f"{'Pais':<40} {'Codigo':<10} {'En cache'}")
        print("-" * 60)
        seen: set[str] = set()
        for country, code in sorted(COUNTRY_CODES.items()):
            if code in seen:
                continue
            seen.add(code)
            cached = "si" if _local_path(code).exists() else "no"
            print(f"{country:<40} {code:<10} {cached}")

    elif args.cmd == "get":
        path = get_flag(args.country)
        if path:
            print(f"\nRuta: {path}")
        else:
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
