import React from 'react';
import {
	AbsoluteFill,
	Audio,
	Series,
	useCurrentFrame,
	useVideoConfig,
	type CalculateMetadataFunction,
} from 'remotion';
import {z} from 'zod';
import {AnimatedCounter} from '../components/AnimatedCounter';
import {MovingBackdrop} from '../components/MovingBackdrop';
import {ProgressBar} from '../components/ProgressBar';
import {SfxCue} from '../components/SfxCue';
import {WordCaptions} from '../components/WordCaptions';
import {muelle, muelleFirme} from '../lib/animacion';
import {rgba} from '../lib/color';
import {normalizarProbabilidades} from '../lib/probabilidades';
import {archivoPublico} from '../lib/publico';
import {
	COLORS,
	DISPLAY_FONT,
	INTERLINEADO_DISPLAY,
	SAFE,
	TEXT_FONT,
} from '../theme';
import {
	jornadaSchema,
	palabraCaptionSchema,
	type Aciertos,
	type Jornada,
	type PalabraCaption,
} from '../types';
import {
	MATCH_PROBABILITY_DURATION,
	MatchProbability,
} from './MatchProbability';
import {duracionRankingCountdown, RankingCountdown} from './RankingCountdown';

// --------------------------------------------------------------------------
// Props
// --------------------------------------------------------------------------

/**
 * Todos los campos son opcionales, y no por comodidad.
 *
 * Remotion mezcla `defaultProps` con los props de `--props` de forma
 * SUPERFICIAL: si el JSON externo trae `opciones`, sustituye al objeto entero,
 * no se fusiona campo a campo. Con campos obligatorios, pasar
 * `{"opciones": {"cierre": "cta"}}` haria fallar la validacion por los cinco
 * campos que faltan. Asi un override parcial funciona como uno espera.
 */
export const opcionesShortSchema = z.object({
	/** Cuantos partidos entran en el cuerpo. El resto del JSON se ignora. */
	maxPartidos: z.number().int().min(1).max(6).optional(),
	cierre: z.enum(['ranking', 'cta']).optional(),
	tituloRanking: z.string().min(1).optional(),
	/** Rotulo junto al porcentaje del countdown. Ver RankingCountdown. */
	etiquetaRanking: z.string().min(1).optional(),
	cta: z
		.object({
			titulo: z.string().min(1).optional(),
			subtitulo: z.string().min(1).optional(),
		})
		.optional(),
	/** Ruta del voiceover dentro de `public/`. `null` = video mudo. */
	voiceover: z.string().nullable().optional(),
	/** Timings palabra a palabra. `null` = sin subtitulos quemados. */
	captions: z.array(palabraCaptionSchema).nullable().optional(),
	/** Texto del gancho. `null` = se deduce del partido mas desequilibrado. */
	hookTexto: z.string().nullable().optional(),
	/** Ruta de la musica de fondo dentro de `public/`. `null` = sin musica. */
	musica: z.string().nullable().optional(),
	/** Volumen de la musica, 0 a 1. Por debajo del voiceover a proposito. */
	musicaVolumen: z.number().min(0).max(1).optional(),
});

/** Lo que puede llegar por el JSON: cualquier subconjunto. */
export type OpcionesShortEntrada = z.infer<typeof opcionesShortSchema>;

/** Lo que usan los componentes: todo resuelto, sin `undefined`. */
export type OpcionesShort = {
	maxPartidos: number;
	cierre: 'ranking' | 'cta';
	tituloRanking: string;
	etiquetaRanking: string;
	cta: {titulo: string; subtitulo: string};
	voiceover: string | null;
	captions: PalabraCaption[] | null;
	hookTexto: string | null;
	musica: string | null;
	musicaVolumen: number;
};

/**
 * Los props del Short son la jornada tal cual, mas un bloque `opciones`.
 *
 * Que el JSON de jornada sea directamente la raiz de los props es lo que
 * permite `--props=jornada.json` sin envoltorios. `opciones` es opcional y se
 * completa con `OPCIONES_POR_DEFECTO`, asi que un fichero de jornada pelado
 * renderiza sin mas.
 */
export const shortSchema = jornadaSchema.extend({
	opciones: opcionesShortSchema.optional(),
});

export type ShortProps = z.infer<typeof shortSchema>;

