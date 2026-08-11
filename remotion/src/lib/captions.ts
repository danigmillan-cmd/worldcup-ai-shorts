import {
	createTikTokStyleCaptions,
	type Caption,
	type TikTokPage,
} from '@remotion/captions';
import type {PalabraCaption} from '../types';

/**
 * Adaptador del formato del pipeline (`captions.json`) al tipo `Caption` de
 * `@remotion/captions`.
 *
 * Se pasa por el tipo estandar en vez de inventarse uno propio para que el dia
 * que el timing venga de Whisper en lugar de edge-tts, encaje sin tocar el
 * componente.
 *
 * Ojo con el espacio inicial: `createTikTokStyleCaptions` usa " " al principio
 * del token como senal de separacion entre palabras y para decidir donde puede
 * cortar una pagina. Sin el, todo el texto acaba en una sola pagina infinita.
 */
export const aCaptions = (palabras: readonly PalabraCaption[]): Caption[] =>
	palabras.map((p, i) => ({
		text: i === 0 ? p.palabra : ` ${p.palabra}`,
		startMs: p.inicioMs,
		endMs: p.finMs,
		timestampMs: (p.inicioMs + p.finMs) / 2,
		confidence: null,
	}));

/**
 * Plan B cuando no hay `captions.json`: reparte el texto uniformemente sobre la
 * duracion disponible. No cuadra con la voz, pero el render no se rompe, que es
 * de lo que se trata.
 */
export const repartirUniforme = (
	texto: string,
	duracionMs: number,
): Caption[] => {
	const palabras = texto.trim().split(/\s+/).filter(Boolean);
	if (palabras.length === 0) {
		return [];
	}
	const porPalabra = duracionMs / palabras.length;

	return palabras.map((palabra, i) => ({
		text: i === 0 ? palabra : ` ${palabra}`,
		startMs: i * porPalabra,
		endMs: (i + 1) * porPalabra,
		timestampMs: (i + 0.5) * porPalabra,
		confidence: null,
	}));
};

export const construirPaginas = ({
	captions,
	texto,
	duracionMs,
	agruparMs,
}: {
	captions?: readonly PalabraCaption[] | null;
	texto?: string;
	duracionMs: number;
	agruparMs: number;
}): TikTokPage[] => {
	const base =
		captions && captions.length > 0
			? aCaptions(captions)
			: repartirUniforme(texto ?? '', duracionMs);

	if (base.length === 0) {
		return [];
	}

	return createTikTokStyleCaptions({
		captions: base,
		combineTokensWithinMilliseconds: agruparMs,
	}).pages;
};
