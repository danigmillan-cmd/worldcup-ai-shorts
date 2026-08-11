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
});

export type RankingCountdownProps = z.infer<typeof rankingCountdownSchema>;

export const RANKING = {
	/** Cartel de entrada. */
	intro: 36,
	/** Puestos del 5 al 2. */
	puesto: 58,
	/** El numero 1 respira mas: es el remate del video. */
	puestoUno: 104,
	cuantos: 5,
} as const;

export const duracionRankingCountdown = (entradas: number): number => {
	const total = Math.min(Math.max(entradas, 1), RANKING.cuantos);
	return RANKING.intro + (total - 1) * RANKING.puesto + RANKING.puestoUno;
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
}> = ({entrada, posicion, total, titulo, maxProb, mostrarSello}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();
	const esUno = posicion === 1;

	const color = readableOn(entrada.colorPrimario, COLORS.bg, 3.2);

	const numeroDentro = muelle(frame, fps, {desde: 0, duracion: 14});
	const nombreDentro = muelleFirme(frame, fps, {desde: 8, duracion: 14});
	const inicioContador = esUno ? 16 : 14;
	const duracionContador = esUno ? 40 : 30;
	const barra = muelleFirme(frame, fps, {
		desde: inicioContador,
		duracion: duracionContador,
	});

	// Solo para el numero 1: sello final y pulso, para que los ultimos 45
	// frames no se queden quietos.
	const sello = esUno ? muelle(frame, fps, {desde: 58, duracion: 20}) : 0;
	const pulso = esUno
		? 1 + 0.04 * Math.max(0, Math.sin((frame - 86) / 3.2)) * (frame > 86 ? 1 : 0)
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
							Opciones de título
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
			{esUno ? <SfxCue sfx="ding" en={58} /> : null}
		</AbsoluteFill>
	);
};

// --------------------------------------------------------------------------

/**
 * Cuenta atras del puesto 5 al 1 con los equipos con mas opciones de titulo.
 *
 * Cada puesto entra con un corte seco (`Series` sin transiciones), el
 * porcentaje sube con contador animado y el numero 1 se queda casi el doble de
 * tiempo en pantalla.
 */
export const RankingCountdown: React.FC<RankingCountdownProps> = ({
	ranking,
	titulo,
	mostrarSello = true,
}) => {
	// Se ordena aqui en vez de fiarse del orden del JSON: la composicion no
	// deberia romperse porque el motor de predicciones escriba en otro orden.
	const ordenado = [...ranking]
		.sort((a, b) => b.probTitulo - a.probTitulo)
		.slice(0, RANKING.cuantos);

	const lider = ordenado[0];
	const maxProb = lider ? lider.probTitulo : 1;

	// Del peor al mejor: la cuenta atras va 5, 4, 3, 2, 1.
	const cuentaAtras = [...ordenado].reverse();

	return (
		<AbsoluteFill style={{backgroundColor: COLORS.bg}}>
			<Series>
				<Series.Sequence durationInFrames={RANKING.intro} name="Intro">
					<Intro titulo={titulo} />
				</Series.Sequence>

				{cuentaAtras.map((entrada, i) => {
					const posicion = cuentaAtras.length - i;
					return (
						<Series.Sequence
							key={`${entrada.equipo}-${posicion}`}
							durationInFrames={
								posicion === 1 ? RANKING.puestoUno : RANKING.puesto
							}
							name={`Nº${posicion} · ${entrada.equipo}`}
						>
							<Puesto
								entrada={entrada}
								posicion={posicion}
								total={cuentaAtras.length}
								titulo={titulo}
								maxProb={maxProb}
								mostrarSello={mostrarSello}
							/>
						</Series.Sequence>
					);
				})}
			</Series>
		</AbsoluteFill>
	);
};
