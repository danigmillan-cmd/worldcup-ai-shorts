#!/usr/bin/env python3
"""
generar_jornada_laliga.py
Builds the matchday JSON for a Spanish-league Short, end to end.

    python generar_jornada_laliga.py --aciertos 3/4 -o remotion/jornada-laliga.json

Pulls fixtures and the table from ESPN (laliga.py), filters them to the clubs
worth publishing (laliga_seleccion.py), rates them with ClubElo and the Poisson
engine under LALIGA_CONSTANTS, and writes the headlines from verified facts
(champions_titulares.py).

Why --aciertos has no default
-----------------------------
The Short's second block is social proof: "acertamos N de M la jornada
pasada". Nothing in this repo tracks results yet, so that number cannot be
computed — and inventing it would put a false claim on screen, which is
precisely what champions_facts.py exists to prevent. So it is a required
argument until result tracking exists. Pass what you actually scored.

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
import laliga
import laliga_seleccion

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


def construir_jornada(aciertos: dict, maximo: int | None = None) -> dict | None:
    """The full matchday dict, or None when there's nothing worth publishing."""
    partidos_crudos = laliga_seleccion.seleccion_para_short(
        maximo=maximo or laliga_seleccion.MAX_PARTIDOS
    )
    if not partidos_crudos:
        print("[ERROR] No hay partidos publicables. ¿ESPN caído, o parón de "
              "selecciones?")
        return None

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

    return {
        "competicion": COMPETICION,
        "fecha": partidos_crudos[0]["fecha"] or date.today().isoformat(),
        "aciertosJornadaAnterior": aciertos,
        "partidos": partidos,
        # Vacío a propósito: el ranking de probabilidad de título necesita una
        # simulación de liga que no existe. El Short cierra con el CTA.
        "ranking": [],
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    cli.add_argument("--aciertos", required=True, type=_parse_aciertos,
                     help="Aciertos reales de la jornada anterior, como N/M. "
                          "Sin valor por defecto a propósito: nada mide esto "
                          "todavía y no se inventa.")
    cli.add_argument("-o", "--salida",
                     help="Fichero de salida. Sin esto solo se muestra.")
    cli.add_argument("--maximo", type=int, default=None,
                     help=f"Partidos en el Short (por defecto "
                          f"{laliga_seleccion.MAX_PARTIDOS}).")
    args = cli.parse_args()

    jornada = construir_jornada(args.aciertos, args.maximo)
    if jornada is None:
        return 1

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
