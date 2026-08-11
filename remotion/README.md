# champions-shorts — capa visual en Remotion

Renderiza Shorts verticales (1080x1920, 30 fps) de predicciones de Champions a partir
de un JSON de jornada. Vídeo programático en React: no hay editor, la animación es
código y los datos entran por props.

Vive dentro del repo `worldcup-ai-shorts` pero es un proyecto Node independiente:
todos los comandos se ejecutan **desde esta carpeta**.

## Puesta en marcha

```powershell
cd remotion
npm install
npm run studio
```

El Studio abre en `http://localhost:3000`. En el panel derecho hay un editor de props
generado a partir del schema Zod de cada composición: puedes cambiar un color o una
probabilidad y ver el resultado sin tocar código ni recargar.

## Render por CLI

`Short` es la composición que se publica. Sus props **son la jornada tal cual**, así que
el fichero de jornada se pasa sin envoltorios:

```powershell
npx remotion render Short out/short.mp4 --props=sample-data/jornada.json
```

Para ajustar duración, cierre, audio o subtítulos, añade un bloque `opciones` al mismo
JSON (ejemplo completo en `sample-data/short-props.json`):

```jsonc
{
  "competicion": "...", "fecha": "...", "partidos": [...], "ranking": [...],
  "opciones": {
    "maxPartidos": 3,          // cuántos partidos entran en el cuerpo
    "cierre": "cta",           // "ranking" | "cta"
    "voiceover": "voz.mp3",    // relativo a public/, null = mudo
    "captions": [...]          // timings palabra a palabra, null = sin subtítulos
  }
}
```

Todos los campos de `opciones` son opcionales y se completan con los valores por defecto
de `OPCIONES_POR_DEFECTO` (`src/compositions/Short.tsx`). Esto no es comodidad: Remotion
mezcla `defaultProps` con `--props` de forma **superficial**, así que un `opciones`
parcial sustituye al objeto entero. Con campos obligatorios, pasar solo
`{"opciones": {"cierre": "cta"}}` reventaría la validación.

**La duración no está fijada en el código.** `calculateMetadata` la calcula a partir de
los props: 2s de gancho + 2s de prueba social + 8s por partido + el cierre
(12,4s si es ranking, 5s si es CTA). Cuatro partidos con ranking = 48,4s. Tres partidos
con CTA = 33s, por debajo del objetivo de 35-50s; con tres partidos usa el cierre de
ranking.

**Calidad.** `remotion.config.ts` fija CRF 23. El defecto de Remotion es 18, calidad de
máster: para este Short son 44 MB frente a 17 MB, y YouTube reencoda igual. Sube la
calidad puntualmente con `--crf 18`.

Las otras composiciones son piezas sueltas y su `--props` sigue el schema de cada una,
no el de la jornada. Para `MatchProbability`:

```jsonc
{ "partido": { /* ...un partido... */ }, "indice": 1, "total": 4 }
```

### `resultadoPredicho`

Cada partido puede traer `"resultadoPredicho": "local" | "empate" | "visitante"`. Es la
barra que se resalta. Lo decide el motor de predicciones y viaja en el JSON para que el
vídeo no lo deduzca por su cuenta: con dos implementaciones del mismo argmax (Python y
TypeScript) sobre probabilidades ya redondeadas, un partido ajustado puede resaltar una
barra que no cuadre con el marcador.

Además, el motor llama empate a los partidos casi igualados, cosa que un argmax nunca
haría — en un Poisson el empate no es nunca el resultado más probable de los tres, ni
con equipos idénticos (38/24/38). En ese caso el gráfico resalta **los dos equipos**, no
la barra de empate, que es la más corta de las tres.

Si el campo falta, se usa la barra más alta. Las jornadas escritas a mano siguen
funcionando.

## Estructura del Short

