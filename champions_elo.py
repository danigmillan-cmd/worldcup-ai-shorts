"""
champions_elo.py
Club Elo ratings from clubelo.com for the Champions predictions Shorts.

The national-team pipeline pulls from eloratings.net (see rankings.py); that
source has no clubs, so this is the club-football equivalent. Same shape of
contract: try live, fall back to the on-disk cache, and record which one fed
the run so a silent fallback can be audited afterwards.

clubelo.com serves a CSV of every rated club for a given date at
http://api.clubelo.com/YYYY-MM-DD — free, no key, no rate limit published.
Ratings update daily.

Public API:
    get_elo_table(force_refresh=False) -> dict[str, float]   # slug -> Elo
    get_elo(slug_or_name, table=None) -> float
    DEFAULT_ELO
"""
import csv
import io
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

import champions_teams

CLUBELO_URL = "http://api.clubelo.com/{fecha}"
CLUBELO_CLUB_URL = "http://api.clubelo.com/{club}"
CACHE_FILE = Path(__file__).parent / "data" / "clubelo_cache.json"
SOURCE_FILE = Path(__file__).parent / "data" / "clubelo_source.json"
HISTORY_CACHE_FILE = Path(__file__).parent / "data" / "clubelo_history_cache.json"

# Reuse the cache for this long before hitting the network again. ClubElo
# recomputes daily, and a matchday render doesn't need fresher than that.
CACHE_MAX_AGE_HOURS = 24

# Per-club history is ~6000 rows going back to the 1940s; every row but the
# last describes a date that has already happened and will never change again.
# A week is plenty, and it keeps a matchday render off the network entirely.
HISTORY_CACHE_MAX_AGE_HOURS = 24 * 7

