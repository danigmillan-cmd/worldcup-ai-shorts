"""
champions_facts.py
Verifiable facts about a matchday, for the headline writer to phrase.

Why this module exists
----------------------
The `titular` on each match reads like sports journalism — "el Inter no marcó
en 4 de sus 5 últimas visitas", "Liverpool no pierde fuera desde marzo". Those
are claims about match results, and we have no source of results: ClubElo
publishes ratings and fixtures, never scorelines. Handing a match to an LLM and
asking for an editorial line therefore produces invented statistics, delivered
with total confidence. A predictions channel publishing made-up stats has a
credibility problem that no amount of good phrasing fixes.

So the writer never gets to invent. This module computes facts that are true by
construction — derived from our own model output, from the Elo table, and from
ClubElo's per-club Elo history — and champions_titulares.py hands only those
facts to Claude, which phrases them and nothing else.

What that costs: the range of angles is narrower than a human writer's. What it
buys: every claim on screen can be traced back to a number.

Public API:
    facts_por_partido(partidos, elo_table=None) -> list[list[dict]]
    mejor_hecho_por_partido(partidos, elo_table=None) -> list[dict]
    PESOS
"""
from datetime import date, datetime

import champions_elo
import champions_teams

# --- Preference, not engine -------------------------------------------------
# Which angles are worth a headline, and how strongly. These are editorial
# taste for THIS channel: another channel would rank them differently, so they
# live here as named constants rather than being buried in the selection code.
PESOS = {
    # A near coin-flip is the single most interesting thing we can honestly say.
    "equilibrio": 1.00,
    # A lopsided favourite is the second — it sets up the "will it happen" hook.
    "favorito": 0.85,
    # Form is compelling but weaker: an Elo swing is a real fact, yet a viewer
    # feels it less directly than a probability.
    "tendencia": 0.75,
    "hueco_elo": 0.55,
    "marcador": 0.40,
}

# A match counts as "the tight one" only below this spread between the two
# win probabilities. Above it the claim stops being interesting.
UMBRAL_EQUILIBRIO = 0.08

# And as "the clear favourite" only above this single-outcome probability.
UMBRAL_FAVORITO = 0.60

# Elo gap worth mentioning on its own. Below this the two clubs are peers and
# the number says nothing a viewer cares about.
UMBRAL_HUECO_ELO = 120.0

# Window for the form fact, and the swing that makes it worth saying. ClubElo
# moves a few points per match, so 40 points over a season-ish window is a
# genuine change of level rather than noise.
DIAS_TENDENCIA = 180
UMBRAL_TENDENCIA = 40.0
# --- End preference ---------------------------------------------------------


# A fact that only just clears its threshold is still that kind of fact, and
# should still outrank a weaker kind. Scoring strength as a bare distance above
# the threshold sends it to zero right at the bar — which ranked a 60%
# favourite BELOW "el marcador más probable es 1-0", the weakest angle we have.
# Strength therefore spans this floor to 1, never 0 to 1.
FUERZA_MINIMA = 0.5

# How stale "no estaba tan alto desde X" has to be before it's worth saying.
# Without this, a club that wobbled during an overall rise gets "no estaba tan
# alto desde hace diez días", which is true and absurd.
DIAS_MINIMOS_RECORD = 365


def _fuerza(normalizado: float) -> float:
    """Map a 0-1 'how far past the threshold' into FUERZA_MINIMA..1."""
    acotado = max(0.0, min(1.0, normalizado))
    return FUERZA_MINIMA + (1.0 - FUERZA_MINIMA) * acotado


def _elo_en(historico: list[dict], objetivo: date) -> float | None:
    """The club's Elo on a given date, or None if the history doesn't reach."""
    anterior = None
    for fila in historico:
        try:
            desde = date.fromisoformat(fila["desde"])
        except (KeyError, ValueError):
            continue
        if desde > objetivo:
            break
        anterior = fila
    return anterior["elo"] if anterior else None


