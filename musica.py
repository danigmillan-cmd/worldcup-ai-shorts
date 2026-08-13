#!/usr/bin/env python3
"""
musica.py
Picks the background track for the next Short, a different one each time.

    python musica.py              # qué sonaría ahora, sin gastar el turno
    python musica.py --preparar   # elige, copia a remotion/public/ y avanza

The rotation is a counter in data/jornada_music_index.json, not a random
draw: random repeats. Over nine tracks a coin-flip picks the same one twice in
a row about one time in nine, and two Shorts in a row with the same music
reads as a bug to anyone who watches both.

The pool is "every mp3 in assets/music", sorted by name. There is no list of
filenames to maintain — adding a track is dropping a file in, removing one is
deleting it. That also means the counter is not a stable identity: adding a
file shifts what comes next. It doesn't matter, because the only property
that has to hold is "different from last time", and any shift preserves it.

Remotion can only read from its own public/ directory, so the chosen track is
copied there under a slugified name. Files with spaces or accents survive
`staticFile()` badly enough that it isn't worth finding out where exactly.

Public API:
    pistas() -> list[Path]
    siguiente(avanzar=True, destino=None) -> str | None
"""
import argparse
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import config

# Where remotion/public lives, relative to the repo root.
PUBLIC_DIR = config.ROOT / "remotion" / "public"


def pistas() -> list[Path]:
    """Every track in the pool, in a stable order."""
    if not config.MUSIC_DIR.is_dir():
        return []
    return sorted(config.MUSIC_DIR.glob("*.mp3"), key=lambda p: p.name.lower())


def _slug(nombre: str) -> str:
    """'No Mercy - TrackTribe.mp3' -> 'no-mercy-tracktribe.mp3'."""
    tallo = Path(nombre).stem
    plano = (unicodedata.normalize("NFKD", tallo)
             .encode("ascii", "ignore").decode("ascii"))
    limpio = re.sub(r"[^a-zA-Z0-9]+", "-", plano).strip("-").lower()
    return f"{limpio or 'pista'}.mp3"


def _indice() -> int:
    try:
        return int(json.loads(
            config.JORNADA_MUSICA_INDEX_FILE.read_text(encoding="utf-8")
        )["next"])
    except Exception:
        return 0


def _guardar_indice(valor: int) -> None:
    try:
        config.JORNADA_MUSICA_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.JORNADA_MUSICA_INDEX_FILE.write_text(
            json.dumps({"next": valor}), encoding="utf-8"
        )
    except OSError as exc:
        # Not fatal: the Short still gets music, it just gets the same one
        # again next time. Worth a warning, not worth failing a render over.
        print(f"[WARN] No se pudo guardar el índice de música: {exc}")


def siguiente(avanzar: bool = True, destino: Path | None = None) -> str | None:
    """
    The next track, copied into public/, as a path relative to public/.

    Returns None when there is no music to use, which is a normal state and
    not an error — `archivoPublico` in the Remotion side renders a silent
    Short rather than failing, the same way it handles a missing voiceover.

    `avanzar=False` answers "what would play" without spending the turn, which
    is what the bare CLI does.
    """
    disponibles = pistas()
    if not disponibles:
        print(f"[WARN] No hay mp3 en {config.MUSIC_DIR} — el Short saldrá sin música")
        return None

    indice = _indice() % len(disponibles)
    elegida = disponibles[indice]

    carpeta = (destino or PUBLIC_DIR) / config.JORNADA_MUSICA_PUBLIC_SUBDIR
    relativa = f"{config.JORNADA_MUSICA_PUBLIC_SUBDIR}/{_slug(elegida.name)}"

    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        shutil.copy2(elegida, carpeta / _slug(elegida.name))
    except OSError as exc:
        print(f"[WARN] No se pudo copiar «{elegida.name}» a public/ ({exc}) — "
              "el Short saldrá sin música")
        return None

    if avanzar:
        _guardar_indice((indice + 1) % len(disponibles))

    print(f"[INFO] Música: «{elegida.stem}» ({indice + 1} de {len(disponibles)})")
    return relativa


def main() -> int:
    cli = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    cli.add_argument("--preparar", action="store_true",
                     help="Copia la pista a public/ y avanza el turno.")
    args = cli.parse_args()

    disponibles = pistas()
    if not disponibles:
        print(f"No hay ninguna pista en {config.MUSIC_DIR}")
        return 1

    indice = _indice() % len(disponibles)
    print(f"Pistas en rotación ({len(disponibles)}):")
    for i, pista in enumerate(disponibles):
        print(f"  {'→' if i == indice else ' '} {pista.stem}")

    if args.preparar:
        print()
        siguiente()
    return 0


if __name__ == "__main__":
    sys.exit(main())
