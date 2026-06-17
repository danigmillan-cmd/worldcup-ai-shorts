#!/usr/bin/env python3
"""
elo_rankings.py
Pipeline de datos ELO para el generador del Mundial 2026.

Fuentes (en orden de preferencia):
  1. eloratings.net  — clasificación principal
  2. Wikipedia       — tabla estática, más robusta
  3. Datos de respaldo (junio 2025) — sin red

Uso:
    from elo_rankings import get_top10
    ranking = get_top10(flags_dir=Path("assets/flags"))
"""

import re
import json
import math
import requests
import numpy as np
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# MAPEO: nombre en inglés → (nombre display en inglés, código ISO bandera)
# ─────────────────────────────────────────────────────────────────────────────
ELO_MAP: dict[str, tuple[str, str]] = {
    "Spain":              ("SPAIN",          "es"),
    "France":             ("FRANCE",         "fr"),
    "England":            ("ENGLAND",        "gb-eng"),
    "Brazil":             ("BRAZIL",         "br"),
    "Argentina":          ("ARGENTINA",      "ar"),
    "Netherlands":        ("NETHERLANDS",    "nl"),
    "Germany":            ("GERMANY",        "de"),
    "Portugal":           ("PORTUGAL",       "pt"),
    "Belgium":            ("BELGIUM",        "be"),
    "Italy":              ("ITALY",          "it"),
    "Uruguay":            ("URUGUAY",        "uy"),
    "Croatia":            ("CROATIA",        "hr"),
    "Denmark":            ("DENMARK",        "dk"),
    "Switzerland":        ("SWITZERLAND",    "ch"),
    "Morocco":            ("MOROCCO",        "ma"),
    "Mexico":             ("MEXICO",         "mx"),
    "Colombia":           ("COLOMBIA",       "co"),
    "United States":      ("USA",            "us"),
    "USA":                ("USA",            "us"),
    "Japan":              ("JAPAN",          "jp"),
    "Senegal":            ("SENEGAL",        "sn"),
    "Ecuador":            ("ECUADOR",        "ec"),
    "Chile":              ("CHILE",          "cl"),
    "Peru":               ("PERU",           "pe"),
    "Ukraine":            ("UKRAINE",        "ua"),
    "Poland":             ("POLAND",         "pl"),
    "Czech Republic":     ("CZECH REPUBLIC", "cz"),
    "Sweden":             ("SWEDEN",         "se"),
    "Turkey":             ("TURKEY",         "tr"),
    "Norway":             ("NORWAY",         "no"),
    "Australia":          ("AUSTRALIA",      "au"),
    "South Korea":        ("SOUTH KOREA",    "kr"),
    "Austria":            ("AUSTRIA",        "at"),
    "Serbia":             ("SERBIA",         "rs"),
    "Hungary":            ("HUNGARY",        "hu"),
    "Romania":            ("ROMANIA",        "ro"),
    "Wales":              ("WALES",          "gb-wls"),
    "Scotland":           ("SCOTLAND",       "gb-sct"),
    "Ivory Coast":        ("IVORY COAST",    "ci"),
    "Cote d'Ivoire":      ("IVORY COAST",    "ci"),
    "Ghana":              ("GHANA",          "gh"),
    "Cameroon":           ("CAMEROON",       "cm"),
    "Egypt":              ("EGYPT",          "eg"),
    "Algeria":            ("ALGERIA",        "dz"),
    "Nigeria":            ("NIGERIA",        "ng"),
    "Tunisia":            ("TUNISIA",        "tn"),
    "Iran":               ("IRAN",           "ir"),
    "Saudi Arabia":       ("SAUDI ARABIA",   "sa"),
    "Qatar":              ("QATAR",          "qa"),
    "Canada":             ("CANADA",         "ca"),
    "South Africa":       ("SOUTH AFRICA",   "za"),
    "Russia":             ("RUSSIA",         "ru"),
    "Slovakia":           ("SLOVAKIA",       "sk"),
    "Slovenia":           ("SLOVENIA",       "si"),
    "Albania":            ("ALBANIA",        "al"),
    "Israel":             ("ISRAEL",         "il"),
    "Georgia":            ("GEORGIA",        "ge"),
    "North Macedonia":    ("N. MACEDONIA",   "mk"),
    "Finland":            ("FINLAND",        "fi"),
    "Costa Rica":         ("COSTA RICA",     "cr"),
    "Panama":             ("PANAMA",         "pa"),
    "Paraguay":           ("PARAGUAY",       "py"),
    "Bolivia":            ("BOLIVIA",        "bo"),
    "Venezuela":          ("VENEZUELA",      "ve"),
    "Honduras":           ("HONDURAS",       "hn"),
    "New Zealand":        ("NEW ZEALAND",    "nz"),
    "Uzbekistan":         ("UZBEKISTAN",     "uz"),
    "Cape Verde":         ("CAPE VERDE",    "cv"),
    "Burkina Faso":       ("BURKINA FASO",  "bf"),
    "Mali":               ("MALI",          "ml"),
    "Curacao":            ("CURACAO",       "cw"),
    "Bosnia Herzegovina": ("BOSNIA",        "ba"),
    "Bosnia and Herzegovina": ("BOSNIA",    "ba"),
    "Jordan":             ("JORDAN",        "jo"),
    "Iraq":               ("IRAQ",          "iq"),
    "Greece":             ("GREECE",        "gr"),
}

