"""
resultados.py
Keeps score of what the channel predicted, so "acertamos N de M" is a fact.

The Short's second block is social proof. Until now that number had to be typed
in by hand, because nothing recorded what had been published or checked how it
turned out — and a made-up accuracy figure is exactly the kind of claim
champions_facts.py exists to keep off the screen.

Two halves:
  - `registrar` writes down every prediction at publication time
  - `aciertos` reads the last publication back, fetches the real results from
    ESPN, and counts

What counts as a hit
--------------------
The 1X2 — home / draw / away — because that is what the Short actually
asserts: `resultadoPredicho` is the bar the video highlights. The exact
scoreline is shown too, but as a most-likely result rather than a claim, and
scoring on it would produce a number near zero that misrepresents the model in
the other direction. Both counts are computed and the exact-score one is
reported alongside, so the headline figure is auditable rather than asserted.

Public API:
    registrar(jornada, competicion) -> None
    aciertos(competicion) -> dict | None
    detalle(competicion) -> dict | None
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import espn

REGISTRO = Path(__file__).parent / "data" / "predicciones_publicadas.json"

# Slack around a publication's own dates when looking for results. A postponed
# match reappears days or weeks later, and scoring it once it's played is more
# honest than quietly dropping it from the total.
DIAS_MARGEN = 10


def _leer() -> dict:
    try:
        return json.loads(REGISTRO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"publicaciones": []}


def _escribir(datos: dict) -> None:
    try:
        REGISTRO.parent.mkdir(parents=True, exist_ok=True)
        REGISTRO.write_text(
            json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"[WARN] No se pudo escribir el registro de predicciones: {exc}")


def _slug_de(equipo: dict) -> str:
    """The catalogue slug behind a rendered team block, best effort."""
    import champions_teams

    return champions_teams._lookup_index().get(
        champions_teams._normalize(equipo["nombre"])
    ) or equipo["nombre"]


def registrar(
    jornada: dict,
    competicion: str | None = None,
    parejas: list[tuple[str, str]] | None = None,
) -> None:
    """
    Write down what this matchday predicted, before it is published.

    `parejas` are the (local, visitante) slugs, in the same order as the
    matches. Pass them whenever the caller has them — the fallback re-derives
    each slug from the rendered name, which loses on any club the catalogue
    doesn't know (`resolve_team` truncates an invented name to 14 characters,
    and that will not resolve back). A prediction whose slugs don't round-trip
    is never scorable, so it silently sits as "not played" forever.

    Idempotent per (competition, date): re-running the generator for the same
    matchday replaces its entry instead of appending a second one, so a
    regenerated Short doesn't get counted twice.
    """
    competicion = competicion or jornada.get("competicion") or "?"
    partidos = jornada.get("partidos", [])
    if parejas is None:
        parejas = [(_slug_de(p["local"]), _slug_de(p["visitante"])) for p in partidos]

    entrada = {
        "competicion": competicion,
        "fecha": jornada.get("fecha"),
        "publicado_en": datetime.now(timezone.utc).isoformat(),
        "partidos": [
            {
                "local": local,
                "visitante": visitante,
                "resultadoPredicho": p.get("resultadoPredicho"),
                "prediccion": p.get("prediccion"),
            }
            for p, (local, visitante) in zip(partidos, parejas)
        ],
    }

    datos = _leer()
    datos["publicaciones"] = [
        p for p in datos.get("publicaciones", [])
        if not (p.get("competicion") == competicion and p.get("fecha") == entrada["fecha"])
    ]
    datos["publicaciones"].append(entrada)
    datos["publicaciones"].sort(key=lambda p: (p.get("fecha") or "", p.get("competicion") or ""))
    _escribir(datos)
    print(f"[INFO] Registradas {len(entrada['partidos'])} predicciones de "
          f"{competicion} ({entrada['fecha']})")


def _ultima_publicacion(competicion: str, antes_de: str | None = None) -> dict | None:
    """The most recent recorded publication for a competition."""
    publicaciones = [
        p for p in _leer().get("publicaciones", [])
        if p.get("competicion") == competicion
        and (antes_de is None or (p.get("fecha") or "") < antes_de)
    ]
    return publicaciones[-1] if publicaciones else None


def _resultado_1x2(goles_local: int, goles_visitante: int) -> str:
    if goles_local > goles_visitante:
        return "local"
    if goles_local < goles_visitante:
        return "visitante"
    return "empate"


def detalle(competicion: str, antes_de: str | None = None) -> dict | None:
    """
    Score the last published matchday, or None if there's nothing to score.

    `antes_de` restricts to publications older than a date — pass the matchday
    being generated so it scores the PREVIOUS one rather than itself.

    Returns None when nothing was ever published, when ESPN is unreachable, or
    when not a single match has been played yet. Callers must handle that: the
    honest answer at that point is "we don't know", not a zero.
    """
    publicacion = _ultima_publicacion(competicion, antes_de)
    if not publicacion or not publicacion.get("partidos"):
        print(f"[INFO] No hay ninguna publicación previa de {competicion} que puntuar")
        return None

    liga = espn.LIGAS.get(competicion)
    if not liga:
        print(f"[WARN] Sin código de liga de ESPN para «{competicion}»")
        return None

    try:
        centro = date.fromisoformat(publicacion["fecha"])
    except (KeyError, TypeError, ValueError):
        print(f"[WARN] La publicación de {competicion} no tiene fecha usable")
        return None

    jugados = espn.partidos(
        liga,
        centro - timedelta(days=DIAS_MARGEN),
        centro + timedelta(days=DIAS_MARGEN),
        solo_terminados=True,
        avisar_sin_resolver=False,
    )
    por_pareja = {(p["local"], p["visitante"]): p for p in jugados}

    aciertos_1x2 = 0
    aciertos_exactos = 0
    resueltos = 0
    pendientes: list[str] = []

    for prediccion in publicacion["partidos"]:
        real = por_pareja.get((prediccion["local"], prediccion["visitante"]))
        if real is None:
            pendientes.append(f"{prediccion['local']}-{prediccion['visitante']}")
            continue

        resueltos += 1
        real_1x2 = _resultado_1x2(real["goles_local"], real["goles_visitante"])
        if real_1x2 == prediccion.get("resultadoPredicho"):
            aciertos_1x2 += 1
        marcador_real = f"{real['goles_local']}-{real['goles_visitante']}"
        if marcador_real == prediccion.get("prediccion"):
            aciertos_exactos += 1

    if resueltos == 0:
        print(f"[INFO] Ninguno de los {len(publicacion['partidos'])} partidos de "
              f"{competicion} ({publicacion['fecha']}) se ha jugado todavía")
        return None

    if pendientes:
        print(f"[INFO] {len(pendientes)} partido(s) sin jugar, fuera del total: "
              f"{', '.join(pendientes)}")

    return {
        "competicion": competicion,
        "fecha": publicacion["fecha"],
        "acertados": aciertos_1x2,
        "total": resueltos,
        "aciertos_marcador_exacto": aciertos_exactos,
        "sin_jugar": len(pendientes),
    }


def aciertos(competicion: str, antes_de: str | None = None) -> dict | None:
    """{"acertados", "total"} for the Short, or None when it can't be known."""
    completo = detalle(competicion, antes_de)
    if completo is None:
        return None
    return {"acertados": completo["acertados"], "total": completo["total"]}


