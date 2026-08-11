"""
champions_titulares.py
Turns verified facts into the short editorial line on each match.

The division of labour is the whole point: champions_facts.py decides WHAT is
true, this module decides how to SAY it. Claude never sees the fixture on its
own — only a fact that has already been computed from the model output, the
Elo table, or ClubElo's Elo history — and is told in the prompt that the fact
is the only thing it may assert. Anything it adds beyond that is caught by
`_valida` below rather than trusted.

Cost: one `claude -p` call per matchday, not per match — all four headlines
come back in a single response. On a Claude subscription that is quota rather
than money; the pipeline never needs an API key. Roughly 700 input tokens and
150 output for a four-match matchday. If `claude` is not on PATH, or the call
fails, or the output doesn't validate, the templates in `_plantilla` take over
and the render still happens.

Public API:
    titulares(partidos, hechos=None) -> list[str]
    MAX_TITULAR
"""
import json
import re
import shutil
import subprocess

import champions_facts

# The renderer drops the headline from 96px to 84 above 30 characters and to
# 72 above 44 (see tamanoTitular in MatchProbability.tsx). Past ~48 it wraps to
# a third line and leaves the safe area, so this is a hard ceiling, not taste.
MAX_TITULAR = 48

# `claude -p` on a cold start can take a while; a matchday render is not
# latency-sensitive, but it must not hang a CI job either.
TIMEOUT_S = 180

_PROMPT = """Eres el redactor de un canal de Shorts de predicciones de fútbol.

Te doy una lista de partidos. Cada uno trae UN HECHO ya verificado.

Escribe para cada partido un titular corto en castellano.

REGLAS, en orden de importancia:

1. NO PUEDES AFIRMAR NADA QUE NO ESTÉ EN EL HECHO. Nada de rachas, lesiones,
   historial, resultados anteriores, cuántos goles marcó nadie, ni contexto de
   ningún tipo que no venga escrito en el hecho. Si no está en el hecho, no
   existe. Esta regla no admite excepciones: el canal publica predicciones y
   una estadística inventada le cuesta la credibilidad.
2. Máximo {max_chars} caracteres. Cuéntalos.
3. Que suene a titular, no a informe: directo, con gancho, sin signos de
   exclamación y sin emoji.
4. No repitas el nombre de los dos equipos — el vídeo ya los muestra en
   pantalla justo debajo. Puedes nombrar a uno si el hecho va de él.
5. No uses cifras que no aparezcan en el hecho. Si el hecho dice 34%, puedes
   decir 34%. Si no dice ningún número, no inventes ninguno.

Devuelve SOLO un array JSON de cadenas, uno por partido y en el mismo orden.
Sin markdown, sin explicación, sin ```json. Solo el array.

PARTIDOS:
"""


def _plantilla(partido: dict, hecho: dict) -> str:
    """
    Deterministic headline, used when Claude isn't available or misbehaves.

    Deliberately plain: this is the floor the channel never drops below, so it
    is built to be always-true and always-short rather than to sound good.
    """
    local = partido["local"]["nombre"]
    visitante = partido["visitante"]["nombre"]
    tipo = hecho.get("tipo")

    if tipo == "equilibrio":
        texto = "El partido más igualado de la jornada"
    elif tipo == "favorito":
        gana = local if partido.get("probLocal", 0) >= partido.get("probVisitante", 0) else visitante
        texto = f"{gana} parte como favorito claro"
    elif tipo == "tendencia":
        texto = hecho["texto"].split(";")[0].split(" en los últimos")[0]
    elif tipo == "hueco_elo":
        texto = hecho["texto"].split(" (")[0]
    elif tipo == "marcador":
        texto = f"Nuestra apuesta: {partido.get('prediccion', '')}".strip()
    else:
        texto = f"{local} contra {visitante}"

    return texto[:MAX_TITULAR].rstrip(" ,;:")


def _cifras(texto: str) -> set[str]:
    """Digit runs in a string, for the invented-number check."""
    return set(re.findall(r"\d+", texto))


def _valida(titular: str, hecho: dict) -> str | None:
    """
    Accept the headline, or say why not.

    The length check is mechanical. The number check is the one that matters:
    a headline containing a figure absent from the fact is the exact failure
    this whole design exists to prevent — "no marcó en 4 de sus 5 últimas
    visitas" is a fabricated statistic, and it looks identical to a real one.
    """
    limpio = titular.strip().strip('"')
    if not limpio:
        return None
    if len(limpio) > MAX_TITULAR:
        print(f"[WARN] Titular descartado por largo ({len(limpio)}): {limpio!r}")
        return None

    inventadas = _cifras(limpio) - _cifras(hecho.get("texto", ""))
    if inventadas:
        print(f"[WARN] Titular descartado, cifras que no están en el hecho "
              f"({', '.join(sorted(inventadas))}): {limpio!r}")
        return None

    return limpio


