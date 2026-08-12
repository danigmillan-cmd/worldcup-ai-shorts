"""
laliga_seleccion.py
Which Spanish matches the channel publishes.

This is the preference half of the Spanish league support — pure editorial
taste, deliberately kept out of laliga.py so the fetching code stays reusable
by anyone whose taste differs. Everything that encodes a choice lives in the
block of constants at the top.

The rule, as specified:
  - four clubs are always in, Valencia among them because it's the owner's club
  - early in the season, before the table means anything, two more clubs stand
    in for "popular" on reputation
  - from matchday 10 the table has enough matches behind it to be worth
    reading, so the standing-in pair gives way to whoever is actually near the
    top

Public API:
    equipos_publicables(jornada=None, tabla=None) -> set[str]
    partidos_publicables(partidos, ...) -> list[dict]
"""
from datetime import date

import laliga

# --- Preference, all of it --------------------------------------------------
# Always published, whatever the table says. Valencia is here because it's
# Dani's club, not because of its size — that is the whole reason this is a
# named constant and not a "top N by Elo".
NUCLEO = ("real-madrid", "barcelona", "atletico", "valencia")

# Before the table means anything, these stand in for "popular". Chosen on
# reputation, and dropped the moment real standings exist.
POPULARES_PRETEMPORADA = ("villarreal", "betis")

# From this matchday on, the table replaces the stand-ins. Ten is roughly a
# quarter of the season: enough for the table to reflect form rather than
# fixture luck, early enough that most of the season uses the real rule.
JORNADA_CORTE = 10

# How far down the table still counts as "arriba". Six is the European-places
# line, which is a boundary a viewer already recognises.
CUPO_TABLA = 6

# How matches get ordered once they're eligible. The Short only shows three or
# four, so this decides what actually airs.
PESO_VALENCIA = 3.0   # the owner's club leads the Short when it plays
PESO_NUCLEO = 1.0     # per core club involved
PESO_ELO = 0.001      # tiebreak: combined Elo, scaled to stay below the above

# Penalty per day a match sits beyond the earliest one on the shortlist.
#
# Without this the ordering is decided by Elo noise: Barcelona-Athletic (round
# three) beat Elche-Barcelona (round two) by 0.06 points of combined Elo, so a
# Short meant to preview this week previewed a fortnight out. The widening
# window is a fallback for a round with nobody in it, not a licence to prefer
# later fixtures.
#
# 0.05/day is deliberately between the two scales it has to separate: four days
# costs 0.2, which comfortably outweighs the ~0.1 that Elo spans, and stays far
# below the 1.0 a core club is worth — so "sooner" breaks ties without ever
# overriding "more interesting".
PESO_DIA = 0.05

# How many matches the Short wants, and how far ahead we'll look to find them.
#
# Filtering to six clubs out of twenty means a single round often yields too
# few. Round 1 of 2026-27 is the worst case and it is not hypothetical: none of
# Real Madrid, Barcelona, Valencia or Betis play in it at all, so a window
# covering only that round produces a two-match Short. So the window grows
# until there is enough, rather than being pinned to one round — this channel
# publishes "the next matches you care about", not "matchday N".
MIN_PARTIDOS = 3
MAX_PARTIDOS = 4
DIAS_INICIAL = 8
DIAS_MAXIMO = 21
# --- End preference ---------------------------------------------------------


def equipos_publicables(
    jornada: int | None = None,
    tabla: list[dict] | None = None,
) -> set[str]:
    """
    The clubs whose matches are worth publishing this week.

    Falls back to NUCLEO + POPULARES_PRETEMPORADA whenever the table can't be
    read — pre-season, or ESPN down. That is the same set the season opens
    with, so a dead upstream degrades to "publish the usual clubs" instead of
    to an empty Short.

    Note ESPN orders a not-yet-started league alphabetically with every club on
    zero points, so `puesto` before a ball is kicked is meaningless. The
    matchday guard below is what keeps that out.
    """
    if tabla is None:
        tabla = laliga.clasificacion()
    if jornada is None:
        jornada = laliga.jornada_actual(tabla)

    seleccion = set(NUCLEO)

    if jornada < JORNADA_CORTE or not tabla:
        seleccion.update(POPULARES_PRETEMPORADA)
        return seleccion

    arriba = [e["slug"] for e in sorted(tabla, key=lambda e: e["puesto"])[:CUPO_TABLA]]
    seleccion.update(arriba)
    return seleccion