def hay_publicacion_previa(competicion: str, antes_de: str | None = None) -> bool:
    """
    Whether anything was ever published for this competition.

    Exists to separate the two ways `aciertos` returns None, which mean
    opposite things to a caller. Nothing published ever is the channel's first
    Short: there is no claim to make and the Short should simply not make one.
    Something published but not yet played is a Short that is being built too
    early, and dropping the block there would quietly cost the social proof on
    an ordinary week — that one has to wait instead.
    """
    return _ultima_publicacion(competicion, antes_de) is not None


if __name__ == "__main__":
    import argparse

    cli = argparse.ArgumentParser(
        description="Puntúa la última jornada publicada de una competición."
    )
    cli.add_argument("competicion", nargs="?", default="LaLiga",
                     choices=sorted(espn.LIGAS))
    args = cli.parse_args()

    completo = detalle(args.competicion)
    if completo is None:
        raise SystemExit(1)

    print(f"\n{completo['competicion']} — jornada del {completo['fecha']}")
    print(f"  Aciertos 1X2:      {completo['acertados']}/{completo['total']}")
    print(f"  Marcador exacto:   {completo['aciertos_marcador_exacto']}/{completo['total']}")
    if completo["sin_jugar"]:
        print(f"  Sin jugar todavía: {completo['sin_jugar']}")
