import {distanciaColor, mix, readableOn} from './color';
import type {Partido} from '../types';

/**
 * Por debajo de esta distancia, dos colores de equipo se leen como el mismo en
 * un grafico de barras. Calibrado con los choques reales de la competicion:
 * Liverpool-Bayern (~40) y Milan-Liverpool (~101) hay que separarlos;
 * Arsenal-Barcelona (~153) se distingue bien y se deja como esta.
 */
export const UMBRAL_COLISION = 120;

/** Contraste minimo de una barra contra el fondo oscuro. */
const CONTRASTE_FONDO = 3.2;

export type ColoresPartido = {
	/** Color de identidad, para el bloque del chip. Admite tonos oscuros. */
	localBase: string;
	visitanteBase: string;
	/** El mismo color corregido para leerse sobre el fondo, para la barra. */
	localBarra: string;
	visitanteBarra: string;
	/**
	 * `true` si al visitante se le ha cambiado el color por choque con el local.
	 * Util para depurar en el Studio y para avisar en el generador.
	 */
	visitanteAjustado: boolean;
};

/**
 * Elige colores distinguibles para los dos equipos de un partido.
 *
 * Mas de veinte de los clubes que pasan por la fase liga tienen el rojo como
 * color primario, asi que un Liverpool-Bayern o un Milan-Atletico es cuestion
 * de tiempo. Con los primarios en bruto salen dos barras del mismo rojo y el
 * grafico deja de leerse: `readableOn` solo arregla el contraste contra el
 * fondo, no entre los dos equipos.
 *
 * Orden de preferencia:
 *   1. Los dos primarios, si ya se distinguen.
 *   2. El secundario del visitante, que para esto esta en el JSON.
 *   3. Aclarar el primario del visitante hasta separarlo (mismo tono, otra
 *      intensidad). Feo, pero legible, y nunca deja dos barras iguales.
 *
 * El color resultante se aplica al equipo entero dentro de ese partido (chip y
 * barra), no solo a la barra: media pantalla en rojo y la otra media en azul
 * para el mismo equipo seria peor que el problema original.
 */
export const resolverColoresPartido = (
	partido: Partido,
	fondo: string,
): ColoresPartido => {
	const localBase = partido.local.colorPrimario;
	const localBarra = readableOn(localBase, fondo, CONTRASTE_FONDO);

	const candidatos = [
		partido.visitante.colorPrimario,
		partido.visitante.colorSecundario,
	];

	for (const candidato of candidatos) {
		const barra = readableOn(candidato, fondo, CONTRASTE_FONDO);
		if (distanciaColor(localBarra, barra) >= UMBRAL_COLISION) {
			return {
				localBase,
				localBarra,
				visitanteBase: candidato,
				visitanteBarra: barra,
				visitanteAjustado: candidato !== partido.visitante.colorPrimario,
			};
		}
	}

	// Ni el primario ni el secundario sirven (p. ej. rojo y negro sobre fondo
	// negro). Se aclara el primario paso a paso hasta que se separe.
	for (let paso = 1; paso <= 10; paso++) {
		const aclarado = mix(partido.visitante.colorPrimario, '#FFFFFF', paso / 10);
		const barra = readableOn(aclarado, fondo, CONTRASTE_FONDO);
		if (distanciaColor(localBarra, barra) >= UMBRAL_COLISION) {
			return {
				localBase,
				localBarra,
				visitanteBase: aclarado,
				visitanteBarra: barra,
				visitanteAjustado: true,
			};
		}
	}

	return {
		localBase,
		localBarra,
		visitanteBase: '#FFFFFF',
		visitanteBarra: '#FFFFFF',
		visitanteAjustado: true,
	};
};