# Rating handed to a club that is in neither ClubElo nor the cache. Sits around
# the bottom of the league-phase field: an unrated club is almost always a
# play-off qualifier, not a giant. Better a plausible underdog than a crash.
DEFAULT_ELO = 1500.0

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _record_source(source: str, clubs_resolved: int) -> None:
    """Persist which source fed the last refresh, mirroring rankings.py."""
    try:
        SOURCE_FILE.parent.mkdir(parents=True, exist_ok=True)
        SOURCE_FILE.write_text(
            json.dumps(
                {
                    "source": source,
                    "clubs_resolved": clubs_resolved,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"[WARN] No se pudo escribir la auditoría de ClubElo: {exc}")


def _fetch_clubelo(timeout: int = 15) -> tuple[dict[str, float], dict[str, str]]:
    """
    Download today's CSV and map it onto the catalogue's slugs.

    ClubElo covers ~600 clubs; only the ones in the catalogue are kept. It uses
    its own spellings ("Paris SG", "Bilbao", "Karabakh Agdam", "Bodoe Glimt"),
    which is why those live as aliases in data/equipos_champions.json — they
    were checked against a real response, not guessed.

    Returns (slug -> Elo, slug -> ClubElo's own spelling). The second map is
    what makes the per-club history endpoint usable: /<Club> is keyed by their
    spelling, and reading it off a real response beats guessing which of our
    aliases they happen to use.
    """
    url = CLUBELO_URL.format(fecha=date.today().isoformat())
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()

    index = champions_teams._lookup_index()
    tabla: dict[str, float] = {}
    nombres: dict[str, str] = {}

    for row in csv.DictReader(io.StringIO(resp.text)):
        club = (row.get("Club") or "").strip()
        slug = index.get(champions_teams._normalize(club))
        # The CSV is rank-ordered, so the first hit for a slug is the senior
        # side — this is what keeps a reserve team ("Sociedad B") from
        # overwriting the first team.
        if slug and slug not in tabla:
            try:
                tabla[slug] = round(float(row["Elo"]), 1)
            except (KeyError, TypeError, ValueError):
                continue
            nombres[slug] = club

    if not tabla:
        raise ValueError("ClubElo respondió pero no casó ningún club del catálogo")
    return tabla, nombres


def _read_cache() -> tuple[dict[str, float], float] | None:
    """Return (table, age_in_hours) or None if there's no readable cache."""
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        guardado = datetime.fromisoformat(payload["timestamp"])
        edad = (datetime.now(timezone.utc) - guardado).total_seconds() / 3600
        return payload["elo"], edad
    except (OSError, KeyError, ValueError):
        return None


def _read_cached_names() -> dict[str, str]:
    """slug -> ClubElo's spelling, as recorded by the last live refresh."""
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return payload.get("nombres_clubelo") or {}
    except (OSError, ValueError):
        return {}


def _write_cache(tabla: dict[str, float], nombres: dict[str, str] | None = None) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "fecha_datos": date.today().isoformat(),
                    "elo": tabla,
                    "nombres_clubelo": nombres or _read_cached_names(),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"[WARN] No se pudo escribir la caché de ClubElo: {exc}")


def get_elo_table(force_refresh: bool = False) -> dict[str, float]:
    """
    Elo per catalogue slug.

    Order: fresh cache -> clubelo.com -> stale cache -> empty.

    An empty table is not fatal: `get_elo()` falls back to DEFAULT_ELO, so a
    render on a runner with no network still produces a video. It will be a
    video where every club looks equally strong, which is why the source is
    written to data/clubelo_source.json — so it's visible after the fact
    rather than being a silent shrug.
    """
    cache = _read_cache()

    if not force_refresh and cache and cache[1] < CACHE_MAX_AGE_HOURS:
        tabla, edad = cache
        print(f"[INFO] ClubElo: caché de hace {edad:.1f} h ({len(tabla)} clubes)")
        return tabla

    try:
        tabla, nombres = _fetch_clubelo()
        print(f"[INFO] ClubElo: descargado en vivo ({len(tabla)} clubes)")
        _write_cache(tabla, nombres)
        _record_source("clubelo.com", len(tabla))
        return tabla
    except Exception as exc:
        print(f"[INFO] ClubElo no disponible ({type(exc).__name__}: {exc})")

    if cache:
        tabla, edad = cache
        print(f"[WARN] ClubElo: usando caché CADUCADA de hace {edad:.1f} h "
              f"({len(tabla)} clubes)")
        _record_source("cache-stale", len(tabla))
        return tabla

    print(f"[WARN] ClubElo: sin datos y sin caché — todos los clubes a "
          f"{DEFAULT_ELO:.0f}. Las probabilidades no significarán nada.")
    _record_source("none", 0)
    return {}


def get_elo(slug_or_name: str, table: dict[str, float] | None = None) -> float:
    """Elo for one club, by slug or by any name the catalogue resolves."""
    tabla = get_elo_table() if table is None else table

    if slug_or_name in tabla:
        return tabla[slug_or_name]

    slug = champions_teams._lookup_index().get(
        champions_teams._normalize(slug_or_name)
    )
    if slug is not None and slug in tabla:
        return tabla[slug]

    print(f"[WARN] Sin Elo para «{slug_or_name}» — se usa {DEFAULT_ELO:.0f}")
    return DEFAULT_ELO


def _get_reintentando(url: str) -> str | None:
    """
    GET with backoff. Returns the body, or None if clubelo.com stayed down.

    Not optional politeness: clubelo.com serves intermittent 502s (it did so
    repeatedly on 11-ago-2026, which is how this got written). Without retries
    a matchday render silently loses every form fact at once and the headlines
    all collapse onto the same fallback angle.

    Note scripts/calibrate_champions.py carries its own copy of this for the
    same reason. Worth folding together the next time either is touched.
    """
    for intento, espera in enumerate((2, 5, 15, None), start=1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=25)
            if resp.status_code < 500:
                return resp.text if resp.status_code < 400 else ""
            motivo = f"HTTP {resp.status_code}"
        except requests.exceptions.RequestException as exc:
            motivo = type(exc).__name__

        if espera is None:
            print(f"[WARN] clubelo.com no responde ({motivo}) tras {intento} intentos")
            return None
        time.sleep(espera)

    return None


def _clubelo_name(slug: str) -> list[str]:
    """
    Candidate spellings for the /<Club> endpoint, best first.

    The live refresh records ClubElo's own spelling per slug, so that is the
    first candidate. The catalogue's name and aliases follow, which covers a
    cache written before this was recorded.
    """
    crudos: list[str] = []
    grabado = _read_cached_names().get(slug)
    if grabado:
        crudos.append(grabado)

    equipo = champions_teams.load_catalog().get(slug)
    if equipo:
        crudos.extend((equipo["nombre"], *equipo.get("alias", [])))

    # /<Club> does not take spaces: "Inter" returns 6112 rows, "Paris SG"
    # returns HTTP 200 with an EMPTY body rather than an error. So every
    # candidate is also tried with the spaces stripped, and an empty response
    # has to be treated as "wrong spelling", not as "this club has no history".
    candidatos: list[str] = []
    for nombre in crudos:
        for variante in (nombre, nombre.replace(" ", "")):
            if variante and variante not in candidatos:
                candidatos.append(variante)
    return candidatos


def _read_history_cache() -> dict:
    try:
        return json.loads(HISTORY_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_elo_history(slug: str) -> list[dict]:
    """
    A club's Elo over time, newest last: [{"desde", "hasta", "elo"}, ...].

    Feeds the verifiable-form facts in champions_facts.py — this endpoint is
    the only free source we have for "how has this club been trending", since
    ClubElo publishes ratings and fixtures but never results.

    Cached for a week: every row but the last describes the past and never
    changes, and a matchday render does not need the tail fresher than that.

    Returns [] when the club can't be resolved or clubelo.com is unreachable.
    Callers must treat that as "no trend fact available", never as an error —
    the whole point of this layer is that a missing fact costs us one headline
    angle, not the video.
    """
    cache = _read_history_cache()
    entrada = cache.get(slug)
    if entrada:
        try:
            edad = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(entrada["timestamp"])
            ).total_seconds() / 3600
            if edad < HISTORY_CACHE_MAX_AGE_HOURS:
                return entrada["historico"]
        except (KeyError, ValueError):
            pass

    historico: list[dict] = []
    for candidato in _clubelo_name(slug):
        texto = _get_reintentando(CLUBELO_CLUB_URL.format(club=quote(candidato)))
        if texto is None:
            # Upstream is down, not a bad spelling — trying the next candidate
            # would just burn more retries against the same dead server.
            break
        filas = list(csv.DictReader(io.StringIO(texto)))

        for fila in filas:
            try:
                historico.append({
                    "desde": fila["From"],
                    "hasta": fila["To"],
                    "elo": round(float(fila["Elo"]), 1),
                })
            except (KeyError, TypeError, ValueError):
                continue
        if historico:
            break

    if not historico:
        print(f"[INFO] Sin histórico de Elo para «{slug}» — se omite el hecho de forma")
        return []

    cache[slug] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "historico": historico,
    }
    try:
        HISTORY_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        HISTORY_CACHE_FILE.write_text(
            json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        print(f"[WARN] No se pudo escribir la caché de históricos: {exc}")

    return historico


if __name__ == "__main__":
    tabla = get_elo_table(force_refresh=True)
    catalogo = champions_teams.load_catalog()

    sin_elo = [s for s in catalogo if s not in tabla]
    print(f"\nClubes del catálogo con Elo: {len(tabla)}/{len(catalogo)}")
    if sin_elo:
        print(f"Sin Elo en ClubElo: {sin_elo}")

    print("\nTop 12:")
    for slug, elo in sorted(tabla.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {catalogo[slug]['nombre']:<14} {elo:>7.1f}")
