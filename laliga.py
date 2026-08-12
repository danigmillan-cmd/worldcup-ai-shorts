"""
laliga.py
Fixtures and standings for the Spanish league, from ESPN.

Why ESPN and not ClubElo
------------------------
ClubElo's /Fixtures does list Spanish matches, but it only reaches a few days
ahead and carries no league or matchday context. The selection rule this feeds
needs the actual league table — "los que estén en las posiciones más altas" is
about points, not about Elo, and a club can sit above another while rated below
it. ESPN publishes both, and fixtures_fetcher.py already talks to ESPN for the
World Cup pipeline, so it is a source this repo already depends on.

Elo still comes from ClubElo (champions_elo.py). ESPN supplies WHO plays and
WHERE they sit; ClubElo supplies HOW GOOD they are.

This module is the engine half — it fetches and normalizes. Which clubs are
worth publishing is taste, and lives in laliga_seleccion.py.

Public API:
    proximos_partidos(dias=8) -> list[dict]
    clasificacion() -> list[dict]
    jornada_actual() -> int
"""
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

import champions_teams

LIGA = "esp.1"
SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/scoreboard"
    "?dates={desde:%Y%m%d}-{hasta:%Y%m%d}&limit=300"
)
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/soccer/{liga}/standings"

CACHE_FILE = Path(__file__).parent / "data" / "laliga_cache.json"

# Standings move once a week and fixtures are published far ahead, so a few
# hours is plenty. Short enough that a Friday render sees Thursday's results.
CACHE_MAX_AGE_HOURS = 6

# No User-Agent, on purpose, matching fixtures_fetcher.py — the ESPN client
# this repo already had working.
#
# Do NOT copy champions_elo.py's browser User-Agent here: ESPN's WAF answers
# 403 Access Denied to that exact string while serving a bare python-requests
# call happily. The two sources want opposite things — ClubElo needs the
# browser string, ESPN rejects it — and the failure is a 403 on a URL that
# works fine in a browser, which is a confusing thing to debug.
_HEADERS: dict[str, str] = {}

_RETRY_DELAYS = (2, 5, 15)


def _get_json(url: str) -> dict | None:
    """GET with backoff. None when ESPN stays unreachable."""
    for intento, espera in enumerate((*_RETRY_DELAYS, None), start=1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=25)
            if resp.status_code < 500:
                resp.raise_for_status()
                return resp.json()
            motivo = f"HTTP {resp.status_code}"
        except (requests.exceptions.RequestException, ValueError) as exc:
            motivo = type(exc).__name__

        if espera is None:
            print(f"[WARN] ESPN no responde ({motivo}) tras {intento} intentos")
            return None
        time.sleep(espera)

    return None


def _slug(nombre: str) -> str | None:
    """ESPN's name -> catalogue slug, or None if we don't know the club."""
    return champions_teams._lookup_index().get(champions_teams._normalize(nombre))


def _leer_cache(clave: str):
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        entrada = payload[clave]
        edad = (
            datetime.now(timezone.utc) - datetime.fromisoformat(entrada["timestamp"])
        ).total_seconds() / 3600
        if edad < CACHE_MAX_AGE_HOURS:
            return entrada["datos"]
    except (OSError, KeyError, ValueError):
        pass
    return None


def _escribir_cache(clave: str, datos) -> None:
    try:
        payload = {}
        if CACHE_FILE.exists():
            try:
                payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            except ValueError:
                payload = {}
        payload[clave] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "datos": datos,
        }
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"[WARN] No se pudo escribir la caché de LaLiga: {exc}")