export const OPCIONES_POR_DEFECTO: OpcionesShort = {
	maxPartidos: 4,
	cierre: 'ranking',
	tituloRanking: 'Quién gana la Champions',
	etiquetaRanking: 'Opciones de título',
	cta: {
		titulo: '¿Y tú qué dices?',
		subtitulo: 'Sígueme y lo comprobamos la semana que viene',
	},
	voiceover: null,
	captions: null,
	hookTexto: null,
	musica: null,
	musicaVolumen: 0.22,
};

/**
 * Rellena campo a campo, incluido el `cta` anidado. Un spread plano no vale:
 * `{...defecto, ...{cta: {titulo: 'x'}}}` perderia el subtitulo.
 */
export const resolverOpciones = (
	o: OpcionesShortEntrada | undefined,
): OpcionesShort => ({
	maxPartidos: o?.maxPartidos ?? OPCIONES_POR_DEFECTO.maxPartidos,
	cierre: o?.cierre ?? OPCIONES_POR_DEFECTO.cierre,
	tituloRanking: o?.tituloRanking ?? OPCIONES_POR_DEFECTO.tituloRanking,
	etiquetaRanking: o?.etiquetaRanking ?? OPCIONES_POR_DEFECTO.etiquetaRanking,
	cta: {
		titulo: o?.cta?.titulo ?? OPCIONES_POR_DEFECTO.cta.titulo,
		subtitulo: o?.cta?.subtitulo ?? OPCIONES_POR_DEFECTO.cta.subtitulo,
	},
	voiceover: o?.voiceover ?? OPCIONES_POR_DEFECTO.voiceover,
	captions: o?.captions ?? OPCIONES_POR_DEFECTO.captions,
	hookTexto: o?.hookTexto ?? OPCIONES_POR_DEFECTO.hookTexto,
	musica: o?.musica ?? OPCIONES_POR_DEFECTO.musica,
	musicaVolumen: o?.musicaVolumen ?? OPCIONES_POR_DEFECTO.musicaVolumen,
});

// --------------------------------------------------------------------------
// Duracion
// --------------------------------------------------------------------------

export const HOOK_FRAMES = 60; // 2s
export const PRUEBA_FRAMES = 60; // 2s
export const CTA_FRAMES = 150; // 5s

/** Cierra con ranking solo si hay ranking; si no, se cae al CTA. */
const cierreEfectivo = (
	jornada: Jornada,
	opciones: OpcionesShort,
): 'ranking' | 'cta' =>
	opciones.cierre === 'ranking' && jornada.ranking.length > 0 ? 'ranking' : 'cta';

/**
 * Solo hay prueba social si hay algo medido que ensenar. Ver la nota de
 * `aciertosSchema` en types.ts, incluida la parte de por que el generador
 * manda `null` explicito en vez de omitir la clave.
 */
export const hayPruebaSocial = (jornada: Jornada): boolean =>
	Boolean(jornada.aciertosJornadaAnterior);

export const duracionShort = (
	jornada: Jornada,
	opciones: OpcionesShort,
): number => {
	const partidos = Math.min(jornada.partidos.length, opciones.maxPartidos);
	const cierre =
		cierreEfectivo(jornada, opciones) === 'ranking'
			? duracionRankingCountdown(jornada.ranking.length)
			: CTA_FRAMES;

	return (
		HOOK_FRAMES +
		(hayPruebaSocial(jornada) ? PRUEBA_FRAMES : 0) +
		partidos * MATCH_PROBABILITY_DURATION +
		cierre
	);
};

/**
 * La duracion depende de los datos: 3 partidos no duran lo mismo que 4, y
 * cerrar con ranking no dura lo mismo que cerrar con CTA. `calculateMetadata`
 * es la forma idiomatica en Remotion de que la composicion se dimensione sola
 * a partir de los props, sin tocar codigo al cambiar de jornada.
 *
 * Tambien es donde se valida el JSON de entrada: si el fichero que llega por
 * `--props` esta mal, el render falla aqui con un error de Zod legible en vez
 * de a mitad de render con un `undefined`.
 */
export const calcularMetadataShort: CalculateMetadataFunction<ShortProps> = ({
	props,
}) => {
	const jornada = shortSchema.parse(props);
	const opciones = resolverOpciones(jornada.opciones);

	return {
		durationInFrames: duracionShort(jornada, opciones),
		props: {...jornada, opciones},
	};
};

