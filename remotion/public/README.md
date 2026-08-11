# public/

Archivos que el vídeo carga en tiempo de render. **Ninguno está en el repo**: hay que
ponerlos a mano o generarlos en el pipeline.

```
public/
├── voiceover.mp3    Locución generada fuera (edge-tts)
└── sfx/             Efectos de sonido — ver sfx/README.md
```

## voiceover.mp3

El nombre no está fijado en el código: se pasa por props.

```jsonc
{ "opciones": { "voiceover": "voiceover.mp3" } }
```

Si el archivo no existe, `archivoPublico()` devuelve `null` y el vídeo sale mudo. No
falla. Esto es lo que permite renderizar en limpio y en GitHub Actions sin audio.

## Subtítulos

Los timings palabra a palabra **no** van aquí: van en los props, en
`opciones.captions`, con el formato de `sample-data/captions.json`:

```json
[{ "palabra": "Madrid", "inicioMs": 1200, "finMs": 1450 }]
```

Los `inicioMs` son relativos al **inicio del vídeo**, que es también el inicio del
voiceover. Si el JSON no trae captions, no se queman subtítulos.

Cuando hay captions, el `Short` apaga la etiqueta de veredicto de `MatchProbability` y
el sello del nº1 de `RankingCountdown`: ambos caen en la franja baja de la zona segura,
que es justo donde se colocan los subtítulos.
