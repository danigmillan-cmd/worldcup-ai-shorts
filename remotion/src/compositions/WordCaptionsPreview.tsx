import React from 'react';
import {AbsoluteFill} from 'remotion';
import {z} from 'zod';
import {MovingBackdrop} from '../components/MovingBackdrop';
import {ProgressBar} from '../components/ProgressBar';
import {WordCaptions} from '../components/WordCaptions';
import {COLORS, SAFE} from '../theme';
import {palabraCaptionSchema} from '../types';

/**
 * Banco de pruebas de `WordCaptions` y `ProgressBar`.
 *
 * No forma parte del Short: existe para poder revisar los subtitulos y la barra
 * de progreso por separado en el Studio. Pon `captions` a null para comprobar
 * el reparto uniforme cuando no hay `captions.json`.
 */
export const wordCaptionsPreviewSchema = z.object({
	captions: z.array(palabraCaptionSchema).nullable(),
	texto: z.string(),
});

export type WordCaptionsPreviewProps = z.infer<typeof wordCaptionsPreviewSchema>;

export const WordCaptionsPreview: React.FC<WordCaptionsPreviewProps> = ({
	captions,
	texto,
}) => {
	return (
		<AbsoluteFill>
			<MovingBackdrop colores={[COLORS.accent, '#DC052D']} />

			<AbsoluteFill
				style={{
					paddingTop: SAFE.top,
					paddingBottom: SAFE.bottom,
					paddingLeft: SAFE.side,
					paddingRight: SAFE.side,
					display: 'flex',
					alignItems: 'center',
					justifyContent: 'center',
				}}
			>
				<WordCaptions captions={captions} texto={texto} />
			</AbsoluteFill>

			<ProgressBar />
		</AbsoluteFill>
	);
};