// --------------------------------------------------------------------------
// Bloques
// --------------------------------------------------------------------------

/**
 * Gancho: el dato mas llamativo de la jornada, a pantalla completa.
 * Sin intro, sin logo, sin saludo. Dos segundos para que no pase el dedo.
 */
const Hook: React.FC<{jornada: Jornada; textoManual: string | null}> = ({
	jornada,
	textoManual,
}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();

	// El partido mas desequilibrado de la jornada: es el titular natural.
	let destacado: {prob: number; frase: string; titular: string; color: string} | null =
		null;

	for (const partido of jornada.partidos) {
		const p = normalizarProbabilidades(partido);
		if (destacado && p.maxProb <= destacado.prob) {
			continue;
		}
		const frase =
			p.favorito === 'local'
				? `${partido.local.nombre} gana`
				: p.favorito === 'visitante'
					? `${partido.visitante.nombre} gana`
					: 'Acaba en empate';
		const color =
			p.favorito === 'visitante'
				? partido.visitante.colorPrimario
				: partido.local.colorPrimario;

		destacado = {prob: p.maxProb, frase, titular: partido.titular, color};
	}

	const entradaFrase = muelle(frame, fps, {desde: 34, duracion: 16});
	const entradaTitular = muelle(frame, fps, {desde: 46, duracion: 14});
	const escalaNumero = muelle(frame, fps, {desde: 0, duracion: 20});

	return (
		<AbsoluteFill>
			<MovingBackdrop colores={[destacado?.color ?? COLORS.accent]} />
			<AbsoluteFill
				style={{
					paddingTop: SAFE.top,
					paddingBottom: SAFE.bottom,
					paddingLeft: SAFE.side,
					paddingRight: SAFE.side,
					display: 'flex',
					flexDirection: 'column',
					justifyContent: 'center',
					gap: 10,
				}}
			>
				{textoManual ? (
					<div
						style={{
							fontFamily: DISPLAY_FONT,
							fontSize: 130,
							lineHeight: INTERLINEADO_DISPLAY,
							letterSpacing: -2,
							textTransform: 'uppercase',
							color: COLORS.ink,
							transform: `scale(${0.8 + escalaNumero * 0.2})`,
							transformOrigin: 'left center',
						}}
					>
						{textoManual}
					</div>
				) : (
					<>
						<AnimatedCounter
							valor={(destacado?.prob ?? 0) * 100}
							desde={0}
							duracion={28}
							sufijo="%"
							style={{
								fontFamily: DISPLAY_FONT,
								fontSize: 340,
								lineHeight: 0.82,
								color: COLORS.accent,
								transform: `scale(${0.7 + escalaNumero * 0.3})`,
								transformOrigin: 'left center',
								display: 'inline-block',
							}}
						/>
						<div
							style={{
								fontFamily: DISPLAY_FONT,
								fontSize: 106,
								lineHeight: INTERLINEADO_DISPLAY,
								letterSpacing: -2,
								textTransform: 'uppercase',
								color: COLORS.ink,
								transform: `translateY(${(1 - entradaFrase) * 60}px)`,
								opacity: entradaFrase,
							}}
						>
							{destacado?.frase ?? ''}
						</div>
						<div
							style={{
								marginTop: 18,
								fontFamily: TEXT_FONT,
								fontWeight: 700,
								fontSize: 46,
								lineHeight: 1.2,
								color: COLORS.inkMuted,
								opacity: entradaTitular,
							}}
						>
							{destacado?.titular ?? ''}
						</div>
					</>
				)}
			</AbsoluteFill>
			<SfxCue sfx="whoosh" en={0} />
		</AbsoluteFill>
	);
};

