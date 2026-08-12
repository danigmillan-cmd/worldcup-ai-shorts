"""
champions_teams.py
Club catalogue and matchday-JSON builder for the Champions predictions Shorts.

Resolves a club name (however the upstream data source spells it) into the
display name and colour pair that the Remotion project expects, and assembles
the matchday JSON that gets passed to `npx remotion render Short --props=...`.

The Remotion project never reads the catalogue: colours are written inline into
the matchday JSON. That keeps the video layer dumb — changing a colour in the
emitted JSON is reflected without touching any code.

Public API:
    resolve_team(name) -> dict
    build_match(local, visitante, probs, prediccion, titular) -> dict
    build_matchday(competicion, fecha, aciertos, partidos, ranking) -> dict
    find_color_collisions() -> list[tuple[str, str, int]]
"""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path(__file__).parent / "data" / "equipos_champions.json"

# Must stay in sync with UMBRAL_COLISION in
# remotion/src/lib/colores-equipo.ts. Below this perceptual distance two team
# colours read as the same bar and the renderer swaps the away side to its
# secondary colour.
COLLISION_THRESHOLD = 120

# Noise words stripped before matching: "FC Bayern München" and "Bayern" have
# to resolve to the same entry.
_NOISE = {
    "fc", "cf", "ac", "sc", "afc", "ssc", "as", "sl", "rb", "vfb", "losc",
    "club", "de", "the", "1", "04", "08", "09", "1899", "1900", "1909",
}


def _normalize(name: str) -> str:
    """Lowercase, strip accents and drop club-name noise words."""
    plain = unicodedata.normalize("NFKD", name)
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    plain = re.sub(r"[^\w\s]", " ", plain.lower())
    words = [w for w in plain.split() if w not in _NOISE]
    return " ".join(words)


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    """Load the club catalogue, keyed by slug."""
    with CATALOG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)["equipos"]


@lru_cache(maxsize=1)
def _lookup_index() -> dict[str, str]:
    """Normalized name/alias/slug -> slug."""
    index: dict[str, str] = {}
    for slug, team in load_catalog().items():
        for key in (slug, team["nombre"], *team.get("alias", [])):
            index[_normalize(key)] = slug
    return index


