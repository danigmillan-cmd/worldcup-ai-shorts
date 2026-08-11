import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {rgba} from '../lib/color';
import {COLORS, SAFE} from '../theme';

type Props = {
	color?: string;
	altura?: number;
	/**
	 * Posicion vertical. Por defecto justo encima de la zona segura, NO en
	 * `y = 0`: los primeros ~190px los tapa la cabecera de YouTube Shorts y la
	 * barra no se veria.
	 */
	y?: number;
};

/**
 * Barra fina que avanza durante todo el video.
 *
 * IMPORTANTE: usa `useCurrentFrame()`, que dentro de un `<Sequence>` es
 * relativo a esa secuencia. Tiene que montarse en la raiz de la composicion,
 * fuera de cualquier secuencia, o medira el progreso del bloque en vez del
 * progreso del Short.
 */
export const ProgressBar: React.FC<Props> = ({
	color = COLORS.accent,
	altura = 7,
	y = SAFE.top - 26,
}) => {
	const frame = useCurrentFrame();
	const {durationInFrames} = useVideoConfig();

	const progreso = Math.min(1, frame / Math.max(1, durationInFrames - 1));

	return (
		<div
			style={{
				position: 'absolute',
				left: SAFE.side,
				right: SAFE.side,
				top: y,
				height: altura,
				backgroundColor: rgba(COLORS.ink, 0.16),
			}}
		>
			<div
				style={{
					width: `${progreso * 100}%`,
					height: '100%',
					backgroundColor: color,
				}}
			/>
		</div>
	);
};