def _interes(
    partido: dict,
    elo_table: dict[str, float],
    fecha_base: str | None = None,
) -> float:
    """Score one eligible match, higher first."""
    lados = (partido["local"], partido["visitante"])
    puntuacion = 0.0

    if "valencia" in lados:
        puntuacion += PESO_VALENCIA
    puntuacion += PESO_NUCLEO * sum(1 for s in lados if s in NUCLEO)
    puntuacion += PESO_ELO * sum(elo_table.get(s, 0.0) for s in lados)

    if fecha_base and partido.get("fecha"):
        try:
            dias = (
                date.fromisoformat(partido["fecha"]) - date.fromisoformat(fecha_base)
            ).days
            puntuacion -= PESO_DIA * max(0, dias)
        except ValueError:
            pass

    return puntuacion


def partidos_publicables(
    partidos: list[dict] | None = None,
    jornada: int | None = None,
    tabla: list[dict] | None = None,
    elo_table: dict[str, float] | None = None,
    maximo: int | None = None,
) -> list[dict]:
    """
    The matchday's fixtures, filtered to the selected clubs and ordered.

    A match qualifies if EITHER side is selected — the point is to show the
    clubs people follow, and those clubs play the rest of the league most
    weeks. Ordering then decides which of the qualifying matches actually fit
    in the Short.
    """
    import champions_elo

    if partidos is None:
        partidos = laliga.proximos_partidos()
    if elo_table is None:
        elo_table = champions_elo.get_elo_table()

    seleccion = equipos_publicables(jornada, tabla)

    elegibles = [
        p for p in partidos
        if p["local"] in seleccion or p["visitante"] in seleccion
    ]
    # Recency is measured from the earliest eligible match, not from today, so
    # an international break doesn't flatten the penalty across the shortlist.
    fecha_base = min((p["fecha"] for p in elegibles if p.get("fecha")), default=None)
    elegibles.sort(key=lambda p: _interes(p, elo_table, fecha_base), reverse=True)

    return elegibles[:maximo] if maximo else elegibles


def _sin_repetir_club(partidos: list[dict]) -> list[dict]:
    """
    Keep the best match per club, preserving order.

    Widening the window past one round means a club can turn up twice — with
    six selected clubs out of twenty, Valencia's next two fixtures easily
    outscore everything else. On screen that reads as a bug rather than as an
    editorial choice, so each club appears at most once and the lower-scoring
    fixture makes way for a different match.
    """
    vistos: set[str] = set()
    salida: list[dict] = []
    for partido in partidos:
        lados = {partido["local"], partido["visitante"]}
        if lados & vistos:
            continue
        vistos |= lados
        salida.append(partido)
    return salida


def seleccion_para_short(
    minimo: int = MIN_PARTIDOS,
    maximo: int = MAX_PARTIDOS,
    dias_max: int = DIAS_MAXIMO,
) -> list[dict]:
    """
    The matches to put in the next Short, widening the window until there are
    enough.

    Returns fewer than `minimo` only when even `dias_max` doesn't produce them
    (an international break, or ESPN down). Callers should check the length
    rather than assume: a Short with two matches renders, but comes in under
    the 35-second floor the channel aims for.
    """
    import champions_elo

    tabla = laliga.clasificacion()
    jornada = laliga.jornada_actual(tabla)
    elo_table = champions_elo.get_elo_table()

    elegidos: list[dict] = []
    dias = DIAS_INICIAL
    while dias <= dias_max:
        elegidos = _sin_repetir_club(
            partidos_publicables(
                laliga.proximos_partidos(dias), jornada, tabla, elo_table
            )
        )
        if len(elegidos) >= minimo:
            break
        print(f"[INFO] Solo {len(elegidos)} partidos en {dias} días — amplío la ventana")
        dias += 7

    if len(elegidos) < minimo:
        print(f"[WARN] Solo {len(elegidos)} partidos publicables en {dias_max} días")

    return elegidos[:maximo]


if __name__ == "__main__":
    import champions_elo
    import champions_teams

    tabla = laliga.clasificacion()
    jornada = laliga.jornada_actual(tabla)
    seleccion = equipos_publicables(jornada, tabla)
    fase = "pretemporada / tabla sin valor" if jornada < JORNADA_CORTE else "por tabla"

    print(f"Jornada {jornada} — selección {fase}")
    print("Equipos publicables:")
    for slug in sorted(seleccion):
        marca = " (núcleo)" if slug in NUCLEO else ""
        print(f"  - {champions_teams.resolve_team(slug)['nombre']}{marca}")

    elegidos = seleccion_para_short()
    print(f"\nAl Short van {len(elegidos)} partidos:")
    for p in elegidos:
        local = champions_teams.resolve_team(p["local"])["nombre"]
        visitante = champions_teams.resolve_team(p["visitante"])["nombre"]
        print(f"  {p['fecha']}  {local:14} - {visitante}")