def _mejor_desde(historico: list[dict], actual: float) -> date | None:
    """
    How far back you have to go to find this club rated higher than `actual`.

    Returns the date its Elo was last above the current one, or None if the
    whole history is below it (i.e. this is an all-time high — rare, and worth
    saying differently).
    """
    for fila in reversed(historico):
        try:
            if fila["elo"] > actual:
                return date.fromisoformat(fila["hasta"])
        except (KeyError, ValueError):
            continue
    return None


def _tendencia(slug: str, hoy: date) -> dict | None:
    """
    Form fact from the Elo curve, or None when there isn't a real one.

    This is the only window we have onto form. It is not the same thing as
    results — a club can gain Elo while drawing — but it is honest about what
    it measures, which "no pierde fuera desde marzo" would not be.
    """
    historico = champions_elo.get_elo_history(slug)
    if len(historico) < 2:
        return None

    actual = historico[-1]["elo"]
    pasado = _elo_en(historico, date.fromordinal(hoy.toordinal() - DIAS_TENDENCIA))
    if pasado is None:
        return None

    delta = actual - pasado
    if abs(delta) < UMBRAL_TENDENCIA:
        return None

    nombre = champions_teams.resolve_team(slug)["nombre"]
    fuerza = _fuerza(abs(delta) / 120.0)

    if delta > 0:
        desde = _mejor_desde(historico, actual)
        antiguedad = (hoy - desde).days if desde else None

        if desde is None:
            detalle = f"; es su Elo más alto registrado ({actual:.0f})"
        elif antiguedad is not None and antiguedad >= DIAS_MINIMOS_RECORD:
            detalle = f"; no estaba tan alto ({actual:.0f}) desde {desde.isoformat()}"
        else:
            # It was higher recently — the rise is real but "best since" would
            # be a silly claim, so the fact is just the rise.
            detalle = f" (ahora {actual:.0f})"

        return {
            "tipo": "tendencia",
            "texto": f"{nombre} ha subido {delta:.0f} puntos de Elo en los "
                     f"últimos {DIAS_TENDENCIA} días{detalle}",
            "fuerza": fuerza,
        }

    return {
        "tipo": "tendencia",
        "texto": f"{nombre} ha perdido {abs(delta):.0f} puntos de Elo en los "
                 f"últimos {DIAS_TENDENCIA} días (ahora {actual:.0f})",
        "fuerza": fuerza,
    }


