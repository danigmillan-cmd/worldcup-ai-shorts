"""
champions_titulares.py
Turns verified facts into the short editorial line on each match.

The division of labour is the whole point: champions_facts.py decides WHAT is
true, this module decides how to SAY it. Claude never sees the fixture on its
own — only a fact that has already been computed from the model output, the
Elo table, or ClubElo's Elo history — and is told in the prompt that the fact
is the only thing it may assert. Anything it adds beyond that is caught by
`_valida` below rather than trusted.

Who writes them, in order
-------------------------
`REDACTORES` is tried top to bottom until one returns something that
validates, and the templates in `_plantilla` catch everything below that. The
order encodes where each one is actually available rather than a ranking of
quality:

  1. Claude, through the `claude` CLI. On the laptop it is on PATH and signed
     in, so it costs subscription quota rather than money.
  2. Gemini, through the REST API, when a key is set. This is the CI path: a
     GitHub runner has no `claude`, and a free tier covers one call per
     matchday many times over. Gemini is just the one that was to hand —
     nothing above `_pedir_a_gemini` knows which model answered, so a third
     redactor is one function returning `list[str] | None` and one more line
     in REDACTORES.
  3. Templates. Always available, never wrong, flat.

Whatever the provider, the key is this channel's OWN key, not one borrowed
from another project — see `_clave_de_gemini` for why that matters more than
it looks.

Cost: one call per matchday, not per match — all four headlines come back in a
single response. Roughly 700 input tokens and 150 output for a four-match
matchday, which is inside every free tier involved. Nothing here is required:
with no `claude` and no key the templates take over and the render still
happens.

Public API:
    titulares(partidos, hechos=None) -> list[str]
    MAX_TITULAR
"""
import json
import os
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

# Gemini's REST endpoint. The model is a constant and not a hardcoded string in
# the call because the free tier's model names move: Google renames and retires
# them faster than this repo gets touched, and the symptom of a stale one is a
# 404 that reads like an auth problem. GEMINI_MODEL overrides it without a
# code change.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
)
GEMINI_TIMEOUT_S = 60

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


def _entrada(payload: list[dict]) -> str:
    """The full prompt: the rules, then the matches."""
    return (_PROMPT.format(max_chars=MAX_TITULAR)
            + json.dumps(payload, ensure_ascii=False, indent=2))


