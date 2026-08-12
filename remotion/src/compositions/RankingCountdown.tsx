import React from 'react';
import {AbsoluteFill, Series, useCurrentFrame, useVideoConfig} from 'remotion';
import {z} from 'zod';
import {AnimatedCounter} from '../components/AnimatedCounter';
import {MovingBackdrop} from '../components/MovingBackdrop';
import {SfxCue} from '../components/SfxCue';
import {muelle, muelleFirme} from '../lib/animacion';
import {readableOn, rgba} from '../lib/color';
import {
	COLORS,
	DISPLAY_FONT,
	INTERLINEADO_DISPLAY,
	SAFE,
	TEXT_FONT,
} from '../theme';
import {rankingEntradaSchema, type RankingEntrada} from '../types';

export const rankingCountdownSchema = z.object({
	ranking: z.array(rankingEntradaSchema).min(1),
	/**
	 * Titulo de la cuenta atras. Por defecto no nombra ninguna competicion:
	 * la restriccion de marca del canal es no usar identidad UEFA/Champions.
	 */
	titulo: z.string().min(1),
	/**
	 * El sello del numero 1 cae en la ultima franja de la zona segura, donde van
	 * los subtitulos. El `Short` lo apaga cuando hay `captions.json`.
	 */
	mostrarSello: z.boolean().optional(),
	/**
	 * Orden de aparicion. Por defecto `true`: sale primero el lider y se remata
	 * en el ultimo de los cinco, que es donde esta la incertidumbre con la
	 * pregunta que usa el canal. Ponlo a `false` para la cuenta atras clasica
	 * 5-4-3-2-1, que es lo que quiere una pregunta cuya duda esta arriba.
	 */
	liderPrimero: z.boolean().optional(),
	/**
	 * Rotulo junto al porcentaje: dice QUE mide ese numero.
	 *
	 * Estaba escrito a fuego como "Opciones de titulo", que dejo de ser cierto
	 * en cuanto el countdown pudo preguntar otra cosa: se veia "Quien juega la
	 * Champions" arriba y "Opciones de titulo" abajo, en la misma pantalla.
	 * Por defecto sigue siendo el titulo, que es lo que era.
	 */
	etiquetaProbabilidad: z.string().optional(),
});

export type RankingCountdownProps = z.infer<typeof rankingCountdownSchema>;

export const RANKING = {
	/** Cartel de entrada. */
	intro: 36,
	/** Cada puesto menos el ultimo que se enseña. */
	puesto: 58,
	/**
	 * El ultimo que sale respira casi el doble: es el remate del video.
	 *
	 * "El ultimo que sale" y "el primero de la tabla" dejaron de ser lo mismo
	 * cuando el orden se invirtio — ver `liderPrimero` mas abajo. La duracion
	 * larga sigue al climax, no al numero 1.
	 */
	remate: 104,
	cuantos: 5,
} as const;

export const duracionRankingCountdown = (entradas: number): number => {
	const total = Math.min(Math.max(entradas, 1), RANKING.cuantos);
	return RANKING.intro + (total - 1) * RANKING.puesto + RANKING.remate;
};

// --------------------------------------------------------------------------

const Cabecera: React.FC<{titulo: string; encendidos: number; total: number}> = ({
	titulo,
	encendidos,
	total,
}) => (
	<div style={{display: 'flex', flexDirection: 'column', gap: 18}}>
		<div
			style={{
				fontFamily: TEXT_FONT,
				fontWeight: 700,
				fontSize: 32,
				letterSpacing: 7,
				textTransform: 'uppercase',
				color: COLORS.inkMuted,
			}}
		>
			{titulo}
		</div>
		<div style={{display: 'flex', gap: 10}}>
			{Array.from({length: total}, (_, i) => (
				<div
					key={i}
					style={{
						width: 54,
						height: 7,
						backgroundColor:
							i < encendidos ? COLORS.accent : rgba(COLORS.ink, 0.18),
					}}
				/>
			))}
		</div>
	</div>
);

const Intro: React.FC<{titulo: string}> = ({titulo}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();
	const entrada = muelle(frame, fps, {desde: 0, duracion: 18});

	return (
		<AbsoluteFill>
			<MovingBackdrop colores={[COLORS.accent, COLORS.draw]} />
			<AbsoluteFill
				style={{
					paddingTop: SAFE.top,
					paddingBottom: SAFE.bottom,
					paddingLeft: SAFE.side,
					paddingRight: SAFE.side,
					display: 'flex',
					flexDirection: 'column',
					justifyContent: 'center',
				}}
			>
				<div
					style={{
						fontFamily: DISPLAY_FONT,
						fontSize: 140,
						lineHeight: INTERLINEADO_DISPLAY,
						letterSpacing: -3,
						textTransform: 'uppercase',
						color: COLORS.ink,
						transform: `scale(${0.8 + entrada * 0.2})`,
						transformOrigin: 'left center',
						opacity: entrada,
					}}
				>
					{titulo}
				</div>
				<div
					style={{
						marginTop: 26,
						fontFamily: TEXT_FONT,
						fontWeight: 700,
						fontSize: 46,
						letterSpacing: 8,
						textTransform: 'uppercase',
						color: COLORS.accent,
						opacity: entrada,
					}}
				>
					Top 5 · cuenta atrás
				</div>
			</AbsoluteFill>
			<SfxCue sfx="whoosh" en={0} />
		</AbsoluteFill>
	);
};

