#!/usr/bin/env python3
"""
ciclo_jornada.py
Decides whether now is the moment to build and publish the next matchday Short.

    python ciclo_jornada.py -o remotion/jornada-laliga.json

Meant to be run on a cron every few hours and to do nothing almost every time.
The channel publishes one Short per matchday; a cron fires far more often than
that, so the entire job of this module is to answer "not yet" cheaply and
"go, and here is the JSON" once per matchday.

Why there is no notion of "matchday N"
--------------------------------------
There deliberately isn't one. laliga_seleccion.seleccion_para_short() already
answers "which matches", and it answers it as "the next fixtures worth showing"
— widening its window past a round boundary when six selected clubs out of
twenty don't produce enough fixtures in one round. Round 1 of 2026-27 is the
case that settled it: none of Real Madrid, Barcelona, Valencia or Betis play in
it. So the question this module answers is not *which* matchday but *when*, and
the answer comes from the fixtures themselves rather than from a counter.

The gates, cheapest first
-------------------------
1. Are there fixtures, and do we know when they kick off? No kick-off times
   means no publication moment, which means nothing to schedule against.
2. Is it time? Too early is a no-op that retries. Too late is the only hard
   no — see below.
3. Has this slot already been published? The ledger is written by
   publicar_jornada.py after a successful upload, so a render that failed
   halfway is retried rather than skipped.
4. Is any of these matches already on the channel? The slot key catches the
   same Short twice; this catches two different Shorts sharing a fixture,
   which the selector will happily produce because it reaches days ahead.

When a Short goes out
---------------------
24 h before the first match it previews, as near to that as the machinery
allows, and late rather than never.

Nothing has to try hard for the first two thirds: the matchday JSON carries the
exact moment and YouTube honours it through publishAt, so the build can happen
any time in the window and the Short still surfaces on the hour.

The third is the part worth being explicit about, because the intuitive
behaviour is wrong. Being past the publication moment is NOT a reason to skip.
The gate lets a negative countdown through, publicar_jornada sees a moment
already behind it and uploads on arrival instead of scheduling, and a Short
that should have gone out at 19:30 goes out at 03:00 instead. Only
config.JORNADA_MARGEN_MINIMO_HORAS stops it, and only because below that the
pipeline cannot finish before kick-off and nobody would see it if it did.

Only past all of them does it run the expensive part — the full build, which
costs a ClubElo fetch, a call to Claude for the headlines, and ~6 s of league
simulation. That ordering is the point of the module: a cron tick that isn't
going to publish costs one ESPN request.

Public API:
    decidir(competicion=COMPETICION, ...) -> Decision
"""
import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
import generar_jornada_laliga
import laliga_seleccion
import processed_matches
import resultados

COMPETICION = generar_jornada_laliga.COMPETICION

# How far back to look for an already-published fixture. Two clubs meet twice a
# season, so the pair only identifies a match within a few weeks of itself —
# past that, Betis-Valencia is a different game and blocking it would be wrong.
# Thirty days covers any gap the selector can open up while staying well under
# the half-season between the two legs.
DIAS_SIN_REPETIR = 30


@dataclass
class Decision:
    """What the cycle concluded, and why — the `motivo` is for the run log."""
    publicar: bool
    motivo: str
    jornada: dict | None = None
    parejas: list | None = None
    clave: str | None = None


def clave_de_slot(competicion: str, publicacion: dict) -> str:
    """
    The ledger key for a Short: competition plus the DATE it goes out.

    Keyed on the publication date rather than on the fixtures because the
    fixture set is not stable between two runs a few hours apart — the ordering
    in laliga_seleccion mixes in Elo, which moves daily, so a set could reorder
    or swap its fourth match and produce a different key for the same Short.
    The publication date is derived from the earliest kick-off of the round and
    doesn't move.

    Local date, not UTC: a Short scheduled for 21:00 Madrid is a Tuesday Short
    to everyone involved, and the UTC date would call it Wednesday half the
    year.
    """
    return f"{competicion}_{publicacion['publicar_en_local'][:10]}"