# ─────────────────────────────────────────────────────────────────────────────
# DATOS DE RESPALDO  (top 10 aproximado, junio 2025)
# ─────────────────────────────────────────────────────────────────────────────
FALLBACK_TOP10: list[tuple[str, int]] = [
    ("Spain",       2166),
    ("France",      2122),
    ("England",     2092),
    ("Brazil",      2069),
    ("Argentina",   2061),
    ("Netherlands", 2024),
    ("Germany",     2018),
    ("Portugal",    2001),
    ("Belgium",     1965),
    ("Italy",       1955),
]

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}


# ─────────────────────────────────────────────────────────────────────────────
# SCRAPING
# ─────────────────────────────────────────────────────────────────────────────
def _parse_rows_bs4(html: str) -> list[tuple[str, int]]:
    """Parsea una tabla HTML con BeautifulSoup buscando (nombre, puntuación)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, int]] = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        name = cells[1].get_text(strip=True)
        rating_str = re.sub(r"[^\d]", "", cells[2].get_text(strip=True))
        if rating_str and len(name) > 1:
            rating = int(rating_str)
            if 1400 < rating < 2500:
                results.append((name, rating))
    return results


def _parse_rows_regex(html: str) -> list[tuple[str, int]]:
    """Fallback: extrae (nombre, puntuación Elo) con regex."""
    pattern = r"\b([A-Z][a-zA-Z '\-]{2,28})\s+(\d{4})\b"
    results: list[tuple[str, int]] = []
    seen: set[str] = set()
    for name, rating_str in re.findall(pattern, html):
        name = name.strip()
        rating = int(rating_str)
        if 1400 < rating < 2500 and name not in seen:
            seen.add(name)
            results.append((name, rating))
    return results


def _fetch_eloratings(timeout: int = 12) -> list[tuple[str, int]]:
    """Descarga rankings desde eloratings.net."""
    resp = requests.get(
        "https://www.eloratings.net/World",
        headers=_HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()
    html = resp.text

    try:
        rows = _parse_rows_bs4(html)
    except Exception:
        rows = _parse_rows_regex(html)

    if len(rows) < 5:
        raise ValueError(f"Solo {len(rows)} filas extraidas de eloratings.net")
    return rows


def _fetch_wikipedia(timeout: int = 12) -> list[tuple[str, int]]:
    """
    Descarga rankings desde la tabla de Wikipedia sobre ELO mundial.
    URL: https://en.wikipedia.org/wiki/World_Football_Elo_Ratings
    """
    from bs4 import BeautifulSoup
    resp = requests.get(
        "https://en.wikipedia.org/wiki/World_Football_Elo_Ratings",
        headers=_HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    results: list[tuple[str, int]] = []
    for table in soup.find_all("table", class_="wikitable"):
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            name = cells[1].get_text(strip=True)
            rating_str = re.sub(r"[^\d]", "", cells[2].get_text(strip=True))
            if rating_str and len(name) > 1:
                rating = int(rating_str)
                if 1400 < rating < 2500:
                    results.append((name, rating))
        if len(results) >= 10:
            break

    if len(results) < 5:
        raise ValueError(f"Wikipedia: solo {len(results)} filas")
    return results


def _fetch_raw(top_n: int = 20) -> list[tuple[str, int]]:
    """
    Intenta obtener datos en vivo desde múltiples fuentes.
    Retorna lista sin filtrar, ordenada por Elo desc.
    """
    sources = [
        ("eloratings.net", _fetch_eloratings),
        ("Wikipedia",      _fetch_wikipedia),
    ]
    for name, fn in sources:
        try:
            rows = fn()
            rows.sort(key=lambda x: x[1], reverse=True)
            # Deduplicar
            seen: set[str] = set()
            unique = [(n, e) for n, e in rows if not (n in seen or seen.add(n))]
            print(f"  Fuente: {name} ({len(unique)} equipos parseados)")
            return unique[:top_n]
        except Exception as e:
            print(f"  {name}: {type(e).__name__} — {e}")

    raise RuntimeError("Todas las fuentes fallaron")


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSIÓN ELO → PROBABILIDADES
# ─────────────────────────────────────────────────────────────────────────────
def elo_to_probabilities(elos: list[float], temperature: float = 100.0) -> list[float]:
    """
    Convierte ratings Elo en probabilidades aproximadas de ganar el Mundial.

    Fórmula: P_i ∝ exp((Elo_i − Elo_max) / T)

    Con T=100 el lider tiene ~5-8x mas probabilidad que el equipo 10.
    Ajusta T para cambiar el spread: T↑ = distribución mas plana.
    """
    arr = np.array(elos, dtype=float)
    log_w = (arr - arr.max()) / temperature
    w = np.exp(log_w)
    probs = (w / w.sum() * 100).round(1)
    return probs.tolist()


# ─────────────────────────────────────────────────────────────────────────────
# DESCARGA DE BANDERAS FALTANTES
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_flags(teams: list[dict], flags_dir: Path, timeout: int = 10) -> None:
    flags_dir.mkdir(parents=True, exist_ok=True)
    for team in teams:
        path = flags_dir / f"{team['code']}.png"
        if path.exists():
            continue
        url = f"https://flagcdn.com/256x192/{team['code']}.png"
        print(f"  [flag] Descargando {team['code']}.png...")
        try:
            r = requests.get(url, headers=_HEADERS, timeout=timeout)
            r.raise_for_status()
            if "image" in r.headers.get("Content-Type", ""):
                path.write_bytes(r.content)
                print(f"  [flag] OK: {team['code']}.png")
        except Exception as e:
            print(f"  [flag] Error {team['code']}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# API PÚBLICA
# ─────────────────────────────────────────────────────────────────────────────
def get_top10(flags_dir: Path | None = None) -> list[dict]:
    """
    Devuelve el top 10 mundial por Elo con probabilidades de victoria del Mundial.

    Cada elemento del resultado:
        rank  (int) : posicion 1-10
        name  (str) : nombre en español (mayusculas)
        code  (str) : codigo ISO de bandera ("es", "br", "gb-eng", ...)
        elo   (int) : rating Elo actual
        pct   (int) : probabilidad % de ganar el Mundial (suma ~100)

    Si el scraping falla usa datos de respaldo de junio 2025.
    """
    print("Obteniendo rankings ELO mundiales...")
    raw: list[tuple[str, int]] | None = None

    try:
        raw = _fetch_raw(top_n=20)
    except Exception:
        print("  Usando datos de respaldo (junio 2025)")
        raw = list(FALLBACK_TOP10)

    # ── Mapear a nombres/flags ────────────────────────────────────────────────
    mapped: list[dict] = []
    for name_en, elo in raw:
        # Búsqueda exacta, luego insensible a capitalización
        mapping = ELO_MAP.get(name_en)
        if mapping is None:
            key_lower = name_en.lower()
            for k, v in ELO_MAP.items():
                if k.lower() == key_lower:
                    mapping = v
                    break
        if mapping is None:
            continue  # equipo no en el mapa
        display, code = mapping
        if any(t["code"] == code for t in mapped):
            continue  # evitar duplicados de código de bandera
        mapped.append({"name_en": name_en, "name": display,
                       "code": code, "elo": int(elo)})
        if len(mapped) == 10:
            break

    # Completar con fallback si es necesario
    if len(mapped) < 10:
        print(f"  Solo {len(mapped)} mapeados; completando con respaldo...")
        for name_en, elo in FALLBACK_TOP10:
            _, code = ELO_MAP[name_en]
            if not any(t["code"] == code for t in mapped):
                display, code = ELO_MAP[name_en]
                mapped.append({"name_en": name_en, "name": display,
                               "code": code, "elo": int(elo)})
            if len(mapped) == 10:
                break

    # ── Probabilidades ────────────────────────────────────────────────────────
    elos  = [t["elo"] for t in mapped]
    probs = elo_to_probabilities(elos, temperature=100.0)

    result: list[dict] = []
    for rank, (team, prob) in enumerate(zip(mapped, probs), start=1):
        result.append({
            "rank": rank,
            "name": team["name"],
            "code": team["code"],
            "elo":  team["elo"],
            "pct":  max(1, round(prob)),
        })

    # ── Descargar banderas faltantes ──────────────────────────────────────────
    if flags_dir is not None:
        _ensure_flags(result, flags_dir)

    # ── Resumen en consola ────────────────────────────────────────────────────
    print(f"\n  {'#':>3}  {'Equipo':<16}  {'Elo':>5}  {'Prob':>6}")
    print("  " + "-" * 38)
    for t in result:
        print(f"  {t['rank']:>3}  {t['name']:<16}  {t['elo']:>5}  {t['pct']:>5}%")
    print()

    return result


# ─────────────────────────────────────────────────────────────────────────────
# CLI rápido
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    data = get_top10()
    print(json.dumps(data, indent=2, ensure_ascii=False))
