import {zColor} from '@remotion/zod-types';
import {z} from 'zod';

/**
 * Esquemas Zod de los datos de jornada.
 *
 * Se declaran con Zod (y no solo con `type`) por dos motivos:
 *  1. Remotion genera un editor de props visual en el Studio a partir del
 *     schema de cada composicion: puedes cambiar un color o una probabilidad
 *     desde la UI y ver el resultado al instante.
 *  2. Sirven para validar el JSON que entra por `--props` antes de renderizar.
 *
 * `zColor()` hace que el Studio pinte un selector de color en vez de un input
 * de texto.
 */

export const equipoSchema = z.object({
	nombre: z.string().min(1),
	colorPrimario: zColor(),
	colorSecundario: zColor(),
});
export type Equipo = z.infer<typeof equipoSchema>;

export const partidoSchema = z.object({
	local: equipoSchema,
	visitante: equipoSchema,
	probLocal: z.number().min(0).max(1),
	probEmpate: z.number().min(0).max(1),
	probVisitante: z.number().min(0).max(1),
	/** Marcador predicho, tal cual se pinta: "2-1". */
	prediccion: z.string().min(1),
	/**
	 * Resultado que resalta el grafico. Lo decide el motor de predicciones y
	 * viaja en el JSON para que el video no vuelva a deducirlo por su cuenta:
	 * con dos implementaciones del mismo argmax (Python y TypeScript) sobre
	 * probabilidades ya redondeadas, un partido ajustado puede resaltar una
	 * barra distinta de la que dice el marcador.
	 *
	 * Ademas el motor llama empate a los partidos casi igualados, cosa que un
	 * argmax nunca haria: en un Poisson el empate no es nunca el resultado mas
	 * probable de los tres, ni con equipos identicos (38/24/38).
	 *
	 * Opcional: si falta, se usa la barra mas alta.
	 */
	resultadoPredicho: z.enum(['local', 'empate', 'visitante']).optional(),
	/**
	 * Frase corta y editorial. Es el gancho visual del bloque.
	 *
	 * El tope de 48 no es estilo: `tamanoTitular` baja el cuerpo a 72px por
	 * encima de 44 caracteres, y a partir de ~48 la frase parte a una tercera
	 * linea y se sale de la zona segura. Que reviente la validacion aqui es
	 * mejor que descubrirlo mirando el mp4. El generador usa el mismo numero
	 * (MAX_TITULAR en champions_titulares.py) — si cambias uno, cambia el otro.
	 */
	titular: z.string().min(1).max(48),
});
export type Partido = z.infer<typeof partidoSchema>;

export const rankingEntradaSchema = z.object({
	equipo: z.string().min(1),
	colorPrimario: zColor(),
	/**
	 * La probabilidad que el countdown enseña. El nombre viene de cuando la
	 * unica pregunta era el titulo; ahora la pregunta la fija
	 * `opciones.tituloRanking` y esto es su respuesta, sea "gana la liga" o
	 * "entra en plazas de Champions". Si cambias uno, cambia el otro: aqui
	 * solo hay un numero y el texto de arriba es lo unico que dice de que va.
	 */
	probTitulo: z.number().min(0).max(1),
});
export type RankingEntrada = z.infer<typeof rankingEntradaSchema>;

export const aciertosSchema = z.object({
	acertados: z.number().int().min(0),
	total: z.number().int().min(1),
});
export type Aciertos = z.infer<typeof aciertosSchema>;

/**
 * Los aciertos son OPCIONALES, y eso es una regla editorial, no una comodidad.
 *
 * El bloque de prueba social dice "acertamos N de M", una afirmacion que solo
 * se puede hacer si hubo una jornada anterior publicada contra la que medirla
 * (resultados.py). En el primer Short del canal no la hay, y el generador se
 * niega a inventarla: el Short se salta el bloque y dura dos segundos menos,
 * en vez de afirmar un numero que nadie ha medido.
 *
 * OJO, y esto costo un render entender: para quitar el bloque hay que mandar
 * `null` EXPLICITO, no omitir la clave. Remotion mezcla lo que llega por
 * `--props` ENCIMA de los `defaultProps` de la composicion, y los de Short
 * salen de sample-data/jornada.json, que trae un 6 de 8. Una clave ausente no
 * desaparece: hereda el dato del ejemplo, y el Short acaba afirmando en
 * pantalla un marcador que viene de un fichero de prueba. De ahi `nullish` en
 * vez de `optional`.
 */

/**
 * Timing palabra a palabra del voiceover, tal y como lo genera el pipeline de
 * audio (edge-tts + alineado). Es el contenido de `captions.json`.
 */
export const palabraCaptionSchema = z.object({
	palabra: z.string(),
	inicioMs: z.number().min(0),
	finMs: z.number().min(0),
});
export type PalabraCaption = z.infer<typeof palabraCaptionSchema>;

export const jornadaSchema = z.object({
	competicion: z.string().min(1),
	/** ISO 8601, YYYY-MM-DD. */
	fecha: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
	aciertosJornadaAnterior: aciertosSchema.nullish(),
	partidos: z.array(partidoSchema).min(1),
	ranking: z.array(rankingEntradaSchema),
});
export type Jornada = z.infer<typeof jornadaSchema>;
