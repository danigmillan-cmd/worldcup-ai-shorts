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
	probTitulo: z.number().min(0).max(1),
});
export type RankingEntrada = z.infer<typeof rankingEntradaSchema>;

export const aciertosSchema = z.object({
	acertados: z.number().int().min(0),
	total: z.number().int().min(1),
});
export type Aciertos = z.infer<typeof aciertosSchema>;

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
	aciertosJornadaAnterior: aciertosSchema,
	partidos: z.array(partidoSchema).min(1),
	ranking: z.array(rankingEntradaSchema),
});
export type Jornada = z.infer<typeof jornadaSchema>;
