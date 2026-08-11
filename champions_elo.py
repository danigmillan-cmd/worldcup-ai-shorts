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
from datetime import date, datetime, timezone
from pathlib import Path

import requests

import champions_teams

CLUBELO_URL = "http://api.clubelo.com/{fecha}"
CACHE_FILE = Path(__file__).parent / "data" / "clubelo_cache.json"
SOURCE_FILE = Path(__file__).parent / "data" / "clubelo_source.json"

# Reuse the cache for this long before hitting the network again. ClubElo
# recomputes daily, and a matchday render doesn't need fresher than that.
CACHE_MAX_AGE_HOURS = 24

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


def _fetch_clubelo(timeout: int = 15) -> dict[str, float]:
    """
    Download today's CSV and map it onto the catalogue's slugs.

    ClubElo covers ~600 clubs; only the ones in the catalogue are kept. It uses
    its own spellings ("Paris SG", "Bilbao", "Karabakh Agdam", "Bodoe Glimt"),
    which is why those live as aliases in data/equipos_champions.json — they
    were checked against a real response, not guessed.
    """
    url = CLUBELO_URL.format(fecha=date.today().isoformat())
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()

    index = champions_teams._lookup_index()
    tabla: dict[str, float] = {}

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

    if not tabla:
        raise ValueError("ClubElo respondió pero no casó ningún club del catálogo")
    return tabla


def _read_cache() -> tuple[dict[str, float], float] | None:
    """Return (table, age_in_hours) or None if there's no readable cache."""
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        guardado = datetime.fromisoformat(payload["timestamp"])
        edad = (datetime.now(timezone.utc) - guardado).total_seconds() / 3600
        return payload["elo"], edad
    except (OSError, KeyError, ValueError):
        return None


def _write_cache(tabla: dict[str, float]) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "fecha_datos": date.today().isoformat(),
                    "elo": tabla,
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
        tabla = _fetch_clubelo()
        print(f"[INFO] ClubElo: descargado en vivo ({len(tabla)} clubes)")
        _write_cache(tabla)
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
