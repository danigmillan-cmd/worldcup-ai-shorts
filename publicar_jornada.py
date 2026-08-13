#!/usr/bin/env python3
"""
publicar_jornada.py
Publishes a rendered matchday Short to YouTube.

    python publicar_jornada.py remotion/out/Short.mp4 remotion/jornada-laliga.json

Takes the two things the pipeline already produces — the mp4 that Remotion
rendered and the JSON that generar_jornada_laliga.py built — and turns them
into a scheduled upload. Nothing is computed here: every number in the
description is read back out of the JSON, for the same reason the on-screen
headlines are (champions_facts.py), so the text under the video cannot drift
from the video.

Same channel, same credentials
------------------------------
These Shorts go to the World Cup channel (decision of 13-ago-2026), so the
GOOGLE_CLIENT_SECRET / YOUTUBE_TOKEN already in the repo are the right ones and
uploader.py needs no second token. What separates a matchday Short from a World
Cup one is metadata only: Spanish language tag, its own titles, its own
hashtags — all in config.JORNADA_YT_*.

When it goes out
----------------
The JSON carries `publicacion.publicar_en_utc`, 24 h before the first match it
previews. That becomes YouTube's `publishAt`, which decouples rendering from
publishing: the render can run whenever a runner is free and the Short still
surfaces at the right hour. If that moment has already passed the video is
published immediately instead — a Short about matches that kick off tomorrow is
worth less every hour it waits, and silently scheduling it into the past would
leave it private forever.

Public API:
    metadatos(jornada) -> dict
    publicar(video, jornada, privacidad=None, programar=True) -> dict
"""
import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import config
import processed_matches
import uploader

# How many fixtures the description lists before it stops. The Short shows four;
# the cap exists so a longer matchday cannot push the hashtags out of the
# ~157 characters YouTube shows before "...more".
MAX_PARTIDOS_EN_DESCRIPCION = 6

# Competition name -> the hashtag that carries it. Anything not listed falls
# back to the name with spaces stripped, which is right for most.
HASHTAGS = {
    "LaLiga": "LaLiga",
    "Champions": "ChampionsLeague",
}

RESULTADO_EN_TEXTO = {
    "local": "gana el local",
    "empate": "empate",
    "visitante": "gana el visitante",
}


def _hashtag(competicion: str) -> str:
    return HASHTAGS.get(competicion, competicion.replace(" ", ""))


def _equipos_del_titular(jornada: dict) -> str:
    """
    The fixture the title leads with: the first one the Short shows.

    generar_jornada_laliga.py already orders the matchday by kick-off, so the
    first match is the nearest one — the one a viewer scrolling on Friday can
    still act on. Picking "the two biggest clubs" instead is a defensible taste
    call and belongs here rather than in the caller, but it needs a notion of
    club size that this JSON deliberately does not carry.
    """
    partidos = jornada.get("partidos") or []
    if not partidos:
        return jornada.get("competicion", "")
    primero = partidos[0]
    return f"{primero['local']['nombre']} - {primero['visitante']['nombre']}"


def _resumen(jornada: dict) -> str:
    """The prediction lines of the description, straight from the JSON."""
    lineas = []
    for partido in (jornada.get("partidos") or [])[:MAX_PARTIDOS_EN_DESCRIPCION]:
        local = partido["local"]["nombre"]
        visitante = partido["visitante"]["nombre"]
        veredicto = RESULTADO_EN_TEXTO.get(partido.get("resultadoPredicho"), "")
        prob = max(
            partido.get("probLocal", 0),
            partido.get("probEmpate", 0),
            partido.get("probVisitante", 0),
        )
        lineas.append(
            f"{local} - {visitante}: {partido['prediccion']} "
            f"({veredicto}, {prob:.0%})"
        )

    aciertos = jornada.get("aciertosJornadaAnterior") or {}
    if aciertos.get("total"):
        lineas.append("")
        lineas.append(
            f"La jornada pasada acertamos {aciertos['acertados']} "
            f"de {aciertos['total']}."
        )
    return "\n".join(lineas)


def metadatos(jornada: dict) -> dict:
    """
    Builds title / description / tags for the upload.

    The chosen title template's index comes back as "title_template_index" so a
    caller can log which variant went out, matching match_data.youtube_metadata
    on the World Cup side.
    """
    competicion = jornada.get("competicion", "")
    indice = random.randrange(len(config.JORNADA_YT_TITLES))
    titulo = config.JORNADA_YT_TITLES[indice].format(
        competicion=competicion,
        fecha=jornada.get("fecha", ""),
        equipos=_equipos_del_titular(jornada),
    )

    descripcion = config.JORNADA_YT_DESCRIPTION.format(
        competicion=competicion,
        fecha=jornada.get("fecha", ""),
        resumen=_resumen(jornada),
        hashtag=_hashtag(competicion),
    )

    # The clubs on screen are the tags most likely to be searched, so they go
    # in front of the generic ones.
    clubes = []
    for partido in jornada.get("partidos") or []:
        for lado in ("local", "visitante"):
            nombre = partido[lado]["nombre"]
            if nombre not in clubes:
                clubes.append(nombre)

    return {
        "title": titulo[:100],          # YouTube's hard limit
        "description": descripcion,
        "tags": [competicion, *clubes, *config.JORNADA_YT_TAGS],
        "title_template_index": indice,
    }


