import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {z} from 'zod';
import {AnimatedCounter} from '../components/AnimatedCounter';
import {MovingBackdrop} from '../components/MovingBackdrop';
import {SfxCue} from '../components/SfxCue';
import {TeamChip} from '../components/TeamChip';
import {impacto, muelle, muelleFirme} from '../lib/animacion';
import {readableOn, rgba} from '../lib/color';
import {resolverColoresPartido} from '../lib/colores-equipo';
import {
	normalizarProbabilidades,
	veredicto,
	type Resultado,
} from '../lib/probabilidades';
import {
	COLORS,
	DISPLAY_FONT,
	INTERLINEADO_DISPLAY,
	SAFE,
	TEXT_FONT,
} from '../theme';
import {partidoSchema} from '../types';

export const matchProbabilitySchema = z.object({
	partido: partidoSchema,
	/** Posicion del partido dentro del Short, para el contador "2 / 4". */
	indice: z.number().int().min(1),
	total: z.number().int().min(1),
	/**
	 * La etiqueta de veredicto ocupa la ultima franja de la zona segura, que es
	 * justo donde se colocan los subtitulos. El `Short` la apaga cuando hay
	 * `captions.json` para que no se pisen.
	 */
	mostrarVeredicto: z.boolean().optional(),
});

export type MatchProbabilityProps = z.infer<typeof matchProbabilitySchema>;

/** 8 segundos. Cuatro partidos = 32s de cuerpo. */
export const MATCH_PROBABILITY_DURATION = 240;

/**
 * Guion de la escena, en frames.
 * Ningun hueco supera los 45 frames: siempre hay un corte o un cambio fuerte
 * antes de que la vista se acomode.
 */
const T = {
	titular: 0,
	enfrentamiento: 30,
	barras: 62,
	/** Separacion entre la entrada de una barra y la siguiente. */
	escalonBarra: 13,
	ganadora: 148,
	sello: 176,
	veredicto: 212,
} as const;

const ANCHO_ETIQUETA = 300;
const ANCHO_PORCENTAJE = 150;

const Barra: React.FC<{
	etiqueta: string;
	color: string;
	/** Probabilidad real, la que se canta en el porcentaje. */
	prob: number;
	/** Relleno relativo al favorito: el mas probable llena la barra entera. */
	relativa: number;
	progreso: number;
	/** Frame de arranque; el contador y el relleno comparten muelle. */
	desde: number;
	duracion: number;
	esGanadora: boolean;
	realce: number;
}> = ({
	etiqueta,
	color,
	prob,
	relativa,
	progreso,
	desde,
	duracion,
	esGanadora,
	realce,
}) => {
	// `color` llega ya resuelto por resolverColoresPartido: legible sobre el
	// fondo y distinguible del otro equipo.
	// Las perdedoras se apagan, pero no tanto como para dejar de leerse: el dato
	// sigue siendo parte del contenido.
	const atenuacion = esGanadora ? 1 : 1 - realce * 0.5;
	const escala = esGanadora ? 1 + realce * 0.05 : 1;

	return (
		<div
			style={{
				display: 'flex',
				alignItems: 'center',
				gap: 18,
				height: 104,
				opacity: progreso * atenuacion,
				transform: `scale(${escala})`,
				transformOrigin: 'left center',
			}}
		>
			<div
				style={{
					width: ANCHO_ETIQUETA,
					textAlign: 'right',
					fontFamily: TEXT_FONT,
					fontWeight: 700,
					fontSize: 40,
					lineHeight: 1,
					letterSpacing: 1,
					textTransform: 'uppercase',
					color: esGanadora ? COLORS.ink : COLORS.inkMuted,
					whiteSpace: 'nowrap',
					overflow: 'hidden',
					textOverflow: 'ellipsis',
				}}
			>
				{etiqueta}
			</div>

			<div
				style={{
					flex: 1,
					height: 78,
					position: 'relative',
					backgroundColor: rgba(COLORS.ink, 0.07),
					// El resalte va en el color de acento, no en blanco: cuando a un
					// equipo se le resuelve el color a su secundario y ese secundario
					// es blanco (le pasa a media competicion), un borde blanco
					// alrededor de una barra blanca no se distingue de nada. El lima
					// no lo usa ningun club.
					outline: esGanadora
						? `${Math.round(realce * 5)}px solid ${COLORS.accent}`
						: 'none',
					outlineOffset: 3,
				}}
			>
				<div
					style={{
						position: 'absolute',
						inset: 0,
						width: `${relativa * progreso * 100}%`,
						backgroundColor: color,
					}}
				/>
				{/* Destello que recorre la barra ganadora al resaltarse. */}
				{esGanadora && realce > 0 && realce < 1 ? (
					<div
						style={{
							position: 'absolute',
							top: 0,
							bottom: 0,
							left: `${realce * 100}%`,
							width: 90,
							background: `linear-gradient(90deg, ${rgba(COLORS.ink, 0)}, ${rgba(COLORS.ink, 0.55)}, ${rgba(COLORS.ink, 0)})`,
						}}
					/>
				) : null}
			</div>

			<div style={{width: ANCHO_PORCENTAJE, textAlign: 'right'}}>
				<AnimatedCounter
					valor={prob * 100}
					desde={desde}
					duracion={duracion}
					sufijo="%"
					style={{
						fontFamily: DISPLAY_FONT,
						fontSize: 66,
						lineHeight: 1,
						color: esGanadora ? COLORS.ink : COLORS.inkMuted,
					}}
				/>
			</div>
		</div>
	);
};

