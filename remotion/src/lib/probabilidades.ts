import type {Partido} from '../types';

export type Resultado = 'local' | 'empate' | 'visitante';

export type ProbabilidadesNormalizadas = {
	local: number;
	empate: number;
	visitante: number;
	/** Resultado que se predice. Manda el motor si lo trae el JSON. */
	favorito: Resultado;
	/**
	 * Barras que se resaltan al final de la escena.
	 *
	 * Normalmente es solo la del resultado predicho. Pero cuando el motor llama
	 * empate a un partido igualadisimo (38/24/38), la barra de empate es la MAS
	 * CORTA de las tres: resaltarla parece un fallo de calculo. En ese caso se
	 * resaltan los dos equipos, que es lo que de verdad dice el dato — no hay
	 * forma de separarlos.
	 */
	resaltadas: Resultado[];
	/** Probabilidad mas alta de las tres, ya normalizada. */
	maxProb: number;
};

/**
 * Un motor de predicciones real no siempre devuelve probabilidades que sumen
 * exactamente 1 (0.41 + 0.24 + 0.34 = 0.99). Si pintaramos los valores en
 * bruto, las barras quedarian descuadradas. Se normalizan siempre.
 */
export const normalizarProbabilidades = (
	partido: Partido,
): ProbabilidadesNormalizadas => {
	const suma = partido.probLocal + partido.probEmpate + partido.probVisitante;
	const divisor = suma > 0 ? suma : 1;

	const local = partido.probLocal / divisor;
	const empate = partido.probEmpate / divisor;
	const visitante = partido.probVisitante / divisor;

	const maxProb = Math.max(local, empate, visitante);

	// Manda el motor de predicciones si ha dicho algo. Solo se deduce por
	// nuestra cuenta cuando el JSON no lo trae (jornadas escritas a mano).
	const favorito: Resultado =
		partido.resultadoPredicho ??
		(maxProb === local ? 'local' : maxProb === empate ? 'empate' : 'visitante');

	const resaltadas: Resultado[] =
		favorito === 'empate' && empate < maxProb
			? ['local', 'visitante']
			: [favorito];

	return {local, empate, visitante, favorito, resaltadas, maxProb};
};

/** Formatea 0.412 como "41". El simbolo de % se pinta aparte, mas pequeno. */
export const porcentaje = (valor: number): string =>
	String(Math.round(valor * 100));

/**
 * Etiqueta editorial derivada de lo claro que esta el partido.
 * Da un remate al bloque y evita que los ultimos segundos queden muertos.
 */
export const veredicto = (maxProb: number): string => {
	if (maxProb >= 0.55) return 'SIN SORPRESAS';
	if (maxProb >= 0.45) return 'FAVORITO CLARO';
	if (maxProb >= 0.38) return 'PARTIDO ABIERTO';
	return 'MONEDA AL AIRE';
};