const Puesto: React.FC<{
	entrada: RankingEntrada;
	posicion: number;
	total: number;
	titulo: string;
	/** Probabilidad del lider, para dimensionar la barra relativa. */
	maxProb: number;
	mostrarSello: boolean;
	/** Ultimo que se enseña: lleva la franja larga y el remate sonoro. */
	esRemate: boolean;
	/** Frames de esta franja, para colocar el sello dentro de ella. */
	duracion: number;
	/** Que mide el porcentaje. Ver `etiquetaProbabilidad`. */
	etiquetaProb: string;
}> = ({
	entrada,
	posicion,
	total,
	titulo,
	maxProb,
	mostrarSello,
	esRemate,
	duracion,
	etiquetaProb,
}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();

	// Dos cosas distintas que antes eran la misma. `esUno` es identidad —el
	// lider va en color de acento y lleva sello— y `esRemate` es ritmo: quien
	// cierra el bloque respira mas. Con la cuenta atras clasica coinciden; con
	// el orden invertido no, y confundirlos deja al lider con el sello cayendo
	// justo en el corte.
	const esUno = posicion === 1;

	const color = readableOn(entrada.colorPrimario, COLORS.bg, 3.2);

	const numeroDentro = muelle(frame, fps, {desde: 0, duracion: 14});
	const nombreDentro = muelleFirme(frame, fps, {desde: 8, duracion: 14});
	const inicioContador = esRemate ? 16 : 14;
	const duracionContador = esRemate ? 40 : 30;
	const barra = muelleFirme(frame, fps, {
		desde: inicioContador,
		duracion: duracionContador,
	});

	// El sello entra pasada media franja, sea cual sea su duracion. Estaba
	// clavado en el frame 58, que era media franja larga — y con el lider en
	// una franja corta habria aparecido en el ultimo frame, o sea nunca.
	const frameSello = Math.round(duracion * 0.55);
	const sello = esUno ? muelle(frame, fps, {desde: frameSello, duracion: 20}) : 0;
	const inicioPulso = frameSello + 28;
	const pulso =
		esUno && esRemate
			? 1 +
				0.04 *
					Math.max(0, Math.sin((frame - inicioPulso) / 3.2)) *
					(frame > inicioPulso ? 1 : 0)
			: 1;

	return (
		<AbsoluteFill>
			<MovingBackdrop colores={[entrada.colorPrimario]} />
			<AbsoluteFill
				style={{
					paddingTop: SAFE.top,
					paddingBottom: SAFE.bottom,
					paddingLeft: SAFE.side,
					paddingRight: SAFE.side,
					display: 'flex',
					flexDirection: 'column',
					justifyContent: 'space-between',
				}}
			>
				<Cabecera
					titulo={titulo}
					encendidos={total - posicion + 1}
					total={total}
				/>

				{/* Numero de puesto ------------------------------------------- */}
				<div
					style={{
						display: 'flex',
						alignItems: 'flex-start',
						gap: 14,
						transform: `scale(${0.55 + numeroDentro * 0.45}) rotate(${(1 - numeroDentro) * -6}deg)`,
						transformOrigin: 'left center',
						opacity: Math.min(1, numeroDentro * 2),
					}}
				>
					<span
						style={{
							fontFamily: TEXT_FONT,
							fontWeight: 700,
							fontSize: 72,
							lineHeight: 1.1,
							color: COLORS.inkMuted,
						}}
					>
						Nº
					</span>
					<span
						style={{
							fontFamily: DISPLAY_FONT,
							fontSize: 400,
							lineHeight: 0.78,
							color: esUno ? COLORS.accent : color,
						}}
					>
						{posicion}
					</span>
				</div>

				{/* Equipo ------------------------------------------------------- */}
				<div style={{display: 'flex', flexDirection: 'column', gap: 16}}>
					<div
						style={{
							height: 12,
							width: `${nombreDentro * 100}%`,
							backgroundColor: color,
						}}
					/>
					<div
						style={{
							fontFamily: DISPLAY_FONT,
							fontSize: entrada.equipo.length > 12 ? 96 : 118,
							lineHeight: 1,
							letterSpacing: -2,
							textTransform: 'uppercase',
							color: COLORS.ink,
							// Barrido: el nombre se descubre de izquierda a derecha.
							clipPath: `inset(0 ${(1 - nombreDentro) * 100}% 0 0)`,
						}}
					>
						{entrada.equipo}
					</div>
				</div>

				{/* Probabilidad -------------------------------------------------- */}
				<div style={{display: 'flex', flexDirection: 'column', gap: 20}}>
					<div
						style={{
							display: 'flex',
							alignItems: 'baseline',
							justifyContent: 'space-between',
						}}
					>
						<span
							style={{
								fontFamily: TEXT_FONT,
								fontWeight: 700,
								fontSize: 40,
								letterSpacing: 5,
								textTransform: 'uppercase',
								color: COLORS.inkMuted,
							}}
						>
							{etiquetaProb}
						</span>
						<AnimatedCounter
							valor={entrada.probTitulo * 100}
							desde={inicioContador}
							duracion={duracionContador}
							sufijo="%"
							style={{
								fontFamily: DISPLAY_FONT,
								fontSize: 210,
								lineHeight: 0.9,
								color: esUno ? COLORS.accent : COLORS.ink,
								transform: `scale(${pulso})`,
								transformOrigin: 'right bottom',
								display: 'inline-block',
							}}
						/>
					</div>

					<div
						style={{
							height: 14,
							backgroundColor: rgba(COLORS.ink, 0.12),
						}}
					>
						<div
							style={{
								height: '100%',
								width: `${(maxProb > 0 ? entrada.probTitulo / maxProb : 0) * barra * 100}%`,
								backgroundColor: esUno ? COLORS.accent : color,
							}}
						/>
					</div>

					{esUno && mostrarSello ? (
						<div
							style={{
								alignSelf: 'flex-start',
								marginTop: 8,
								fontFamily: TEXT_FONT,
								fontWeight: 700,
								fontSize: 42,
								letterSpacing: 6,
								textTransform: 'uppercase',
								color: '#08080C',
								backgroundColor: COLORS.accent,
								padding: '10px 28px 6px',
								transform: `scale(${0.6 + sello * 0.4}) rotate(-2deg)`,
								opacity: Math.min(1, sello * 2),
							}}
						>
							El favorito
						</div>
					) : null}
				</div>
			</AbsoluteFill>

			<SfxCue sfx="whoosh" en={0} />
			{esUno ? <SfxCue sfx="ding" en={frameSello} /> : null}
		</AbsoluteFill>
	);
};

