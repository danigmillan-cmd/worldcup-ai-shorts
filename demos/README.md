# Demos

Vídeos de muestra de los dos canales, generados el 12-ago-2026 con el pipeline
completo. Cada `.mp4` tiene al lado el `.json` exacto con el que se renderizó,
así que se puede volver a producir el mismo vídeo:

```powershell
cd remotion
npx remotion render Short ../demos/laliga.mp4 --props=../demos/jornada-laliga.json
```

| Fichero | Qué es | Partidos |
| --- | --- | --- |
| `laliga.mp4` / `jornada-laliga.json` | LaLiga, 41 s | Valencia-Celta, Espanyol-Real Madrid, Atlético-Málaga, Elche-Barcelona (19-23 ago) |
| `champions.mp4` / `jornada-champions.json` | Champions, 41 s | Real Madrid-Bayern, Man City-Inter, Arsenal-Barcelona, PSG-Liverpool |

Los dos son 1080x1920 a 30 fps, 1230 fotogramas, CRF 23 (~15 MB).

## Qué es real y qué no

Los dos JSON llevan un campo `_demo` que dice lo mismo que esta sección. No es
un detalle menor: el canal se sostiene sobre no afirmar cosas que no podemos
demostrar, y una demo no es excusa para saltárselo.

**LaLiga — real de punta a punta.** Calendario y clasificación de ESPN, Elo de
ClubElo, probabilidades y marcadores del modelo, titulares generados desde
hechos verificados.

Es la **jornada 2**, no la 1, y no es un error: en la jornada 1 de 2026-27 no
juega ninguno de los equipos del filtro — ni Madrid, ni Barça, ni Valencia, ni
Betis. El selector amplía la ventana hasta reunir partidos que interesen.

**Champions — emparejamientos inventados.** El sorteo de la fase liga 2026-27
no se ha celebrado: ESPN sigue sirviendo la temporada 2025-26 y devuelve cero
partidos. Los cuatro cruces son plausibles, no reales. Todo lo demás —clubes,
Elo, probabilidades, marcador, titulares— sale del pipeline de verdad.

**Los aciertos son un marcador de posición en los dos.** El bloque de prueba
social dice "acertamos 3 de 4", y no hay ninguna jornada anterior que puntuar
porque la temporada no ha empezado. En producción ese número lo calcula
`resultados.py` contra resultados reales, y el generador se niega a arrancar si
no puede.

## Qué falta para que esto sea el vídeo final

- **Cierre.** Los dos cierran con CTA en vez del countdown de probabilidad de
  título, que necesita una simulación de liga que no está escrita. Con 4
  partidos y CTA salen 41 s, dentro del objetivo de 35-50 s.
- **Audio.** Sin voz en off ni subtítulos: `opciones.voiceover` va a `null` y no
  hay efectos en `public/sfx/`. Los cues de sonido están puestos y suenan solos
  en cuanto se añadan los mp3.