/** Prueba social: los aciertos de la jornada anterior, con contador. */
const PruebaSocial: React.FC<{aciertos: Aciertos}> = ({aciertos}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();
	const {acertados, total} = aciertos;

	const entradaEtiqueta = muelle(frame, fps, {desde: 34, duracion: 14});

	return (
		<AbsoluteFill>
			<MovingBackdrop colores={[COLORS.accent]} />
			<AbsoluteFill
				style={{
					paddingTop: SAFE.top,
					paddingBottom: SAFE.bottom,
					paddingLeft: SAFE.side,
					paddingRight: SAFE.side,
					display: 'flex',
					flexDirection: 'column',
					justifyContent: 'center',
					gap: 8,
				}}
			>
				<div
					style={{
						fontFamily: TEXT_FONT,
						fontWeight: 700,
						fontSize: 40,
						letterSpacing: 8,
						textTransform: 'uppercase',
						color: COLORS.inkMuted,
					}}
				>
					La jornada pasada
				</div>

				<div style={{display: 'flex', alignItems: 'baseline'}}>
					<AnimatedCounter
						valor={acertados}
						desde={6}
						duracion={26}
						style={{
							fontFamily: DISPLAY_FONT,
							fontSize: 330,
							lineHeight: 0.85,
							color: COLORS.accent,
						}}
					/>
					<span
						style={{
							fontFamily: DISPLAY_FONT,
							fontSize: 180,
							lineHeight: 0.85,
							color: COLORS.inkMuted,
						}}
					>
						/{total}
					</span>
				</div>

				<div
					style={{
						fontFamily: DISPLAY_FONT,
						fontSize: 92,
						lineHeight: INTERLINEADO_DISPLAY,
						letterSpacing: -1,
						textTransform: 'uppercase',
						color: COLORS.ink,
						transform: `translateY(${(1 - entradaEtiqueta) * 50}px)`,
						opacity: entradaEtiqueta,
					}}
				>
					Aciertos
				</div>

				{/* Marcas que se encienden una a una: da movimiento a los ultimos
				    frames del bloque, que si no se quedarian quietos. */}
				<div style={{display: 'flex', gap: 12, marginTop: 26}}>
					{Array.from({length: total}, (_, i) => {
						const encendida = muelleFirme(frame, fps, {
							desde: 40 + i * 2,
							duracion: 10,
						});
						return (
							<div
								key={i}
								style={{
									flex: 1,
									height: 22,
									backgroundColor:
										i < acertados
											? rgba(COLORS.accent, encendida)
											: rgba(COLORS.ink, 0.14),
								}}
							/>
						);
					})}
				</div>
			</AbsoluteFill>
			<SfxCue sfx="ding" en={30} />
		</AbsoluteFill>
	);
};

/** Cierre alternativo al ranking. */
const CtaSuscripcion: React.FC<{titulo: string; subtitulo: string}> = ({
	titulo,
	subtitulo,
}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();

	const entradaTitulo = muelle(frame, fps, {desde: 0, duracion: 20});
	const entradaSub = muelle(frame, fps, {desde: 30, duracion: 18});
	const entradaBloque = muelle(frame, fps, {desde: 60, duracion: 20});
	// Latido continuo: el CTA nunca se queda inmovil.
	const latido = 1 + 0.03 * Math.sin(frame / 6);

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
					gap: 34,
				}}
			>
				<div
					style={{
						fontFamily: DISPLAY_FONT,
						fontSize: 132,
						lineHeight: INTERLINEADO_DISPLAY,
						letterSpacing: -3,
						textTransform: 'uppercase',
						color: COLORS.ink,
						transform: `translateY(${(1 - entradaTitulo) * 70}px)`,
						opacity: entradaTitulo,
					}}
				>
					{titulo}
				</div>

				<div
					style={{
						fontFamily: TEXT_FONT,
						fontWeight: 700,
						fontSize: 52,
						lineHeight: 1.2,
						color: COLORS.inkMuted,
						transform: `translateY(${(1 - entradaSub) * 40}px)`,
						opacity: entradaSub,
					}}
				>
					{subtitulo}
				</div>

				<div
					style={{
						alignSelf: 'flex-start',
						backgroundColor: COLORS.accent,
						color: '#08080C',
						fontFamily: DISPLAY_FONT,
						fontSize: 76,
						letterSpacing: 2,
						textTransform: 'uppercase',
						padding: '18px 44px 12px',
						transform: `scale(${(0.6 + entradaBloque * 0.4) * latido}) rotate(-2deg)`,
						opacity: Math.min(1, entradaBloque * 2),
					}}
				>
					Suscríbete
				</div>
			</AbsoluteFill>
			<SfxCue sfx="whoosh" en={0} />
			<SfxCue sfx="ding" en={60} />
		</AbsoluteFill>
	);
};

// --------------------------------------------------------------------------
// Composicion raiz
// --------------------------------------------------------------------------