| Bloque         | Duración         | Qué es                                              |
| -------------- | ---------------- | --------------------------------------------------- |
| Hook           | 60f (2s)         | El favorito más claro de la jornada, a pantalla completa. Sin intro ni logo. |
| Prueba social  | 60f (2s)         | `aciertosJornadaAnterior` con contador               |
| Cuerpo         | 240f (8s) × N    | `MatchProbability` encadenado                        |
| Cierre         | 372f o 150f      | `RankingCountdown` o CTA, según `opciones.cierre`    |

El gancho se deduce del partido más desequilibrado del JSON. Se puede forzar con
`opciones.hookTexto`.

## Reglas del proyecto

**Safe areas.** La UI de YouTube Shorts tapa el 10% superior y el 18% inferior. Están
en `src/theme.ts` (`SAFE`) y todo el contenido vive dentro. Nunca metas datos ahí.

**Ritmo.** Nunca más de 45 frames (1,5s) sin un corte o un cambio visual fuerte. Todas
las entradas con `spring()`, nada de `interpolate` lineal para animar apariciones. El
fondo (`MovingBackdrop`) no se para nunca.

Los contadores y las barras usan `muelleFirme()` (con `overshootClamping`), no
`muelle()`: un muelle con rebote haría que un 41% enseñase 46% antes de asentarse, y en
un número eso no parece animación, parece un bug.

**Marca.** Cero escudos de club, cero logos o marca UEFA/Champions. Los equipos se
representan solo con el nombre en texto y bloques de su color, siempre desde el JSON.
Nada de himno ni música con copyright: solo los SFX que se aporten a mano.

**Acentos.** Anton no reserva hueco para las tildes de las mayúsculas: con un
`lineHeight` bajo, la Í de "TÍTULO" en una segunda línea invade el renglón de arriba.
Todo texto de display que pueda partirse usa `INTERLINEADO_DISPLAY` (`src/theme.ts`).
En castellano esto pasa constantemente.

**Portabilidad.** El render final corre en Ubuntu headless. Sin rutas absolutas, sin
dependencias de Windows y sin fuentes del sistema — la tipografía entra por
`@remotion/google-fonts`, que es un paquete npm.

## Estructura

```
sample-data/jornada.json   Jornada de ejemplo (datos inventados)
sample-data/captions.json  Timings palabra a palabra de ejemplo
public/sfx/                Efectos de sonido (los archivos se ponen a mano)
src/types.ts               Schemas Zod + tipos de los datos de entrada
src/theme.ts               Fuentes, colores, safe areas, constantes de vídeo
src/sfx.ts                 Constantes de SFX y comprobación de existencia
src/lib/color.ts           Contraste y legibilidad de los colores del JSON
src/lib/animacion.ts       Muelles y sacudida de impacto
src/lib/probabilidades.ts  Normalización de probabilidades y veredicto
src/lib/captions.ts        Adaptador a @remotion/captions y reparto uniforme
src/components/            Componentes compartidos
src/compositions/          Una composición por escena
src/Root.tsx               Registro de composiciones
```

## Componentes compartidos

| Componente        | Qué hace                                                          |
| ----------------- | ----------------------------------------------------------------- |
| `AnimatedCounter` | Número que rueda de 0 al valor final, sin rebote                   |
| `TeamChip`        | Nombre de equipo sobre bloque de su color primario                 |
| `WordCaptions`    | Subtítulos palabra a palabra con pop y cambio de color             |
| `SfxCue`          | Coloca un efecto de sonido en un frame; mudo si falta el archivo   |
| `ProgressBar`     | Barra fina de progreso — **debe ir en la raíz, fuera de Sequence** |
| `MovingBackdrop`  | Fondo que nunca se para                                            |

`ProgressBar` usa `useCurrentFrame()`, que dentro de un `<Sequence>` es relativo a esa
secuencia. Montada dentro de una, mediría el progreso del bloque, no el del Short.

## Nota de licencia

Remotion es gratis para uso individual y empresas de hasta 3 personas, pero requiere
licencia de pago por encima de eso. Ver https://remotion.dev/license