def clasificacion() -> list[dict]:
    """
    The league table, best first: [{"slug", "puesto", "puntos", "jugados"}, ...].

    Empty when ESPN is unreachable and there's no usable cache. Callers must
    handle that — laliga_seleccion falls back to its fixed list of clubs, which
    is exactly the pre-season behaviour, so a dead ESPN degrades to "publish the
    usual suspects" rather than to a crash.
    """
    cacheado = _leer_cache("clasificacion")
    if cacheado is not None:
        return cacheado

    datos = _get_json(STANDINGS_URL.format(liga=LIGA))
    if not datos:
        return []

    try:
        entradas = datos["children"][0]["standings"]["entries"]
    except (KeyError, IndexError, TypeError):
        print("[WARN] La clasificación de ESPN no tiene la forma esperada")
        return []

    tabla: list[dict] = []
    for entrada in entradas:
        nombre = (entrada.get("team") or {}).get("displayName") or ""
        slug = _slug(nombre)
        if not slug:
            print(f"[WARN] Equipo sin catalogar en la clasificación: «{nombre}»")
            continue
        stats = {s.get("name"): s.get("value") for s in entrada.get("stats", [])}
        tabla.append({
            "slug": slug,
            "puesto": int(stats.get("rank") or 0),
            "puntos": int(stats.get("points") or 0),
            "jugados": int(stats.get("gamesPlayed") or 0),
        })

    tabla.sort(key=lambda e: e["puesto"] or 99)
    _escribir_cache("clasificacion", tabla)
    return tabla


def jornada_actual(tabla: list[dict] | None = None) -> int:
    """
    Matchdays played so far, as the max across clubs.

    Max rather than min because midweek rounds and postponements leave clubs
    on different counts; the question the selection rule asks is "how much of
    the season has happened", and the club furthest along answers it best.
    Returns 0 before the season starts.
    """
    tabla = clasificacion() if tabla is None else tabla
    return max((e["jugados"] for e in tabla), default=0)


def proximos_partidos(dias: int = 8) -> list[dict]:
    """
    Upcoming fixtures: [{"fecha", "local", "visitante"}, ...], slugs resolved.

    `dias` defaults to 8 because a Spanish matchday is spread Friday to Monday
    and the next one starts the following weekend — eight days catches exactly
    one round from any day of the week without bleeding into the next.
    """
    clave = f"partidos_{dias}"
    cacheado = _leer_cache(clave)
    if cacheado is not None:
        return cacheado

    hoy = date.today()
    datos = _get_json(
        SCOREBOARD_URL.format(liga=LIGA, desde=hoy, hasta=hoy + timedelta(days=dias))
    )
    if not datos:
        return []

    partidos: list[dict] = []
    for evento in datos.get("events", []):
        try:
            competidores = evento["competitions"][0]["competitors"]
        except (KeyError, IndexError, TypeError):
            continue

        lados = {}
        for competidor in competidores:
            nombre = (competidor.get("team") or {}).get("displayName") or ""
            lados[competidor.get("homeAway")] = _slug(nombre)

        local, visitante = lados.get("home"), lados.get("away")
        if not local or not visitante:
            print(f"[WARN] Partido sin resolver: «{evento.get('name')}»")
            continue

        partidos.append({
            "fecha": (evento.get("date") or "")[:10],
            "local": local,
            "visitante": visitante,
        })

    partidos.sort(key=lambda p: p["fecha"])
    _escribir_cache(clave, partidos)
    return partidos


if __name__ == "__main__":
    tabla = clasificacion()
    print(f"Jornada actual: {jornada_actual(tabla)}")
    print(f"\nClasificación ({len(tabla)}):")
    for e in tabla[:8]:
        nombre = champions_teams.resolve_team(e["slug"])["nombre"]
        print(f"  {e['puesto']:2}. {nombre:14} {e['puntos']:3} pts "
              f"({e['jugados']} jugados)")

    partidos = proximos_partidos()
    print(f"\nPróximos partidos ({len(partidos)}):")
    for p in partidos:
        local = champions_teams.resolve_team(p["local"])["nombre"]
        visitante = champions_teams.resolve_team(p["visitante"])["nombre"]
        print(f"  {p['fecha']}  {local:14} - {visitante}")
