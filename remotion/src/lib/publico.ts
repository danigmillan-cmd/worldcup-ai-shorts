import {getStaticFiles, staticFile} from 'remotion';

/**
 * Devuelve la URL de un archivo de `public/`, o `null` si no existe.
 *
 * `staticFile()` no comprueba nada: apuntar a un archivo que falta no da error
 * al escribirlo, da un error de red poco claro a mitad de render.
 * `getStaticFiles()` si conoce el contenido real de `public/`, asi que con esto
 * el proyecto renderiza en limpio aunque no haya ni voiceover ni efectos.
 */
export const archivoPublico = (
	relativa: string | null | undefined,
): string | null => {
	if (!relativa) {
		return null;
	}
	const limpia = relativa.replace(/^\/+/, '');
	const existe = getStaticFiles().some((archivo) => archivo.name === limpia);
	return existe ? staticFile(limpia) : null;
};