def _hsl_to_hex(hue: float, sat: float, light: float) -> str:
    """HSL (0-360, 0-1, 0-1) to #RRGGBB."""
    chroma = (1 - abs(2 * light - 1)) * sat
    second = chroma * (1 - abs((hue / 60) % 2 - 1))
    offset = light - chroma / 2
    table = [
        (chroma, second, 0), (second, chroma, 0), (0, chroma, second),
        (0, second, chroma), (second, 0, chroma), (chroma, 0, second),
    ]
    r, g, b = table[int(hue // 60) % 6]
    return "#{:02X}{:02X}{:02X}".format(
        round((r + offset) * 255), round((g + offset) * 255), round((b + offset) * 255)
    )


def _fallback_team(name: str) -> dict:
    """
    Invent a stable colour for a club that isn't catalogued.

    The league-phase draw happens in late August and the play-off round decides
    the last slots, so the catalogue will always be missing somebody. Falling
    back to a fixed grey would put two identical grey bars on screen the first
    time two unknowns meet; deriving the hue from the name keeps them apart and
    keeps the same club the same colour across every video.

    Saturation and lightness are fixed at values that already clear the
    contrast floor against the dark background, so `readableOn()` on the
    Remotion side leaves them alone.
    """
    digest = sum((i + 1) * ord(c) for i, c in enumerate(_normalize(name)))
    return {
        "nombre": name[:14],
        "colorPrimario": _hsl_to_hex(digest % 360, 0.72, 0.55),
        "colorSecundario": _hsl_to_hex((digest * 7 + 180) % 360, 0.60, 0.70),
        "_fallback": True,
    }


def resolve_team(name: str) -> dict:
    """
    Resolve a club name into {nombre, colorPrimario, colorSecundario}.

    Accepts the slug, the display name or any alias, in any capitalisation and
    with or without accents. Never raises: unknown clubs get a derived colour
    and are flagged with `_fallback` so the caller can log them.
    """
    slug = _lookup_index().get(_normalize(name))
    if slug is None:
        return _fallback_team(name)

    team = load_catalog()[slug]
    return {
        "nombre": team["nombre"],
        "colorPrimario": team["colorPrimario"],
        "colorSecundario": team["colorSecundario"],
    }


def build_match(
    local: str,
    visitante: str,
    prob_local: float,
    prob_empate: float,
    prob_visitante: float,
    prediccion: str,
    titular: str,
    resultado_predicho: str | None = None,
) -> dict:
    """Assemble one match in the shape the Remotion schema expects."""
    match = {
        "local": resolve_team(local),
        "visitante": resolve_team(visitante),
        "probLocal": round(prob_local, 4),
        "probEmpate": round(prob_empate, 4),
        "probVisitante": round(prob_visitante, 4),
        "prediccion": prediccion,
        "titular": titular,
    }
    if resultado_predicho is not None:
        match["resultadoPredicho"] = resultado_predicho
    return match


def build_match_from_elo(
    local: str,
    visitante: str,
    titular: str,
    fecha: str = "",
    elo_local: float | None = None,
    elo_visitante: float | None = None,
    elo_table: dict[str, float] | None = None,
    constantes: dict | None = None,
) -> dict:
    """
    Assemble one match straight from the two clubs' Elo ratings.

    Ratings are pulled from clubelo.com unless passed explicitly. Pass
    `elo_table` (from champions_elo.get_elo_table()) when building a whole
    matchday, so the network/cache is hit once instead of once per club.

    `local` gets the home-advantage bonus. The scoreline draw is seeded on the
    fixture so re-rendering the same matchday never changes the prediction.

    Imported lazily: champions_elo imports this module for name resolution, so
    a module-level import here would be circular.
    """
    import champions_elo
    import champions_predictions

    if elo_local is None or elo_visitante is None:
        tabla = champions_elo.get_elo_table() if elo_table is None else elo_table
        if elo_local is None:
            elo_local = champions_elo.get_elo(local, tabla)
        if elo_visitante is None:
            elo_visitante = champions_elo.get_elo(visitante, tabla)

    seed = f"{fecha}|{_normalize(local)}|{_normalize(visitante)}"
    prediction = champions_predictions.predict(
        elo_local, elo_visitante, seed, constantes
    )

    return {
        "local": resolve_team(local),
        "visitante": resolve_team(visitante),
        "titular": titular,
        **prediction,
    }


def build_matchday(
    competicion: str,
    fecha: str,
    acertados: int,
    total: int,
    partidos: list[dict],
    ranking: list[tuple[str, float]],
) -> dict:
    """
    Assemble the full matchday JSON.

    `ranking` is a list of (club name, title probability); it gets sorted
    descending and trimmed to the five the countdown shows.
    """
    top = sorted(ranking, key=lambda entry: entry[1], reverse=True)[:5]
    return {
        "competicion": competicion,
        "fecha": fecha,
        "aciertosJornadaAnterior": {"acertados": acertados, "total": total},
        "partidos": partidos,
        "ranking": [
            {
                "equipo": resolve_team(name)["nombre"],
                "colorPrimario": resolve_team(name)["colorPrimario"],
                "probTitulo": round(prob, 4),
            }
            for name, prob in top
        ],
    }


def _color_distance(a: str, b: str) -> float:
    """
    Perceptual "redmean" distance. Mirrors distanciaColor() in
    remotion/src/lib/color.ts — keep both in sync.

    Note this is NOT WCAG contrast: contrast only measures luminance, so a red
    and a green of equal brightness score as identical while being perfectly
    distinguishable.
    """
    ar, ag, ab = (int(a[i:i + 2], 16) for i in (1, 3, 5))
    br, bg, bb = (int(b[i:i + 2], 16) for i in (1, 3, 5))
    dr, dg, db = ar - br, ag - bg, ab - bb
    r_mean = (ar + br) / 2
    return (
        (2 + r_mean / 256) * dr * dr
        + 4 * dg * dg
        + (2 + (255 - r_mean) / 256) * db * db
    ) ** 0.5


def find_color_collisions() -> list[tuple[str, str, int]]:
    """
    Every pair in the catalogue whose primaries are too close to tell apart.

    These pairings still render fine — the Remotion side swaps the away team to
    its secondary colour — but the list is worth eyeballing when curating the
    catalogue, because it shows which clubs will never appear in their real
    colour when drawn against each other.
    """
    teams = list(load_catalog().items())
    collisions = []
    for i, (slug_a, a) in enumerate(teams):
        for slug_b, b in teams[i + 1:]:
            distance = _color_distance(a["colorPrimario"], b["colorPrimario"])
            if distance < COLLISION_THRESHOLD:
                collisions.append((slug_a, slug_b, round(distance)))
    return sorted(collisions, key=lambda row: row[2])


if __name__ == "__main__":
    catalog = load_catalog()
    print(f"Clubes en el catálogo: {len(catalog)}")

    long_names = [t["nombre"] for t in catalog.values() if len(t["nombre"]) > 14]
    print(f"Nombres de más de 14 caracteres: {long_names or 'ninguno'}")

    collisions = find_color_collisions()
    print(f"\nPares que chocan en color ({len(collisions)}):")
    for slug_a, slug_b, distance in collisions:
        print(f"  {distance:>4}  {slug_a} / {slug_b}")
