/**
 * Utilidades de color.
 *
 * Los colores vienen del JSON, asi que pueden ser cualquier cosa: el negro del
 * Inter, el granate del Barcelona o el amarillo del Madrid. Sobre fondo oscuro
 * unos se leen y otros desaparecen. Estas funciones garantizan contraste
 * suficiente sin que haya que tocar el JSON.
 */

export type Rgb = {r: number; g: number; b: number};

const FALLBACK: Rgb = {r: 255, g: 255, b: 255};

export const hexToRgb = (hex: string): Rgb => {
	const match = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim());
	if (!match) {
		return FALLBACK;
	}
	const body = match[1] as string;
	const full =
		body.length === 3
			? body
					.split('')
					.map((c) => c + c)
					.join('')
			: body;
	return {
		r: parseInt(full.slice(0, 2), 16),
		g: parseInt(full.slice(2, 4), 16),
		b: parseInt(full.slice(4, 6), 16),
	};
};

export const rgbToHex = ({r, g, b}: Rgb): string => {
	const part = (v: number) =>
		Math.round(Math.min(255, Math.max(0, v)))
			.toString(16)
			.padStart(2, '0');
	return `#${part(r)}${part(g)}${part(b)}`;
};

export const rgba = (hex: string, alpha: number): string => {
	const {r, g, b} = hexToRgb(hex);
	return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

/** Luminancia relativa segun WCAG 2.1. */
export const relativeLuminance = (hex: string): number => {
	const {r, g, b} = hexToRgb(hex);
	const channel = (v: number) => {
		const s = v / 255;
		return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
	};
	return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
};

/** Ratio de contraste WCAG entre dos colores (1 = identicos, 21 = maximo). */
export const contrastRatio = (a: string, b: string): number => {
	const la = relativeLuminance(a);
	const lb = relativeLuminance(b);
	const [light, dark] = la > lb ? [la, lb] : [lb, la];
	return ((light as number) + 0.05) / ((dark as number) + 0.05);
};

/** Mezcla lineal entre dos colores. `amount` 0 = a, 1 = b. */
export const mix = (a: string, b: string, amount: number): string => {
	const ca = hexToRgb(a);
	const cb = hexToRgb(b);
	const t = Math.min(1, Math.max(0, amount));
	return rgbToHex({
		r: ca.r + (cb.r - ca.r) * t,
		g: ca.g + (cb.g - ca.g) * t,
		b: ca.b + (cb.b - ca.b) * t,
	});
};

/**
 * Distancia perceptual aproximada entre dos colores (formula "redmean").
 *
 * OJO: para saber si dos equipos se distinguen entre si NO vale
 * `contrastRatio`. El contraste WCAG solo mide luminancia, asi que un rojo y un
 * verde del mismo brillo dan ratio 1,0 (identicos segun WCAG) siendo
 * perfectisimamente distinguibles. Y al reves. Para "estos dos colores se
 * parecen demasiado" hace falta distancia de color, no contraste.
 *
 * Escala orientativa: Liverpool vs Bayern ~40, Milan vs Liverpool ~101,
 * Arsenal vs Barcelona ~153, Real Madrid vs Bayern ~377.
 */
export const distanciaColor = (a: string, b: string): number => {
	const ca = hexToRgb(a);
	const cb = hexToRgb(b);
	const dr = ca.r - cb.r;
	const dg = ca.g - cb.g;
	const db = ca.b - cb.b;
	const rMedia = (ca.r + cb.r) / 2;

	return Math.sqrt(
		(2 + rMedia / 256) * dr * dr +
			4 * dg * dg +
			(2 + (255 - rMedia) / 256) * db * db,
	);
};

/** Devuelve negro o blanco, el que mas contraste tenga sobre `bg`. */
export const textOn = (bg: string): string =>
	relativeLuminance(bg) > 0.42 ? '#08080C' : '#FFFFFF';

/**
 * Aclara (o oscurece) `color` lo justo para que se lea sobre `bg`.
 * Sin esto, el azul marino del Inter sobre el fondo negro es invisible.
 */
export const readableOn = (
	color: string,
	bg: string,
	minRatio = 4.5,
): string => {
	if (contrastRatio(color, bg) >= minRatio) {
		return color;
	}
	const target = relativeLuminance(bg) > 0.42 ? '#000000' : '#FFFFFF';
	let candidate = color;
	for (let step = 1; step <= 20; step++) {
		candidate = mix(color, target, step / 20);
		if (contrastRatio(candidate, bg) >= minRatio) {
			return candidate;
		}
	}
	return target;
};