def _hace(dias: int) -> str:
    """An ISO date `dias` days ago, for bounding a lookback."""
    return (datetime.now(timezone.utc).date() - timedelta(days=dias)).isoformat()


def _horas_hasta(momento_iso: str) -> float | None:
    try:
        momento = datetime.fromisoformat(momento_iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return (momento - datetime.now(timezone.utc)).total_seconds() / 3600


def decidir(
    competicion: str = COMPETICION,
    ventana_horas: float | None = None,
    forzar: bool = False,
    sin_ranking: bool = False,
    aciertos: dict | None = None,
    margen_horas: float | None = None,
) -> Decision:
    """
    Run the three gates and, if they all pass, build the matchday.

    `forzar` skips gates 2 and 3 — the window and the ledger — for a manual run
    that wants a Short now. It does NOT skip gate 1: without fixtures there is
    nothing to build, forced or not.

    `aciertos` forces the previous matchday's hit rate. It is rarely needed:
    with an empty ledger the first Short omits the block rather than blocking,
    and from the second one on the figure is measured. Pass it only to override
    a number you know better than the ledger does.
    """
    ventana = config.JORNADA_VENTANA_HORAS if ventana_horas is None else ventana_horas
    margen = (config.JORNADA_MARGEN_MINIMO_HORAS
              if margen_horas is None else margen_horas)

    # ── Gate 1: are there fixtures, with kick-off times? ─────────────────────
    crudos = laliga_seleccion.seleccion_para_short()
    if not crudos:
        return Decision(False, "No hay partidos publicables (¿parón, o ESPN caído?)")

    publicacion = generar_jornada_laliga.cuando_publicar(crudos)
    if publicacion is None:
        return Decision(
            False,
            "ESPN todavía no da hora de comienzo de algún partido — se reintenta",
        )

    clave = clave_de_slot(competicion, publicacion)

    # ── Gate 2: is it time? ──────────────────────────────────────────────────
    if not forzar:
        faltan = _horas_hasta(publicacion["publicar_en_utc"])
        hasta_saque = _horas_hasta(publicacion["primer_partido_utc"])

        # Too late is the only hard no. Being PAST the publication moment is
        # not: `faltan` simply goes negative, the gate lets it through, and
        # publicar_jornada uploads on arrival instead of scheduling. A Short
        # that should have gone out at 19:30 and can only go out at 03:00 is
        # still worth publishing — it just stops being scheduled.
        if hasta_saque is not None and hasta_saque < margen:
            return Decision(
                False,
                f"El primer partido de {clave} empieza en {hasta_saque:.1f} h, "
                f"por debajo del margen de {margen:.0f} h — ya no da tiempo a "
                "publicarlo como previa",
            )
        if faltan is None:
            return Decision(False, f"Hora de publicación ilegible en {clave}")
        if faltan > ventana:
            return Decision(
                False,
                f"Todavía faltan {faltan:.1f} h para publicar {clave} "
                f"(ventana de {ventana:.0f} h)",
            )
        if faltan < 0:
            print(f"[WARN] La hora de publicación de {clave} pasó hace "
                  f"{-faltan:.1f} h — se publica en cuanto suba, sin programar")

    # ── Gate 3: has this slot already gone out? ──────────────────────────────
    if not forzar and processed_matches.is_processed(
        clave, processed_matches.load(config.JORNADA_SHORTS_FILE)
    ):
        return Decision(False, f"{clave} ya se publicó")

    # ── Gate 3b: is any of these matches already on the channel? ─────────────
    #
    # The slot key alone is not enough. It keys on the publication date, so two
    # Shorts a day apart are two different slots even when they preview the
    # same fixture — and they can, because "the next fixtures worth showing"
    # reaches days ahead. The opening weekend of 2026-27 hit this immediately:
    # a Short published on the 14th and the next slot on the 15th both led with
    # Racing-Villarreal.
    #
    # Blocking the whole Short rather than dropping the repeated match is
    # deliberate. A missed Short is recoverable and nobody sees it; a duplicate
    # preview is on the channel forever.
    if not forzar:
        ya_vistos = resultados.parejas_publicadas(
            competicion, desde=_hace(DIAS_SIN_REPETIR)
        )
        repetidos = [
            f"{c['local']}-{c['visitante']}" for c in crudos
            if (c["local"], c["visitante"]) in ya_vistos
        ]
        if repetidos:
            return Decision(
                False,
                f"Ya se publicó {', '.join(repetidos)} — se espera a que la "
                "selección avance a partidos nuevos",
            )

    # ── Everything past here costs money and minutes ─────────────────────────
    print(f"[INFO] Construyendo {clave}...")
    construido = generar_jornada_laliga.construir_jornada(
        aciertos=aciertos, sin_ranking=sin_ranking
    )
    if construido is None:
        # construir_jornada already explained itself. The usual cause is that
        # the previous matchday hasn't been played yet, which resolves on its
        # own — so this is a no-op, not a failure.
        return Decision(
            False,
            "No se pudo construir la jornada (aciertos de la anterior sin "
            "calcular todavía, probablemente) — se reintenta",
        )

    jornada, parejas = construido
    return Decision(True, f"Toca publicar {clave}", jornada, parejas, clave)


def _emitir_salidas_de_actions(decision: Decision, salida: Path | None) -> None:
    """Hand the verdict to the workflow via $GITHUB_OUTPUT, if we're in one."""
    destino = os.environ.get("GITHUB_OUTPUT")
    if not destino:
        return
    with open(destino, "a", encoding="utf-8") as fh:
        fh.write(f"publicar={'true' if decision.publicar else 'false'}\n")
        fh.write(f"motivo={decision.motivo}\n")
        fh.write(f"clave={decision.clave or ''}\n")
        fh.write(f"jornada={salida or ''}\n")


def main() -> int:
    cli = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cli.add_argument("-o", "--salida", type=Path,
                     help="Dónde escribir el JSON cuando toque publicar.")
    cli.add_argument("--ventana", type=float, default=None,
                     help=f"Horas antes de la publicación en que se construye "
                          f"(por defecto {config.JORNADA_VENTANA_HORAS}).")
    cli.add_argument("--forzar", action="store_true",
                     help="Sáltate la ventana y el registro: construye ya.")
    cli.add_argument("--no-registrar", action="store_true",
                     help="No apuntar las predicciones. Para pruebas.")
    cli.add_argument("--sin-ranking", action="store_true",
                     help="Cierra con CTA en vez de con el countdown.")
    cli.add_argument("--aciertos", type=generar_jornada_laliga._parse_aciertos,
                     default=None,
                     help="Fuerza los aciertos de la jornada anterior, como "
                          "N/M. No suele hacer falta: se miden solos, y el "
                          "primer Short sale sin el bloque.")
    args = cli.parse_args()

    decision = decidir(
        ventana_horas=args.ventana,
        forzar=args.forzar,
        sin_ranking=args.sin_ranking,
        aciertos=args.aciertos,
    )

    print(f"\n  {'PUBLICAR' if decision.publicar else 'NADA QUE HACER'} — "
          f"{decision.motivo}")

    if decision.publicar and args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(
            json.dumps(decision.jornada, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  Escrito en {args.salida}")

        # Recorded here and not after the upload on purpose: this is the
        # predictions ledger that next week's "acertamos N de M" is measured
        # against, and it has to reflect what the Short says regardless of
        # whether YouTube accepted the video.
        if not args.no_registrar:
            resultados.registrar(decision.jornada, COMPETICION, decision.parejas)

    _emitir_salidas_de_actions(decision, args.salida if decision.publicar else None)

    # A "not yet" is a successful run. Only a broken one should go red, or the
    # cron cries wolf every few hours.
    return 0


if __name__ == "__main__":
    sys.exit(main())