def _parsear(salida: str, esperados: int, quien: str) -> list[str] | None:
    """
    A model's raw answer as a list of headlines, or None if it isn't one.

    Shared by every redactor because the failure modes are the same wherever
    the text came from: a fenced block despite being asked for bare JSON,
    something that isn't JSON at all, or the wrong number of lines. What is
    NOT checked here is whether a headline is *true* — that is `_valida`, per
    headline, against its own fact.
    """
    salida = (salida or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", salida, re.S)
    if fence:
        salida = fence.group(1).strip()

    try:
        lineas = json.loads(salida)
    except ValueError:
        print(f"[WARN] {quien} no devolvió JSON válido. Titulares por plantilla.")
        return None

    if not isinstance(lineas, list) or not all(isinstance(x, str) for x in lineas):
        print(f"[WARN] {quien} devolvió algo que no es una lista de cadenas. "
              "Titulares por plantilla.")
        return None

    if len(lineas) != esperados:
        print(f"[WARN] {quien} devolvió {len(lineas)} titulares para "
              f"{esperados} partidos. Titulares por plantilla.")
        return None

    return lineas


def _clave_de_gemini() -> str:
    """
    The API key to use, preferring this channel's own.

    Two variables, and the order matters. Gemini's free tier is metered per
    API key (per Google Cloud project, really), so a key shared with another
    project shares one quota: a burst here would spend requests that the other
    project needed, and neither would know why. SHORTS_GEMINI_API_KEY exists so
    this channel can hold a key of its own, minted from a separate AI Studio
    project, and be structurally unable to interfere.

    GEMINI_API_KEY still works as a fallback because it is what is usually
    already exported on a machine, but it warns — silently borrowing another
    project's quota is exactly the surprise this is here to avoid.
    """
    propia = os.environ.get("SHORTS_GEMINI_API_KEY", "").strip()
    if propia:
        return propia

    compartida = os.environ.get("GEMINI_API_KEY", "").strip()
    if compartida:
        print("[WARN] Usando GEMINI_API_KEY, que puede ser la de otro "
              "proyecto: la cuota gratuita es por clave y se comparte. "
              "Define SHORTS_GEMINI_API_KEY para separarlas.")
    return compartida


def _pedir_a_gemini(payload: list[dict]) -> list[str] | None:
    """
    One Gemini REST call for the whole matchday. None on any failure.

    Does nothing without a key — it is optional on purpose, so cloning this
    repo and running the generator never demands a third-party account. In CI
    it comes from the repository secret. See `_clave_de_gemini` for which
    variable and why there are two.

    Volume, for judging whether a free tier covers it: one call per matchday,
    so roughly eight to ten a month for a weekly Short. That is far below any
    free tier's daily limit — the reason to keep the keys separate is not this
    project's appetite, it's that a shared bucket couples two schedules that
    have nothing to do with each other.
    """
    clave = _clave_de_gemini()
    if not clave:
        return None

    import requests

    cuerpo = {
        "contents": [{"parts": [{"text": _entrada(payload)}]}],
        # Temperature is left at the model default: these headlines are
        # constrained hard by the prompt and by _valida, and a colder setting
        # mostly produces the template phrasing we already have for free.
        "generationConfig": {"responseMimeType": "application/json"},
    }

    try:
        respuesta = requests.post(
            GEMINI_URL.format(modelo=GEMINI_MODEL),
            headers={"x-goog-api-key": clave},
            json=cuerpo,
            timeout=GEMINI_TIMEOUT_S,
        )
    except Exception as exc:
        print(f"[WARN] Falló la llamada a Gemini ({exc}). Titulares por plantilla.")
        return None

    if respuesta.status_code != 200:
        # 429 is the free tier's rate limit and is the one worth recognising:
        # it means the key works and the quota is spent, not that it is wrong.
        detalle = "cuota agotada" if respuesta.status_code == 429 else respuesta.reason
        print(f"[WARN] Gemini respondió {respuesta.status_code} ({detalle}). "
              "Titulares por plantilla.")
        return None

    try:
        texto = (respuesta.json()["candidates"][0]
                 ["content"]["parts"][0]["text"])
    except (ValueError, KeyError, IndexError, TypeError):
        print("[WARN] Gemini devolvió una respuesta con una forma inesperada. "
              "Titulares por plantilla.")
        return None

    return _parsear(texto, len(payload), "Gemini")


def _pedir_a_claude(payload: list[dict]) -> list[str] | None:
    """One `claude -p` call for the whole matchday. None on any failure."""
    claude_bin = shutil.which("claude")
    if not claude_bin:
        return None

    entrada = _entrada(payload)

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

    return _parsear(resultado.stdout, len(payload), "Claude")


# Preference: who gets asked, and in what order. Each entry is (name, function)
# and each function returns None when it isn't available or doesn't work out,
# so the chain falls through without anything special happening. Reordering
# this line is the whole knob — swap the two to prefer Gemini on the laptop
# too, or cut it to `()` to publish only template headlines.
REDACTORES = (
    ("Claude", _pedir_a_claude),
    ("Gemini", _pedir_a_gemini),
)


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

    crudos = None
    for nombre, redactor in REDACTORES:
        crudos = redactor(payload)
        if crudos:
            print(f"[INFO] Titulares escritos por {nombre}")
            break
    if crudos is None:
        print("[INFO] Ningún redactor disponible — titulares por plantilla")

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
