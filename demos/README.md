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
| `laliga.mp4` / `jornada-laliga.json` | LaLiga, 48,4 s, countdown de **plazas de Champions** | Valencia-Celta, Espanyol-Real Madrid, Atlético-Málaga, Elche-Barcelona (19-23 ago) |
| `champions.mp4` / `jornada-champions.json` | Champions, 41 s, cierra con CTA | Real Madrid-Bayern, Man City-Inter, Arsenal-Barcelona, PSG-Liverpool |

Los dos son 1080x1920 a 30 fps, CRF 23.

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

## El countdown

Las probabilidades salen de `liga_simulator.py`: juega los 380 partidos que
quedan 20.000 veces con el mismo modelo que produce las barras del cuerpo del
vídeo, y mira dónde acaba cada equipo. No es un ranking por Elo.

La pregunta es **quién acaba entre los cuatro primeros**, y sale **del más
probable al menos probable**:

| | |
| --- | --- |
| Nº1 Barcelona | 100,0 % |
| Nº2 Real Madrid | 99,8 % |
| Nº3 Atlético | 87,8 % |
| Nº4 Villarreal | 42,3 % |
| Nº5 Betis | 31,6 % |

El orden es al revés de lo que pide el instinto, y a propósito. Rematar en
Barcelona sería rematar en el dato más previsible del vídeo; así el que se
queda en pantalla al final es el que de verdad está en juego. La franja larga
—el doble de tiempo— va al último que sale, no al número 1.

Se descartaron dos alternativas:

- **El título.** En LaLiga es demasiado previsible: deja tres de las cinco
  posiciones a ~0 % buena parte de la temporada.
- **Una clasificación esperada.** Sale en el mismo orden —ordena por fuerza, así
  que no arregla lo de "obvio"— y encima es más engañosa: "4. Villarreal, 63
  pts" se lee como predicción, pero Villarreal acaba cuarto solo en el **28,5 %**
  de las temporadas simuladas, Betis quinto en el 20,3 % y Rayo sexto en el
  12,9 %. La tabla entera tal y como se vería prácticamente nunca ocurre: es la
  media de muchos futuros, no la predicción de uno.

## Qué falta para que esto sea el vídeo final

- **La Champions cierra con CTA.** Su countdown necesitaría simular fase liga
  más playoffs más eliminatorias, y el cuadro depende de un sorteo que aún no
  existe. `liga_simulator.py` no sirve para eso: simula una liga, no una copa.
- **Audio.** Sin voz en off ni subtítulos: `opciones.voiceover` va a `null` y no
  hay efectos en `public/sfx/`. Los cues de sonido están puestos y suenan solos
  en cuanto se añadan los mp3.
