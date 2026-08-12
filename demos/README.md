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
| `laliga.mp4` / `jornada-laliga.json` | LaLiga, 48,4 s, countdown de **plazas de Champions**. El formato elegido. | Valencia-Celta, Espanyol-Real Madrid, Atlético-Málaga, Elche-Barcelona (19-23 ago) |
| `laliga-titulo.mp4` / `jornada-laliga-titulo.json` | Los mismos partidos con el countdown del **título**, para comparar | ídem |
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

## Las dos versiones del countdown

Las probabilidades salen de `liga_simulator.py`: juega los 380 partidos que
quedan 20.000 veces con el mismo modelo que produce las barras del cuerpo del
vídeo, y mira dónde acaba cada equipo. No es un ranking por Elo. **Una sola
simulación responde las dos preguntas** — solo cambia por dónde se corta la
tabla final.

| | Título (corte 1) | Plazas de Champions (corte 4) |
| --- | --- | --- |
| Barcelona | 63,5 % | 100,0 % |
| Real Madrid | 34,4 % | 99,8 % |
| Atlético | 1,9 % | 87,8 % |
| Villarreal | 0,1 % | 42,3 % |
| Betis | 0,1 % | 31,6 % |

**El del título muere por abajo:** las tres últimas posiciones son ~0 % y lo
seguirán siendo buena parte de la temporada.

**El de Champions muere por arriba:** Barcelona y Madrid entran seguro, así que
las dos primeras posiciones no tienen intriga — y como el countdown va de la
quinta a la primera, termina en un 100 %.

Se eligió el de Champions: el título en LaLiga es demasiado previsible.

### Por qué no una clasificación esperada

Se consideró y se descartó. Sale en **el mismo orden** —ordena por fuerza, así
que no arregla lo de "demasiado obvio"— y encima es más engañosa: "4.
Villarreal, 63 pts" se lee como una predicción, pero Villarreal acaba cuarto
solo en el **28,5 %** de las temporadas simuladas, Betis quinto en el 20,3 % y
Rayo sexto en el 12,9 %. La tabla entera tal y como se ve prácticamente nunca
ocurre: es la media de muchos futuros, no la predicción de uno. Una
probabilidad dice lo que sabe; una media lo esconde.

Lo único en lo que ganaba es que ningún hueco queda muerto (89, 85, 72, 62, 60
son todos distintos). Eso se arregla eligiendo mejor la pregunta.

## Qué falta para que esto sea el vídeo final

- **La Champions cierra con CTA.** Su countdown necesitaría simular fase liga
  más playoffs más eliminatorias, y el cuadro depende de un sorteo que aún no
  existe. `liga_simulator.py` no sirve para eso: simula una liga, no una copa.
- **Audio.** Sin voz en off ni subtítulos: `opciones.voiceover` va a `null` y no
  hay efectos en `public/sfx/`. Los cues de sonido están puestos y suenan solos
  en cuanto se añadan los mp3.
