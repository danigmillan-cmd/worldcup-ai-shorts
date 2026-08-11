import {spring} from 'remotion';

type Opciones = {
	/** Frame absoluto en el que arranca la animacion. */
	desde: number;
	/** Duracion de la animacion en frames. */
	duracion: number;
};

/**
 * Muelle con rebote. Para entradas, escalas y todo lo que gane con un golpe
 * de energia. Regla del proyecto: nada de interpolaciones lineales.
 */
export const muelle = (
	frame: number,
	fps: number,
	{desde, duracion}: Opciones,
): number =>
	spring({
		frame: frame - desde,
		fps,
		durationInFrames: duracion,
		config: {damping: 13, mass: 0.9, stiffness: 130},
	});

/**
 * Muelle sin rebote (`overshootClamping`). Obligatorio para contadores y
 * barras: un muelle normal haria que un 41% mostrase 46% antes de asentarse,
 * y en un numero eso no parece animacion, parece un bug.
 */
export const muelleFirme = (
	frame: number,
	fps: number,
	{desde, duracion}: Opciones,
): number =>
	spring({
		frame: frame - desde,
		fps,
		durationInFrames: duracion,
		config: {damping: 200, mass: 0.6, stiffness: 100, overshootClamping: true},
	});

/**
 * Sacudida que se apaga sola. Se usa en el impacto del sello del marcador
 * para que el corte tenga peso.
 */
export const impacto = (
	frame: number,
	desde: number,
	amplitud = 14,
	duracion = 16,
): number => {
	const t = frame - desde;
	if (t < 0 || t > duracion) return 0;
	const decaimiento = 1 - t / duracion;
	return Math.sin(t * 1.2) * amplitud * decaimiento * decaimiento;
};
