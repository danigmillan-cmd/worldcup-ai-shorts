#!/usr/bin/env python3
"""
scripts/gemini_modelos.py
Lists the Gemini models a key can actually reach.

    python scripts/gemini_modelos.py

Exists because the failure it diagnoses is silent and recurring. Google renames
and retires free-tier models faster than this repo gets touched, and a stale
name comes back as a 404 that reads like an auth problem —
champions_titulares.py then falls through to templates and the Short publishes
flatter without anyone noticing. Guessing the new name from memory is how you
get a second 404, so this asks.

Prints Markdown, because its main caller is a GitHub Actions step summary.
Reads the key the same way champions_titulares does, so it diagnoses the key
that is actually in use rather than a different one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import champions_titulares  # noqa: E402

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"


def main() -> int:
    print("\n### Modelos que acepta esta clave\n")

    clave = champions_titulares._clave_de_gemini()
    if not clave:
        print("_Sin clave configurada: no hay a quién preguntar._")
        return 1

    import requests

    try:
        respuesta = requests.get(
            ENDPOINT, headers={"x-goog-api-key": clave}, timeout=30
        )
    except Exception as exc:
        print(f"_No se pudo consultar la lista de modelos: {exc}_")
        return 1

    if respuesta.status_code != 200:
        # A 401/403 here says the key itself is the problem, which is a
        # different fix from a renamed model — worth distinguishing.
        print(f"_La consulta devolvió {respuesta.status_code}._ "
              "Un 401 o 403 apunta a la clave, no al nombre del modelo.")
        print(f"\n```\n{respuesta.text[:400]}\n```")
        return 1

    nombres = [
        modelo["name"].removeprefix("models/")
        for modelo in respuesta.json().get("models", [])
        if "generateContent" in modelo.get("supportedGenerationMethods", [])
    ]

    if not nombres:
        print("_La clave funciona pero no alcanza ningún modelo que sirva para "
              "esto (`generateContent`)._")
        return 1

    print("Pon uno de estos en `GEMINI_MODEL`:\n")
    print("```")
    print("\n".join(nombres))
    print("```")
    return 0


if __name__ == "__main__":
    sys.exit(main())
