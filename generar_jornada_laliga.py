#!/usr/bin/env python3
"""
generar_jornada_laliga.py
Builds the matchday JSON for a Spanish-league Short, end to end.

    python generar_jornada_laliga.py -o remotion/jornada-laliga.json

Pulls fixtures and the table from ESPN (laliga.py), filters them to the clubs
worth publishing (laliga_seleccion.py), rates them with ClubElo and the Poisson
engine under LALIGA_CONSTANTS, writes the headlines from verified facts
(champions_titulares.py), and scores the previous matchday against real
results (resultados.py).

Every prediction is recorded on the way out, which is what makes the next
run's "acertamos N de M" a measurement instead of a guess. When the previous
matchday hasn't been played yet there is no honest number to show, so the
generator stops and says so rather than filling one in; --aciertos N/M
overrides it when you know better.

The title-probability ranking is left empty and the Short closes on the CTA
instead: a league title race needs a season simulation that hasn't been
written, and an empty countdown is better than a made-up one.
"""
import argparse
import json
import sys
from datetime import date

import champions_predictions
import champions_teams
import champions_titulares
import espn
import laliga
import laliga_seleccion
import liga_simulator
import resultados

COMPETICION = "LaLiga"

# Far enough out to cover the whole calendar; ESPN returns the full 380-match
# season and anything past the last match is simply empty.
FIN_DE_TEMPORADA = date(2027, 6, 30)


def _parse_aciertos(texto: str) -> dict:
    """"3/4" -> {"acertados": 3, "total": 4}, with the schema's own limits."""
    try:
        acertados, total = (int(x) for x in texto.split("/", 1))
    except (ValueError, AttributeError):
        raise argparse.ArgumentTypeError(
            f"«{texto}» no tiene la forma N/M, por ejemplo 3/4"
        )
    if total < 1 or acertados < 0 or acertados > total:
        raise argparse.ArgumentTypeError(
            f"«{texto}» no es un marcador posible (0 <= N <= M, M >= 1)"
        )
    return {"acertados": acertados, "total": total}


# The two questions the countdown can ask, and the label each puts on screen.
# Same simulation either way — only the cut-off through the final table differs.
#
# `champions` is the default because the title race in LaLiga is close to a
# foregone conclusion: it leaves three of the five slots at ~0% for most of a
# season, while the fourth place is genuinely contested.
#
# An expected final table was considered instead and rejected. It comes out in
# the SAME order — it ranks by strength, so it does not fix the obviousness —
# and it is quietly less honest: "4. Villarreal, 63 pts" reads as a prediction,
# but Villarreal finishes fourth in only 28% of simulated seasons, and the
# table as a whole essentially never happens. A probability says what it knows;
# an average hides it.
PREGUNTAS = {
    "titulo": (1, "Quién gana LaLiga"),
    "champions": (liga_simulator.PLAZAS_CHAMPIONS, "Quién juega la Champions"),
}


def _ranking(elo_table: dict[str, float], semilla: str, pregunta: str) -> tuple[list[dict], str]:
    """
    The closing countdown: (entries, on-screen title), from a real simulation.

    Seeded on the matchday date so re-rendering the same Short twice shows the
    same percentages — a countdown that shifts by a tenth between renders looks
    broken even though both figures are valid samples.

    Returns ([], "") if the season calendar or the table can't be read; the
    caller then closes on the CTA, which beats a countdown of zeroes.
    """
    tabla = laliga.clasificacion()
    calendario = espn.partidos(
        espn.LIGAS[COMPETICION], date.today(), FIN_DE_TEMPORADA,
        avisar_sin_resolver=False,
    )
    pendientes = liga_simulator._pendientes_de(calendario)

    if not tabla or not pendientes:
        print("[WARN] Sin clasificación o sin calendario — el Short cerrará con CTA")
        return [], ""

    corte, etiqueta = PREGUNTAS[pregunta]
    print(f"[INFO] Simulando {len(pendientes)} partidos que quedan "
          f"({liga_simulator.N_SIMULACIONES} temporadas)...")
    ranking = liga_simulator.probabilidades_puesto(
        tabla, pendientes, elo_table,
        corte=corte,
        constantes=champions_predictions.LALIGA_CONSTANTS,
        semilla=semilla,
    )

    entradas = [
        {
            "equipo": champions_teams.resolve_team(e["slug"])["nombre"],
            "colorPrimario": champions_teams.resolve_team(e["slug"])["colorPrimario"],
            "probTitulo": e["prob"],
        }
        for e in ranking
    ]
    return entradas, etiqueta