export const Short: React.FC<ShortProps> = (props) => {
	const opciones = resolverOpciones(props.opciones);
	const partidos = props.partidos.slice(0, opciones.maxPartidos);
	const cierre = cierreEfectivo(props, opciones);

	const voz = archivoPublico(opciones.voiceover);
	const captions = opciones.captions;
	const hayCaptions = Boolean(captions && captions.length > 0);

	const musica = archivoPublico(opciones.musica);
	const {durationInFrames, fps} = useVideoConfig();

	/**
	 * Entrada y salida de la musica. La salida es lo que importa: las pistas
	 * duran dos o tres minutos y el Short medio, asi que el corte cae en mitad
	 * de un compas y suena a error de montaje. El medio segundo de entrada
	 * evita el golpe seco del primer frame.
	 */
	const volumenMusica = React.useCallback(
		(f: number) => {
			const entrada = Math.round(fps * 0.5);
			const salida = Math.round(fps * 1.5);
			const subida = entrada > 0 ? Math.min(1, f / entrada) : 1;
			const restantes = durationInFrames - 1 - f;
			const bajada = salida > 0 ? Math.min(1, Math.max(0, restantes) / salida) : 1;
			return opciones.musicaVolumen * subida * bajada;
		},
		[durationInFrames, fps, opciones.musicaVolumen],
	);

	return (
		<AbsoluteFill style={{backgroundColor: COLORS.bg}}>
			<Series>
				<Series.Sequence durationInFrames={HOOK_FRAMES} name="Hook">
					<Hook jornada={props} textoManual={opciones.hookTexto} />
				</Series.Sequence>

				{props.aciertosJornadaAnterior ? (
					<Series.Sequence durationInFrames={PRUEBA_FRAMES} name="Prueba social">
						<PruebaSocial aciertos={props.aciertosJornadaAnterior} />
					</Series.Sequence>
				) : null}

				{partidos.map((partido, i) => (
					<Series.Sequence
						key={`${partido.local.nombre}-${partido.visitante.nombre}`}
						durationInFrames={MATCH_PROBABILITY_DURATION}
						name={`${partido.local.nombre} · ${partido.visitante.nombre}`}
					>
						<MatchProbability
							partido={partido}
							indice={i + 1}
							total={partidos.length}
							mostrarVeredicto={!hayCaptions}
						/>
					</Series.Sequence>
				))}

				<Series.Sequence
					durationInFrames={
						cierre === 'ranking'
							? duracionRankingCountdown(props.ranking.length)
							: CTA_FRAMES
					}
					name={cierre === 'ranking' ? 'Cierre · Ranking' : 'Cierre · CTA'}
				>
					{cierre === 'ranking' ? (
						<RankingCountdown
							ranking={props.ranking}
							titulo={opciones.tituloRanking}
							etiquetaProbabilidad={opciones.etiquetaRanking}
							mostrarSello={!hayCaptions}
						/>
					) : (
						<CtaSuscripcion
							titulo={opciones.cta.titulo}
							subtitulo={opciones.cta.subtitulo}
						/>
					)}
				</Series.Sequence>
			</Series>

			{/* Fuera de <Series> a proposito: dentro de una secuencia,
			    useCurrentFrame() es relativo y la barra mediria el bloque. */}
			<ProgressBar />

			{voz ? <Audio src={voz} /> : null}
			{musica ? (
				<Audio src={musica} volume={volumenMusica} name="Música de fondo" />
			) : null}

			{hayCaptions ? (
				<AbsoluteFill
					style={{
						paddingLeft: SAFE.side,
						paddingRight: SAFE.side,
						paddingBottom: SAFE.bottom,
						// AbsoluteFill ya viene con flexDirection: column. Sin fijarlo,
						// `alignItems: flex-end` alinea a la derecha, no abajo.
						display: 'flex',
						flexDirection: 'column',
						justifyContent: 'flex-end',
						alignItems: 'center',
					}}
				>
					{/* Velo para que los subtitulos se lean sobre cualquier escena. */}
					<AbsoluteFill
						style={{
							top: 'auto',
							bottom: 0,
							height: SAFE.bottom + 420,
							background: `linear-gradient(to top, ${rgba('#000000', 0.8)}, ${rgba('#000000', 0)})`,
						}}
					/>
					<WordCaptions captions={captions} tamano={88} />
				</AbsoluteFill>
			) : null}
		</AbsoluteFill>
	);
};
