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
import laliga_seleccion
import resultados

COMPETICION = "LaLiga"


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


def construir_jornada(
    aciertos: dict | None = None,
    maximo: int | None = None,
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

    jornada = {
        "competicion": COMPETICION,
        "fecha": fecha,
        "aciertosJornadaAnterior": aciertos,
        "partidos": partidos,
        # Vacío a propósito: el ranking de probabilidad de título necesita una
        # simulación de liga que no existe. El Short cierra con el CTA.
        "ranking": [],
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
    args = cli.parse_args()

    construido = construir_jornada(args.aciertos, args.maximo)
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

    if args.salida:
        with open(args.salida, "w", encoding="utf-8") as fh:
            json.dump(jornada, fh, ensure_ascii=False, indent=2)
        print(f"\n[INFO] Escrito en {args.salida}")
        print("[INFO] Recuerda añadir \"opciones\": {\"cierre\": \"cta\"} al "
              "renderizar: sin ranking, el cierre por defecto se queda vacío.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
