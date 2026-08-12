"""
espn.py
Shared ESPN plumbing: fixtures, results and the retry/naming rules.

Both the Spanish league (laliga.py) and results tracking (resultados.py) read
the same scoreboard endpoint, differing only in which competition and whether
they want matches that have already finished. Keeping one client means the
403-on-User-Agent trap below is written down once instead of being rediscovered
per module.

Public API:
    LIGAS
    get_json(url) -> dict | None
    slug(nombre) -> str | None
    partidos(liga, desde, hasta, solo_terminados=False) -> list[dict]
"""
import time
from datetime import date

import requests

import champions_teams

# ESPN's league codes for the competitions this repo publishes.
LIGAS = {
    "LaLiga": "esp.1",
    "Champions": "uefa.champions",
}

SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/{liga}/scoreboard"
    "?dates={desde:%Y%m%d}-{hasta:%Y%m%d}&limit=400"
)

# No User-Agent, on purpose, matching fixtures_fetcher.py — the ESPN client
# this repo already had working.
#
# Do NOT copy champions_elo.py's browser User-Agent here: ESPN's WAF answers
# 403 Access Denied to that exact string while serving a bare python-requests
# call happily. The two sources want opposite things — ClubElo needs the
# browser string, ESPN rejects it — and the failure is a 403 on a URL that
# opens fine in a browser, which is a confusing thing to debug.
HEADERS: dict[str, str] = {}

_RETRY_DELAYS = (2, 5, 15)


def get_json(url: str) -> dict | None:
    """GET with backoff. None when ESPN stays unreachable."""
    for intento, espera in enumerate((*_RETRY_DELAYS, None), start=1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=25)
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


def slug(nombre: str) -> str | None:
    """ESPN's name -> catalogue slug, or None if we don't know the club."""
    return champions_teams._lookup_index().get(champions_teams._normalize(nombre))


def partidos(
    liga: str,
    desde: date,
    hasta: date,
    solo_terminados: bool = False,
    avisar_sin_resolver: bool = True,
) -> list[dict]:
    """
    Matches in a date range, slugs resolved.

    Each entry carries `fecha`, `local`, `visitante`, `terminado`, and — for a
    finished match — `goles_local` and `goles_visitante`.

    A match whose clubs don't resolve is dropped rather than guessed at: for
    fixtures that would mean rendering an invented colour, and for results it
    would mean scoring a prediction against the wrong match.

    `avisar_sin_resolver` exists because the two callers care differently. When
    picking fixtures, an unknown club is a catalogue gap worth shouting about.
    When scoring results the window covers a whole round, most of which we
    never published — and last season's relegated clubs are legitimately absent
    from the catalogue, so warning about them is noise.
    """
    datos = get_json(SCOREBOARD_URL.format(liga=liga, desde=desde, hasta=hasta))
    if not datos:
        return []

    salida: list[dict] = []
    for evento in datos.get("events", []):
        try:
            competidores = evento["competitions"][0]["competitors"]
            estado = evento["status"]["type"]
        except (KeyError, IndexError, TypeError):
            continue

        terminado = bool(estado.get("completed"))
        if solo_terminados and not terminado:
            continue

        lados: dict[str, dict] = {}
        for competidor in competidores:
            nombre = (competidor.get("team") or {}).get("displayName") or ""
            lados[competidor.get("homeAway")] = {
                "slug": slug(nombre),
                "nombre_espn": nombre,
                "goles": competidor.get("score"),
            }

        local, visitante = lados.get("home"), lados.get("away")
        if not local or not visitante or not local["slug"] or not visitante["slug"]:
            if avisar_sin_resolver:
                sin_resolver = [
                    l["nombre_espn"] for l in (local, visitante) if l and not l["slug"]
                ]
                print(f"[WARN] Partido sin resolver: «{evento.get('name')}»"
                      f"{' — ' + ', '.join(sin_resolver) if sin_resolver else ''}")
            continue

        partido = {
            "fecha": (evento.get("date") or "")[:10],
            # Hora de comienzo completa, en UTC, tal y como la da ESPN
            # ("2026-08-15T17:30Z"). La fecha sola no basta para decidir cuándo
            # se publica el Short: eso va 24 h antes del PRIMER saque, y una
            # jornada empieza a horas muy distintas según el día.
            "inicio": evento.get("date") or "",
            "local": local["slug"],
            "visitante": visitante["slug"],
            "terminado": terminado,
        }
        if terminado:
            try:
                partido["goles_local"] = int(local["goles"])
                partido["goles_visitante"] = int(visitante["goles"])
            except (TypeError, ValueError):
                # Marked finished but without a usable score — abandoned, or
                # ESPN mid-update. Treat as not played rather than as 0-0.
                partido["terminado"] = False

        salida.append(partido)

    salida.sort(key=lambda p: p["fecha"])
    return salida