def _pedir_a_claude(payload: list[dict]) -> list[str] | None:
    """One `claude -p` call for the whole matchday. None on any failure."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        print("[WARN] Claude Code CLI ('claude') no está en el PATH. "
              "Titulares por plantilla.")
        return None

    prompt = _PROMPT.format(max_chars=MAX_TITULAR)
    entrada = prompt + json.dumps(payload, ensure_ascii=False, indent=2)

    try:
        # Prompt and data go through stdin: on Windows `claude` resolves to an
        # npm .cmd shim and multi-line arguments break cmd.exe quoting.
        resultado = subprocess.run(
            [claude_bin, "-p"],
            input=entrada,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        print(f"[WARN] Claude no respondió en {TIMEOUT_S}s. Titulares por plantilla.")
        return None
    except Exception as exc:
        print(f"[WARN] Falló la llamada a Claude ({exc}). Titulares por plantilla.")
        return None

    if resultado.returncode != 0:
        err = (resultado.stderr or "").strip().splitlines()
        print(f"[WARN] Claude salió con código {resultado.returncode}"
              f"{': ' + err[-1] if err else ''}. Titulares por plantilla.")
        return None

    salida = (resultado.stdout or "").strip()
    # Tolerate a fenced block even though the prompt asks for bare JSON.
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", salida, re.S)
    if fence:
        salida = fence.group(1).strip()

    try:
        lineas = json.loads(salida)
    except ValueError:
        print(f"[WARN] Claude no devolvió JSON válido. Titulares por plantilla.")
        return None

    if not isinstance(lineas, list) or not all(isinstance(x, str) for x in lineas):
        print("[WARN] Claude devolvió algo que no es una lista de cadenas. "
              "Titulares por plantilla.")
        return None

    if len(lineas) != len(payload):
        print(f"[WARN] Claude devolvió {len(lineas)} titulares para "
              f"{len(payload)} partidos. Titulares por plantilla.")
        return None

    return lineas


def titulares(partidos: list[dict], hechos: list[dict] | None = None) -> list[str]:
    """
    A headline per match, in order.

    Falls back to a template per match — never raises and never returns fewer
    headlines than matches, because a matchday that renders with a plain
    headline beats a matchday that doesn't render.
    """
    if not partidos:
        return []

    if hechos is None:
        hechos = champions_facts.mejor_hecho_por_partido(partidos)

    payload = [
        {
            "local": p["local"]["nombre"],
            "visitante": p["visitante"]["nombre"],
            "hecho": h.get("texto", ""),
        }
        for p, h in zip(partidos, hechos)
    ]

    crudos = _pedir_a_claude(payload)
    salida: list[str] = []
    for i, (partido, hecho) in enumerate(zip(partidos, hechos)):
        candidato = _valida(crudos[i], hecho) if crudos else None
        salida.append(candidato or _plantilla(partido, hecho))

    return salida


def rellenar_jornada(jornada: dict, sobrescribir: bool = False) -> dict:
    """
    Fill in the `titular` of every match in a matchday, in place.

    By default a match that already carries a headline is left alone, so a
    line written by hand survives a re-run. Pass sobrescribir=True to replace
    everything.
    """
    partidos = jornada.get("partidos") or []
    pendientes = [
        p for p in partidos if sobrescribir or not (p.get("titular") or "").strip()
    ]
    if not pendientes:
        print("[INFO] Todos los partidos ya tienen titular.")
        return jornada

    for partido, titular in zip(pendientes, titulares(pendientes)):
        partido["titular"] = titular

    return jornada


if __name__ == "__main__":
    import argparse

    cli = argparse.ArgumentParser(
        description="Escribe los titulares de una jornada a partir de hechos "
                    "verificados."
    )
    cli.add_argument("jornada", nargs="?",
                     default="remotion/sample-data/jornada.json")
    cli.add_argument("-o", "--salida",
                     help="Dónde escribir el JSON. Sin esto solo se muestra.")
    cli.add_argument("--sobrescribir", action="store_true",
                     help="Reemplazar también los titulares ya escritos.")
    args = cli.parse_args()

    with open(args.jornada, encoding="utf-8") as fh:
        jornada = json.load(fh)

    partidos = jornada["partidos"]
    hechos = champions_facts.mejor_hecho_por_partido(partidos)
    lineas = titulares(partidos, hechos)

    for partido, hecho, titular in zip(partidos, hechos, lineas):
        print(f"{partido['local']['nombre']} - {partido['visitante']['nombre']}")
        print(f"  hecho   [{hecho['tipo']}] {hecho['texto']}")
        print(f"  titular ({len(titular)}) {titular!r}\n")

    if args.salida:
        for partido, titular in zip(partidos, lineas):
            partido["titular"] = titular
        with open(args.salida, "w", encoding="utf-8") as fh:
            json.dump(jornada, fh, ensure_ascii=False, indent=2)
        print(f"[INFO] Escrito en {args.salida}")