def construir_jornada(
    aciertos: dict | None = None,
    maximo: int | None = None,
    sin_ranking: bool = False,
    pregunta: str = "champions",
) -> tuple[dict, list[tuple[str, str]]] | None:
    """
    (matchday dict, club-slug pairs), or None when there's nothing to publish.

    The pairs come back alongside because resultados.registrar needs the slugs
    and the matchday itself only carries rendered names, which don't always
    resolve back.

    `aciertos` overrides the computed figure. Left out, the previous published
    matchday is scored against real results (resultados.py); if that can't be
    known yet, this returns None rather than inventing a number.
    """
    partidos_crudos = laliga_seleccion.seleccion_para_short(
        maximo=maximo or laliga_seleccion.MAX_PARTIDOS
    )
    if not partidos_crudos:
        print("[ERROR] No hay partidos publicables. ¿ESPN caído, o parón de "
              "selecciones?")
        return None

    fecha = partidos_crudos[0]["fecha"] or date.today().isoformat()

    if aciertos is None:
        aciertos = resultados.aciertos(COMPETICION, antes_de=fecha)
        if aciertos is None:
            print("[ERROR] No se pueden calcular los aciertos de la jornada "
                  "anterior todavía, y no se inventan. Pasa --aciertos N/M a "
                  "mano, o espera a que se jueguen los partidos publicados.")
            return None
        print(f"[INFO] Aciertos calculados de la jornada anterior: "
              f"{aciertos['acertados']}/{aciertos['total']}")

    elo_table = __import__("champions_elo").get_elo_table()

    partidos = []
    for crudo in partidos_crudos:
        local = champions_teams.resolve_team(crudo["local"])["nombre"]
        visitante = champions_teams.resolve_team(crudo["visitante"])["nombre"]
        partidos.append(
            champions_teams.build_match_from_elo(
                local,
                visitante,
                titular="",  # lo escribe champions_titulares más abajo
                fecha=crudo["fecha"],
                elo_table=elo_table,
                constantes=champions_predictions.LALIGA_CONSTANTS,
            )
        )

    for partido, titular in zip(partidos, champions_titulares.titulares(partidos)):
        partido["titular"] = titular

    ranking, etiqueta = ([], "") if sin_ranking else _ranking(elo_table, fecha, pregunta)

    jornada = {
        "competicion": COMPETICION,
        "fecha": fecha,
        "aciertosJornadaAnterior": aciertos,
        "partidos": partidos,
        "ranking": ranking,
        # Emitido aquí y no dejado al render: el cierre por defecto es el
        # countdown y su título por defecto dice "Quién gana la Champions",
        # que en un Short de LaLiga sobre el título sería sencillamente falso.
        "opciones": (
            {"cierre": "ranking", "tituloRanking": etiqueta}
            if ranking else {"cierre": "cta"}
        ),
    }
    parejas = [(c["local"], c["visitante"]) for c in partidos_crudos]
    return jornada, parejas


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("--aciertos", type=_parse_aciertos, default=None,
                     help="Fuerza los aciertos de la jornada anterior, como "
                          "N/M. Normalmente no hace falta: se calculan solos "
                          "contra los resultados reales.")
    cli.add_argument("-o", "--salida",
                     help="Fichero de salida. Sin esto solo se muestra.")
    cli.add_argument("--maximo", type=int, default=None,
                     help=f"Partidos en el Short (por defecto "
                          f"{laliga_seleccion.MAX_PARTIDOS}).")
    cli.add_argument("--no-registrar", action="store_true",
                     help="No apuntar estas predicciones en el registro. Para "
                          "pruebas: sin registro no se podrán puntuar luego.")
    cli.add_argument("--sin-ranking", action="store_true",
                     help="Saltarse la simulación de liga y cerrar con CTA. "
                          "Tarda unos segundos menos.")
    cli.add_argument("--pregunta", choices=sorted(PREGUNTAS), default="champions",
                     help="Qué pregunta el countdown: quién entra en plazas de "
                          "Champions («champions», por defecto) o quién gana la "
                          "liga («titulo»). Misma simulación, distinto corte.")
    args = cli.parse_args()

    construido = construir_jornada(
        args.aciertos, args.maximo, args.sin_ranking, args.pregunta
    )
    if construido is None:
        return 1
    jornada, parejas = construido

    if not args.no_registrar:
        resultados.registrar(jornada, COMPETICION, parejas)

    print(f"\n{jornada['competicion']} — {jornada['fecha']}")
    print(f"Aciertos de la jornada anterior: "
          f"{jornada['aciertosJornadaAnterior']['acertados']}"
          f"/{jornada['aciertosJornadaAnterior']['total']}\n")
    for p in jornada["partidos"]:
        print(f"  {p['local']['nombre']} - {p['visitante']['nombre']}")
        print(f"    {p['probLocal']:.0%} / {p['probEmpate']:.0%} / "
              f"{p['probVisitante']:.0%}   →  {p['prediccion']}")
        print(f"    «{p['titular']}»")

    if jornada["ranking"]:
        print(f"\n  {jornada['opciones']['tituloRanking']}:")
        for e in jornada["ranking"]:
            print(f"    {e['equipo']:14} {e['probTitulo']:6.1%}")

    if args.salida:
        with open(args.salida, "w", encoding="utf-8") as fh:
            json.dump(jornada, fh, ensure_ascii=False, indent=2)
        print(f"\n[INFO] Escrito en {args.salida}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