// --------------------------------------------------------------------------

/**
 * Los cinco equipos con mas opciones, uno por franja.
 *
 * Por defecto va del mas probable al menos probable y remata en el quinto —
 * ver `liderPrimero`. Cada puesto entra con un corte seco (`Series` sin
 * transiciones), el porcentaje sube con contador animado y el ultimo que sale
 * se queda casi el doble de tiempo en pantalla.
 */
export const RankingCountdown: React.FC<RankingCountdownProps> = ({
	ranking,
	titulo,
	mostrarSello = true,
	liderPrimero = true,
	etiquetaProbabilidad = 'Opciones de título',
}) => {
	// Se ordena aqui en vez de fiarse del orden del JSON: la composicion no
	// deberia romperse porque el motor de predicciones escriba en otro orden.
	const ordenado = [...ranking]
		.sort((a, b) => b.probTitulo - a.probTitulo)
		.slice(0, RANKING.cuantos);

	const lider = ordenado[0];
	const maxProb = lider ? lider.probTitulo : 1;

	// Del mas obvio al menos obvio: 1, 2, 3, 4, 5.
	//
	// Al reves de lo que pide el instinto, y a proposito. Con la pregunta que
	// usa el canal —quien entra en plazas de Champions— los dos primeros estan
	// al 100% y al 99,8%: rematar ahi es rematar en el dato mas previsible del
	// video. Enseñandolos primero, el que se queda en pantalla al final es el
	// que de verdad esta en juego (Betis al 31,6%).
	//
	// `liderPrimero=false` recupera la cuenta atras clasica 5-4-3-2-1, que es
	// la que quiere una pregunta con la incertidumbre arriba.
	const secuencia = liderPrimero ? ordenado : [...ordenado].reverse();

	return (
		<AbsoluteFill style={{backgroundColor: COLORS.bg}}>
			<Series>
				<Series.Sequence durationInFrames={RANKING.intro} name="Intro">
					<Intro titulo={titulo} />
				</Series.Sequence>

				{secuencia.map((entrada, i) => {
					// El numero que se pinta es el puesto en la tabla, no el
					// orden de aparicion: el lider es el 1 salga cuando salga.
					const posicion = liderPrimero ? i + 1 : secuencia.length - i;
					const esElRemate = i === secuencia.length - 1;
					const duracion = esElRemate ? RANKING.remate : RANKING.puesto;
					return (
						<Series.Sequence
							key={`${entrada.equipo}-${posicion}`}
							durationInFrames={duracion}
							name={`Nº${posicion} · ${entrada.equipo}`}
						>
							<Puesto
								entrada={entrada}
								posicion={posicion}
								total={secuencia.length}
								titulo={titulo}
								maxProb={maxProb}
								mostrarSello={mostrarSello}
								esRemate={esElRemate}
								duracion={duracion}
								etiquetaProb={etiquetaProbabilidad}
							/>
						</Series.Sequence>
					);
				})}
			</Series>
		</AbsoluteFill>
	);
};
