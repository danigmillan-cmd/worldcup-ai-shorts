import type {TikTokPage} from '@remotion/captions';
import React, {useMemo} from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {muelleFirme} from '../lib/animacion';
import {construirPaginas} from '../lib/captions';
import {rgba} from '../lib/color';
import {COLORS, DISPLAY_FONT, INTERLINEADO_DISPLAY} from '../theme';
import type {PalabraCaption} from '../types';

type Props = {
	/** Timings reales del voiceover. Si faltan, se reparte `texto`. */
	captions?: readonly PalabraCaption[] | null;
	/** Texto de respaldo. Obligatorio si no hay `captions`. */
	texto?: string;
	tamano?: number;
	colorActivo?: string;
	colorInactivo?: string;
	/** Cuantos ms de palabras caben en una pagina antes de cortar. */
	agruparMs?: number;
	style?: React.CSSProperties;
};

const paginaActiva = (paginas: TikTokPage[], ms: number): TikTokPage | null => {
	if (paginas.length === 0) {
		return null;
	}
	for (const pagina of paginas) {
		if (ms >= pagina.startMs && ms < pagina.startMs + pagina.durationMs) {
			return pagina;
		}
	}
	// Margen corto al final para absorber el redondeo de frames. Pasado eso, los
	// subtitulos desaparecen: si el voiceover acaba antes que el video, dejar la
	// ultima pagina fija seria un subtitulo clavado durante medio Short.
	const ultima = paginas[paginas.length - 1];
	if (ultima && ms >= ultima.startMs && ms < ultima.startMs + ultima.durationMs + 400) {
		return ultima;
	}
	return null;
};

/**
 * Subtitulos palabra por palabra, centrados, estilo TikTok.
 *
 * La palabra activa cambia de color y da un pop de escala que se desinfla:
 * arranca a 1,22 y cae a 1 en unos 7 frames. Un muelle con rebote no vale aqui
 * porque se quedaria fijo en el tamano grande.
 */
export const WordCaptions: React.FC<Props> = ({
	captions,
	texto,
	tamano = 96,
	colorActivo = COLORS.accent,
	colorInactivo = COLORS.ink,
	agruparMs = 900,
	style,
}) => {
	const frame = useCurrentFrame();
	const {fps, durationInFrames} = useVideoConfig();
	const ms = (frame / fps) * 1000;

	const paginas = useMemo(
		() =>
			construirPaginas({
				captions,
				texto,
				duracionMs: (durationInFrames / fps) * 1000,
				agruparMs,
			}),
		[captions, texto, durationInFrames, fps, agruparMs],
	);

	const pagina = paginaActiva(paginas, ms);
	if (!pagina) {
		return null;
	}

	return (
		<div
			style={{
				display: 'flex',
				flexWrap: 'wrap',
				justifyContent: 'center',
				alignItems: 'center',
				gap: `${Math.round(tamano * 0.14)}px ${Math.round(tamano * 0.28)}px`,
				textAlign: 'center',
				...style,
			}}
		>
			{pagina.tokens.map((token, i) => {
				const activo = ms >= token.fromMs && ms < token.toMs;
				const pop = activo
					? 1 +
						0.22 *
							(1 -
								muelleFirme(frame, fps, {
									desde: (token.fromMs / 1000) * fps,
									duracion: 7,
								}))
					: 1;

				return (
					<span
						key={`${token.fromMs}-${i}`}
						style={{
							display: 'inline-block',
							fontFamily: DISPLAY_FONT,
							fontSize: tamano,
							lineHeight: INTERLINEADO_DISPLAY,
							letterSpacing: -1,
							textTransform: 'uppercase',
							color: activo ? colorActivo : colorInactivo,
							opacity: activo ? 1 : 0.55,
							transform: `scale(${pop})`,
							// Los subtitulos van sobre lo que sea: sombra dura para que
							// se lean igual sobre un bloque de color que sobre el fondo.
							textShadow: `0 6px 24px ${rgba('#000000', 0.85)}, 0 2px 4px ${rgba('#000000', 0.9)}`,
						}}
					>
						{token.text.trim()}
					</span>
				);
			})}
		</div>
	);
};
