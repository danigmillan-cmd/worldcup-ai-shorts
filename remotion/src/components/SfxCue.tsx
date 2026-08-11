import React from 'react';
import {Audio, Sequence} from 'remotion';
import {rutaSfx, type NombreSfx} from '../sfx';

type Props = {
	sfx: NombreSfx;
	/** Frame, relativo al contenedor, en el que suena. */
	en: number;
	volumen?: number;
};

/**
 * Coloca un efecto de sonido en un frame concreto.
 *
 * Si el mp3 no esta en `public/sfx/`, no renderiza nada: los cues se pueden
 * dejar puestos en las composiciones desde el primer dia y el video sale mudo
 * hasta que se aporten los archivos.
 */
export const SfxCue: React.FC<Props> = ({sfx, en, volumen = 1}) => {
	const src = rutaSfx(sfx);
	if (!src) {
		return null;
	}

	return (
		<Sequence from={Math.max(0, Math.round(en))} name={`sfx · ${sfx}`} layout="none">
			<Audio src={src} volume={volumen} />
		</Sequence>
	);
};
