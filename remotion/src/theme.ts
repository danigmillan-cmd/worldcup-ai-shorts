import {loadFont as loadAnton} from '@remotion/google-fonts/Anton';
import {loadFont as loadBarlowCondensed} from '@remotion/google-fonts/BarlowCondensed';

/**
 * Las fuentes se cargan via `@remotion/google-fonts`: es un paquete npm, asi que
 * el render es identico en Windows y en Ubuntu headless sin depender de fuentes
 * instaladas en el sistema.
 */
const anton = loadAnton();
const barlow = loadBarlowCondensed('normal', {
	weights: ['600', '700'],
	subsets: ['latin'],
});

/** Titulares y numeros grandes: condensada, pesada, sin alternativas de peso. */
export const DISPLAY_FONT = anton.fontFamily;
/** Etiquetas, datos y texto secundario. */
export const TEXT_FONT = barlow.fontFamily;

export const VIDEO = {
	width: 1080,
	height: 1920,
	fps: 30,
} as const;

/**
 * La UI de YouTube Shorts tapa el 10% superior y el 18% inferior.
 * Ningun texto ni dato critico puede caer en esas bandas.
 */
export const SAFE = {
	top: Math.round(VIDEO.height * 0.1), // 192px
	bottom: Math.round(VIDEO.height * 0.18), // 346px
	side: 72,
} as const;

export const SAFE_HEIGHT = VIDEO.height - SAFE.top - SAFE.bottom; // 1382px
export const SAFE_WIDTH = VIDEO.width - SAFE.side * 2; // 936px

export const COLORS = {
	bg: '#07070B',
	surface: '#12121B',
	ink: '#FFFFFF',
	inkMuted: '#9A9AB4',
	/** Color del empate: deliberadamente neutro, nunca compite con los equipos. */
	draw: '#5C5F70',
	accent: '#D7FF3E',
} as const;

/** Ritmo: nunca mas de 45 frames (1,5s) sin un cambio visual fuerte. */
export const MAX_STATIC_FRAMES = 45;

/**
 * Interlineado minimo para texto de display en varias lineas.
 *
 * Anton no reserva hueco para las tildes de las mayusculas: con `lineHeight`
 * por debajo de esto, la Í de "TÍTULO" o la Ú de "ÚLTIMAS" en la segunda linea
 * invaden el renglon de arriba. En castellano eso pasa constantemente, asi que
 * cualquier texto que pueda partirse en dos lineas usa esta constante.
 */
export const INTERLINEADO_DISPLAY = 1.12;