def _cuando_publicar(jornada: dict) -> str | None:
    """
    `publicacion.publicar_en_utc` as an RFC 3339 UTC timestamp, or None.

    None means "publish on arrival", and there are two ways to get there: the
    generator could not work out a publication time (ESPN had no kick-off hour
    for some match), or the time it worked out is already behind us.
    """
    pub = jornada.get("publicacion") or {}
    crudo = pub.get("publicar_en_utc")
    if not crudo:
        print("[INFO] La jornada no trae hora de publicación — se publica ya")
        return None

    try:
        cuando = datetime.fromisoformat(crudo.replace("Z", "+00:00"))
    except ValueError:
        print(f"[WARN] Hora de publicación ilegible ({crudo!r}) — se publica ya")
        return None

    if cuando.tzinfo is None:
        cuando = cuando.replace(tzinfo=timezone.utc)
    if cuando <= datetime.now(timezone.utc):
        print(f"[WARN] La hora de publicación ({crudo}) ya ha pasado — se publica ya")
        return None

    return cuando.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _anotar_en_el_registro(jornada: dict, video: Path, url: str) -> str | None:
    """
    Mark this matchday's slot as published, so the cron doesn't publish it
    twice.

    Written HERE and not in ciclo_jornada.py because only a completed upload
    should close a slot: a run that rendered and then failed to upload has to
    be retried, not skipped. Returns the ledger key, or None if the matchday
    carries no publication block to key on.

    ciclo_jornada is imported lazily — it pulls in ESPN, ClubElo and the
    simulator, none of which an upload needs.
    """
    import ciclo_jornada

    publicacion = jornada.get("publicacion")
    if not publicacion or not publicacion.get("publicar_en_local"):
        print("[INFO] La jornada no trae bloque de publicación — no se anota "
              "en el registro de Shorts publicados")
        return None

    clave = ciclo_jornada.clave_de_slot(
        jornada.get("competicion", "?"), publicacion
    )
    processed_matches.mark_processed(
        clave,
        uploaded=True,
        youtube_url=url,
        video_path=str(video),
        data=processed_matches.load(config.JORNADA_SHORTS_FILE),
        path=config.JORNADA_SHORTS_FILE,
    )
    print(f"[INFO] Anotado en el registro: {clave}")
    return clave


def publicar(video: Path, jornada: dict, privacidad: str | None = None,
             programar: bool = True, anotar: bool = True) -> dict:
    """
    Uploads `video` with the metadata `jornada` implies.

    Returns {"video_id", "youtube_url", "publish_at", "clave", **metadatos}.
    """
    if not video.exists():
        raise FileNotFoundError(f"No hay vídeo en {video}")

    meta = metadatos(jornada)
    publish_at = _cuando_publicar(jornada) if programar else None

    print("  Autenticando con YouTube...")
    yt = uploader.get_upload_client()
    print()

    video_id = uploader.upload_video(
        yt,
        video_path=video,
        title=meta["title"],
        description=meta["description"],
        tags=meta["tags"],
        privacy=privacidad or config.JORNADA_YT_PRIVACY,
        language=config.JORNADA_YT_LANGUAGE,
        publish_at=publish_at,
    )

    url = f"https://www.youtube.com/shorts/{video_id}"
    clave = _anotar_en_el_registro(jornada, video, url) if anotar else None

    return {
        **meta,
        "video_id": video_id,
        "youtube_url": url,
        "publish_at": publish_at,
        "clave": clave,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("video", type=Path, help="El mp4 que rindió Remotion")
    parser.add_argument("jornada", type=Path, help="El JSON de la jornada")
    parser.add_argument(
        "--privacidad", choices=["public", "unlisted", "private"],
        help=f"Por defecto {config.JORNADA_YT_PRIVACY}. Se ignora al programar: "
             "YouTube exige que un vídeo programado esté en private hasta su hora.",
    )
    parser.add_argument(
        "--ya", action="store_true",
        help="Publica en cuanto suba, ignorando la hora de la jornada.",
    )
    parser.add_argument(
        "--en-seco", action="store_true",
        help="Enseña el título y la descripción que se subirían, y no sube nada.",
    )
    parser.add_argument(
        "--no-anotar", action="store_true",
        help="No cerrar el slot en el registro de Shorts publicados. Para "
             "subidas a mano que no deben impedir la del cron.",
    )
    args = parser.parse_args()

    with open(args.jornada, encoding="utf-8") as fh:
        jornada = json.load(fh)

    if args.en_seco:
        meta = metadatos(jornada)
        cuando = _cuando_publicar(jornada) if not args.ya else None
        print(f"\nTítulo      : {meta['title']}")
        print(f"Etiquetas   : {', '.join(meta['tags'])}")
        print(f"Publicar en : {cuando or 'al subir'}")
        print(f"\n{meta['description']}\n")
        return

    resultado = publicar(
        args.video, jornada,
        privacidad=args.privacidad,
        programar=not args.ya,
        anotar=not args.no_anotar,
    )
    print(f"\n  Video ID  : {resultado['video_id']}")
    print(f"  Short URL : {resultado['youtube_url']}")
    if resultado["publish_at"]:
        print(f"  Programado: {resultado['publish_at']}")
    print(f"  Studio    : "
          f"https://studio.youtube.com/video/{resultado['video_id']}/edit")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)
