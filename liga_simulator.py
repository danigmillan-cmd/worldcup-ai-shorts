"""
liga_simulator.py
Monte Carlo over a league season -> real "probability of winning the title".

This is what the Short's closing countdown needs. Every other number the
channel shows is computed rather than asserted, and a title race is no
exception: the ranking comes out of playing the remaining fixtures thousands
of times with the same Poisson model that produces the match predictions, so
the countdown stays mutually coherent with the bars in the body of the video.

Relationship to the World Cup simulators
---------------------------------------
tournament_simulator.py is hardwired to that format — 12 fixed groups plus a
knockout bracket — so it cannot be pointed at a league. group_simulator.py is
closer (round-robin, points, tiebreak) but always starts from zero, and a
league is simulated mid-season from the standing table. What is reused is the
part that matters for coherence: prediction_engine's scoreline matrix.

Sampling is deliberately not group_simulator's `sample_from_matrix`. That
recomputes the matrix total and linearly scans 49 cells on every draw, which
is fine for a 4-team group's 6 fixtures and not for 380 of them: a season is
~16x faster per draw from a cumulative table built once per fixture, and the
speed buys simulation count, which is what resolves a 1%-chance club from a
0.2%-chance one.

Approximations, all deliberate:
  - Tiebreak is goal difference then goals for, not LaLiga's head-to-head.
    Head-to-head needs the full result grid per simulation and moves the top
    of the table almost never; the countdown only shows five clubs.
  - Elo is frozen at today's values. Clubs drift over a season, but the drift
    is unknowable in advance and modelling it would be inventing.

Public API:
    probabilidades_titulo(...) -> list[dict]
    simular(...) -> dict
"""
import bisect
import random
from datetime import date

import champions_predictions
import prediction_engine as pe

# Enough draws that the fifth-placed club's figure is stable to a tenth of a
# point between runs, which is the precision the countdown displays. Costs a
# few seconds; the result is cached by the caller, not recomputed per render.
N_SIMULACIONES = 20000

# How many clubs the countdown shows.
TOP_RANKING = 5

PUNTOS_VICTORIA = 3
PUNTOS_EMPATE = 1


def _tabla_acumulada(matriz: list[list[float]]) -> tuple[list[float], list[tuple[int, int]], float]:
    """Flatten a scoreline matrix into (cutoffs, scorelines, total) for bisect."""
    cortes: list[float] = []
    marcadores: list[tuple[int, int]] = []
    acumulado = 0.0
    for i, fila in enumerate(matriz):
        for j, p in enumerate(fila):
            acumulado += p
            cortes.append(acumulado)
            marcadores.append((i, j))
    return cortes, marcadores, acumulado


def preparar_partidos(
    pendientes: list[dict],
    elo_table: dict[str, float],
    constantes: dict | None = None,
) -> list[tuple[str, str, list[float], list[tuple[int, int]], float]]:
    """
    Build the sampling table for each remaining fixture, once.

    Depends only on the two Elos and who is at home, so it is hoisted out of
    the simulation loop entirely — this is the whole reason a full season is
    cheap to simulate many times.
    """
    constantes = constantes or champions_predictions.LALIGA_CONSTANTS
    preparados = []
    for partido in pendientes:
        local, visitante = partido["local"], partido["visitante"]
        matriz = pe.match_matrix(
            elo_table.get(local, 1500.0),
            elo_table.get(visitante, 1500.0),
            host_a=True,
            **constantes,
        )
        cortes, marcadores, total = _tabla_acumulada(matriz)
        preparados.append((local, visitante, cortes, marcadores, total))
    return preparados


