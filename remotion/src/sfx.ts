import {archivoPublico} from './lib/publico';

/**
 * Efectos de sonido del proyecto.
 *
 * Las rutas son relativas a `public/`. Los archivos NO estan en el repo: hay
 * que ponerlos a mano (ver `public/sfx/README.md`). Nada de descargar audio de
 * ningun sitio ni de usar musica con copyright.
 */
export const SFX = {
	/** Transicion entre bloques. Corto y seco, 200-400 ms. */
	whoosh: 'sfx/whoosh.mp3',
	/** Confirmacion: cifra que se asienta, puesto que se revela. */
	ding: 'sfx/ding.mp3',
	/** Caida de tono para el dato negativo o el cierre. */
	bajon: 'sfx/bajon.mp3',
} as const;

export type NombreSfx = keyof typeof SFX;

/** Ruta del efecto, o `null` si el mp3 no esta en `public/sfx/`. */
export const rutaSfx = (nombre: NombreSfx): string | null =>
	archivoPublico(SFX[nombre]);