def facts_por_partido(
    partidos: list[dict],
    elo_table: dict[str, float] | None = None,
    hoy: date | None = None,
) -> list[list[dict]]:
    """
    Every verifiable fact for every match, strongest first.

    `partidos` are matches as champions_teams.build_match_from_elo returns
    them: resolved teams plus the model's probabilities and scoreline. Facts
    that need the matchday as a whole (the tightest match, the biggest
    favourite) are computed across the list, which is why this takes the whole
    matchday rather than one match at a time.
    """
    hoy = hoy or date.today()
    tabla = elo_table if elo_table is not None else champions_elo.get_elo_table()

    margenes = [
        abs(p.get("probLocal", 0.0) - p.get("probVisitante", 0.0)) for p in partidos
    ]
    favoritismos = [
        max(p.get("probLocal", 0.0), p.get("probVisitante", 0.0)) for p in partidos
    ]
    idx_mas_igualado = margenes.index(min(margenes)) if margenes else -1
    idx_mas_favorito = favoritismos.index(max(favoritismos)) if favoritismos else -1

    salida: list[list[dict]] = []
    for i, partido in enumerate(partidos):
        hechos: list[dict] = []
        local = partido["local"]["nombre"]
        visitante = partido["visitante"]["nombre"]

        if i == idx_mas_igualado and margenes[i] < UMBRAL_EQUILIBRIO:
            hechos.append({
                "tipo": "equilibrio",
                "texto": f"es el partido más igualado de la jornada: "
                         f"{partido['probLocal']:.0%} local, "
                         f"{partido['probEmpate']:.0%} empate, "
                         f"{partido['probVisitante']:.0%} visitante",
                "fuerza": _fuerza(1.0 - margenes[i] / UMBRAL_EQUILIBRIO),
            })

        if i == idx_mas_favorito and favoritismos[i] > UMBRAL_FAVORITO:
            gana = local if partido["probLocal"] >= partido["probVisitante"] else visitante
            hechos.append({
                "tipo": "favorito",
                "texto": f"{gana} es el favorito más claro de la jornada, "
                         f"con {favoritismos[i]:.0%} de ganar",
                "fuerza": _fuerza((favoritismos[i] - UMBRAL_FAVORITO) / 0.30),
            })

        slug_l = champions_teams._lookup_index().get(champions_teams._normalize(local))
        slug_v = champions_teams._lookup_index().get(
            champions_teams._normalize(visitante)
        )
        if slug_l and slug_v and slug_l in tabla and slug_v in tabla:
            hueco = tabla[slug_l] - tabla[slug_v]
            if abs(hueco) >= UMBRAL_HUECO_ELO:
                arriba, abajo = (
                    (local, visitante) if hueco > 0 else (visitante, local)
                )
                hechos.append({
                    "tipo": "hueco_elo",
                    "texto": f"{arriba} está {abs(hueco):.0f} puntos de Elo por "
                             f"encima de {abajo} ({tabla[slug_l]:.0f} contra "
                             f"{tabla[slug_v]:.0f})",
                    "fuerza": _fuerza(abs(hueco) / 300.0),
                })

        for slug in (slug_l, slug_v):
            if slug:
                tendencia = _tendencia(slug, hoy)
                if tendencia:
                    hechos.append(tendencia)

        if partido.get("prediccion"):
            hechos.append({
                "tipo": "marcador",
                "texto": f"el marcador más probable es {partido['prediccion']} "
                         f"({local} contra {visitante})",
                "fuerza": 0.5,
            })

        hechos.sort(key=lambda h: PESOS.get(h["tipo"], 0.0) * h["fuerza"], reverse=True)
        salida.append(hechos)

    return salida


def mejor_hecho_por_partido(
    partidos: list[dict],
    elo_table: dict[str, float] | None = None,
    hoy: date | None = None,
) -> list[dict]:
    """
    One fact per match, chosen so the matchday doesn't repeat an angle.

    Four matches all headlined "X is N points of Elo above Y" would be four
    true statements and a boring Short, so a fact type already used is skipped
    while any alternative remains. `equilibrio` and `favorito` are unique by
    construction; `tendencia` and `hueco_elo` are the ones that would otherwise
    repeat.
    """
    todos = facts_por_partido(partidos, elo_table, hoy)
    usados: set[str] = set()
    elegidos: list[dict] = []

    for hechos in todos:
        elegido = next((h for h in hechos if h["tipo"] not in usados), None)
        if elegido is None:
            # Every angle for this match is already spoken for. Repeat the
            # strongest rather than leave the match without a headline.
            elegido = hechos[0] if hechos else {
                "tipo": "ninguno",
                "texto": "",
                "fuerza": 0.0,
            }
        usados.add(elegido["tipo"])
        elegidos.append(elegido)

    return elegidos


if __name__ == "__main__":
    import json
    import sys

    ruta = sys.argv[1] if len(sys.argv) > 1 else "remotion/sample-data/jornada.json"
    jornada = json.loads(open(ruta, encoding="utf-8").read())
    for partido, hecho in zip(
        jornada["partidos"], mejor_hecho_por_partido(jornada["partidos"])
    ):
        print(f"{partido['local']['nombre']} - {partido['visitante']['nombre']}")
        print(f"  [{hecho['tipo']}] {hecho['texto']}\n")