def simular(
    tabla: list[dict],
    pendientes: list[dict],
    elo_table: dict[str, float],
    n_sims: int = N_SIMULACIONES,
    constantes: dict | None = None,
    semilla: int | str | None = None,
) -> dict:
    """
    Play the rest of the season `n_sims` times.

    Returns {"titulos": {slug: veces}, "n_sims": n, "puntos_medios": {...}}.

    `tabla` is the current standings (laliga.clasificacion()); clubs start from
    the points and goals they already have, so this works at any point in the
    season, including before a ball is kicked when every club starts at zero.

    `semilla` makes a run reproducible — pass the matchday date so the same
    Short rendered twice shows the same percentages.
    """
    rng = random.Random(semilla)
    preparados = preparar_partidos(pendientes, elo_table, constantes)

    equipos = [e["slug"] for e in tabla]
    puntos_base = {e["slug"]: e.get("puntos", 0) for e in tabla}
    gf_base = {e["slug"]: e.get("goles_favor", 0) for e in tabla}
    gc_base = {e["slug"]: e.get("goles_contra", 0) for e in tabla}

    titulos = {s: 0 for s in equipos}
    puntos_totales = {s: 0 for s in equipos}

    aleatorio = rng.random
    for _ in range(n_sims):
        puntos = dict(puntos_base)
        gf = dict(gf_base)
        gc = dict(gc_base)

        for local, visitante, cortes, marcadores, total in preparados:
            goles_l, goles_v = marcadores[
                bisect.bisect_left(cortes, aleatorio() * total)
            ]
            gf[local] = gf.get(local, 0) + goles_l
            gc[local] = gc.get(local, 0) + goles_v
            gf[visitante] = gf.get(visitante, 0) + goles_v
            gc[visitante] = gc.get(visitante, 0) + goles_l

            if goles_l > goles_v:
                puntos[local] = puntos.get(local, 0) + PUNTOS_VICTORIA
            elif goles_l < goles_v:
                puntos[visitante] = puntos.get(visitante, 0) + PUNTOS_VICTORIA
            else:
                puntos[local] = puntos.get(local, 0) + PUNTOS_EMPATE
                puntos[visitante] = puntos.get(visitante, 0) + PUNTOS_EMPATE

        campeon = max(
            equipos,
            key=lambda s: (puntos[s], gf[s] - gc[s], gf[s], aleatorio()),
        )
        titulos[campeon] += 1
        for s in equipos:
            puntos_totales[s] += puntos[s]

    return {
        "titulos": titulos,
        "n_sims": n_sims,
        "puntos_medios": {s: puntos_totales[s] / n_sims for s in equipos},
    }


def probabilidades_titulo(
    tabla: list[dict],
    pendientes: list[dict],
    elo_table: dict[str, float],
    top: int = TOP_RANKING,
    n_sims: int = N_SIMULACIONES,
    constantes: dict | None = None,
    semilla: int | str | None = None,
) -> list[dict]:
    """
    The countdown's entries: [{"slug", "probTitulo", "puntos_medios"}, ...],
    best first, trimmed to `top`.
    """
    salida = simular(tabla, pendientes, elo_table, n_sims, constantes, semilla)
    n = salida["n_sims"]

    clasificado = sorted(
        (
            {
                "slug": slug,
                "probTitulo": round(veces / n, 4),
                "puntos_medios": round(salida["puntos_medios"][slug], 1),
            }
            for slug, veces in salida["titulos"].items()
        ),
        # Average points breaks ties, and there are a lot of them: in a league
        # with two dominant clubs everyone from third or fourth down rounds to
        # 0.0%, and sorting on probability alone leaves those in dictionary
        # order — which put Alavés (44 average points) above Athletic (50).
        key=lambda e: (e["probTitulo"], e["puntos_medios"]),
        reverse=True,
    )
    return clasificado[:top]


def _pendientes_de(partidos: list[dict], desde: date | None = None) -> list[dict]:
    """Fixtures from `desde` onward — everything still to be played."""
    corte = (desde or date.today()).isoformat()
    return [p for p in partidos if (p.get("fecha") or "") >= corte]


if __name__ == "__main__":
    import champions_elo
    import champions_teams
    import espn
    import laliga

    tabla = laliga.clasificacion()
    calendario = espn.partidos(
        espn.LIGAS["LaLiga"], date.today(), date(2027, 6, 30),
        avisar_sin_resolver=False,
    )
    pendientes = _pendientes_de(calendario)
    elo = champions_elo.get_elo_table()

    print(f"Equipos: {len(tabla)} | partidos por jugar: {len(pendientes)} | "
          f"simulaciones: {N_SIMULACIONES}")

    import time
    t = time.perf_counter()
    ranking = probabilidades_titulo(tabla, pendientes, elo, top=10, semilla="demo")
    print(f"Calculado en {time.perf_counter() - t:.1f}s\n")

    for i, e in enumerate(ranking, 1):
        nombre = champions_teams.resolve_team(e["slug"])["nombre"]
        print(f"  {i:2}. {nombre:14} {e['probTitulo']:6.1%}   "
              f"({e['puntos_medios']:.0f} pts de media)")
