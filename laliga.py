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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import champions_teams
import espn

LIGA = espn.LIGAS["LaLiga"]
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/soccer/{liga}/standings"

CACHE_FILE = Path(__file__).parent / "data" / "laliga_cache.json"

# Standings move once a week and fixtures are published far ahead, so a few
# hours is plenty. Short enough that a Friday render sees Thursday's results.
CACHE_MAX_AGE_HOURS = 6

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

    datos = espn.get_json(STANDINGS_URL.format(liga=LIGA))
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
        slug = espn.slug(nombre)
        if not slug:
            print(f"[WARN] Equipo sin catalogar en la clasificación: «{nombre}»")
            continue
        stats = {s.get("name"): s.get("value") for s in entrada.get("stats", [])}
        # ESPN names goals with its generic scoring fields: pointsFor/Against
        # are goals for/against, not points. `points` is the league points.
        tabla.append({
            "slug": slug,
            "puesto": int(stats.get("rank") or 0),
            "puntos": int(stats.get("points") or 0),
            "jugados": int(stats.get("gamesPlayed") or 0),
            "goles_favor": int(stats.get("pointsFor") or 0),
            "goles_contra": int(stats.get("pointsAgainst") or 0),
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
    partidos = [
        {"fecha": p["fecha"], "local": p["local"], "visitante": p["visitante"]}
        for p in espn.partidos(LIGA, hoy, hoy + timedelta(days=dias))
    ]
    if partidos:
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