// --------------------------------------------------------------------------

export const MatchProbability: React.FC<MatchProbabilityProps> = ({
	partido,
	indice,
	total,
	mostrarVeredicto = true,
}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();

	const p = normalizarProbabilidades(partido);
	// La fase liga esta llena de equipos rojos: sin esto, un Liverpool-Bayern
	// pinta dos barras del mismo rojo.
	const colores = resolverColoresPartido(partido, COLORS.bg);

	const entradaTitular = muelle(frame, fps, {desde: T.titular, duracion: 22});
	const entradaEnfrentamiento = muelle(frame, fps, {
		desde: T.enfrentamiento,
		duracion: 24,
	});
	const realce = muelleFirme(frame, fps, {desde: T.ganadora, duracion: 18});
	const entradaSello = muelle(frame, fps, {desde: T.sello, duracion: 26});
	const entradaVeredicto = muelle(frame, fps, {desde: T.veredicto, duracion: 20});
	const sacudida = impacto(frame, T.sello + 6);

	const filas: {clave: Resultado; etiqueta: string; color: string; prob: number}[] = [
		{
			clave: 'local',
			etiqueta: partido.local.nombre,
			color: colores.localBarra,
			prob: p.local,
		},
		{
			clave: 'empate',
			etiqueta: 'Empate',
			color: readableOn(COLORS.draw, COLORS.bg, 3.2),
			prob: p.empate,
		},
		{
			clave: 'visitante',
			etiqueta: partido.visitante.nombre,
			color: colores.visitanteBarra,
			prob: p.visitante,
		},
	];

	// El titular es la unica cadena de longitud imprevisible: se le baja el
	// cuerpo si viene largo para que no se salga de la zona segura.
	const tamanoTitular =
		partido.titular.length > 44 ? 72 : partido.titular.length > 30 ? 84 : 96;

	return (
		<AbsoluteFill>
			<MovingBackdrop
				colores={[partido.local.colorPrimario, partido.visitante.colorPrimario]}
			/>

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
				{/* Cabecera --------------------------------------------------- */}
				<div
					style={{
						fontFamily: TEXT_FONT,
						fontWeight: 700,
						fontSize: 32,
						letterSpacing: 7,
						textTransform: 'uppercase',
						color: COLORS.inkMuted,
						opacity: entradaTitular,
					}}
				>
					Partido {indice} <span style={{color: COLORS.accent}}>/</span> {total}
				</div>

				{/* Titular ------------------------------------------------------ */}
				<div
					style={{
						fontFamily: DISPLAY_FONT,
						fontSize: tamanoTitular,
						lineHeight: INTERLINEADO_DISPLAY,
						letterSpacing: -1,
						textTransform: 'uppercase',
						color: COLORS.ink,
						transform: `translateY(${(1 - entradaTitular) * 70}px) scale(${0.86 + entradaTitular * 0.14})`,
						transformOrigin: 'left top',
						opacity: entradaTitular,
					}}
				>
					{partido.titular}
				</div>

				{/* Enfrentamiento ---------------------------------------------- */}
				<div
					style={{
						display: 'flex',
						alignItems: 'center',
						justifyContent: 'space-between',
						gap: 16,
					}}
				>
					<TeamChip
						nombre={partido.local.nombre}
						colorPrimario={partido.local.colorPrimario}
						colorSecundario={partido.local.colorSecundario}
						progreso={entradaEnfrentamiento}
						deslizarDesde="izquierda"
					/>
					<span
						style={{
							fontFamily: DISPLAY_FONT,
							fontSize: 40,
							color: COLORS.inkMuted,
							opacity: entradaEnfrentamiento,
						}}
					>
						VS
					</span>
					<TeamChip
						nombre={partido.visitante.nombre}
						colorPrimario={colores.visitanteBase}
						colorSecundario={partido.visitante.colorSecundario}
						progreso={entradaEnfrentamiento}
						deslizarDesde="derecha"
					/>
				</div>

				{/* Barras -------------------------------------------------------- */}
				<div style={{display: 'flex', flexDirection: 'column', gap: 12}}>
					{filas.map((fila, i) => {
						const desde = T.barras + i * T.escalonBarra;
						return (
							<Barra
								key={fila.clave}
								etiqueta={fila.etiqueta}
								color={fila.color}
								prob={fila.prob}
								relativa={p.maxProb > 0 ? fila.prob / p.maxProb : 0}
								progreso={muelleFirme(frame, fps, {desde, duracion: 34})}
								desde={desde}
								duracion={34}
								esGanadora={p.resaltadas.includes(fila.clave)}
								realce={realce}
							/>
						);
					})}
				</div>

				{/* Marcador predicho y veredicto -------------------------------- */}
				<div
					style={{
						display: 'flex',
						flexDirection: 'column',
						alignItems: 'center',
						gap: 22,
					}}
				>
					<div
						style={{
							display: 'flex',
							alignItems: 'baseline',
							gap: 26,
							backgroundColor: COLORS.accent,
							padding: '10px 40px 18px',
							transform: `rotate(-2.5deg) scale(${0.55 + entradaSello * 0.45}) translateY(${sacudida}px)`,
							opacity: Math.min(1, entradaSello * 2),
							boxShadow: `0 22px 60px ${rgba('#000000', 0.55)}`,
						}}
					>
						<span
							style={{
								fontFamily: TEXT_FONT,
								fontWeight: 700,
								fontSize: 34,
								letterSpacing: 4,
								textTransform: 'uppercase',
								color: '#08080C',
							}}
						>
							Predicción
						</span>
						<span
							style={{
								fontFamily: DISPLAY_FONT,
								fontSize: 128,
								lineHeight: 0.9,
								color: '#08080C',
							}}
						>
							{partido.prediccion}
						</span>
					</div>

					{mostrarVeredicto ? (
						<div
							style={{
								fontFamily: TEXT_FONT,
								fontWeight: 700,
								fontSize: 38,
								letterSpacing: 6,
								textTransform: 'uppercase',
								color: COLORS.accent,
								border: `3px solid ${rgba(COLORS.accent, 0.55)}`,
								padding: '8px 30px 4px',
								transform: `scale(${0.7 + entradaVeredicto * 0.3})`,
								opacity: entradaVeredicto,
							}}
						>
							{veredicto(p.maxProb)}
						</div>
					) : null}
				</div>
			</AbsoluteFill>

			{/* Los cues quedan puestos aunque no haya mp3 en public/sfx/:
			    SfxCue no renderiza nada si el archivo falta. */}
			<SfxCue sfx="whoosh" en={T.titular} />
			<SfxCue sfx="whoosh" en={T.enfrentamiento} volumen={0.7} />
			<SfxCue sfx="ding" en={T.ganadora} />
			<SfxCue sfx="bajon" en={T.sello} />
		</AbsoluteFill>
	);
};
