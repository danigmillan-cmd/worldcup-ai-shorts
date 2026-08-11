import React from 'react';
import {Composition} from 'remotion';
import captionsJson from '../sample-data/captions.json';
import jornadaJson from '../sample-data/jornada.json';
import {
	MATCH_PROBABILITY_DURATION,
	MatchProbability,
	matchProbabilitySchema,
} from './compositions/MatchProbability';
import {
	duracionRankingCountdown,
	RankingCountdown,
	rankingCountdownSchema,
} from './compositions/RankingCountdown';
import {
	calcularMetadataShort,
	OPCIONES_POR_DEFECTO,
	Short,
	shortSchema,
} from './compositions/Short';
import {
	WordCaptionsPreview,
	wordCaptionsPreviewSchema,
} from './compositions/WordCaptionsPreview';
import {VIDEO} from './theme';
import {jornadaSchema, palabraCaptionSchema} from './types';
import {z} from 'zod';

/**
 * Los JSON de ejemplo se validan al arrancar. Si el formato se rompe, el Studio
 * lo dice aqui con un mensaje claro en vez de fallar mas tarde con un
 * `undefined` a mitad de render.
 */
const jornada = jornadaSchema.parse(jornadaJson);
const captions = z.array(palabraCaptionSchema).parse(captionsJson);

const primerPartido = jornada.partidos[0];
if (!primerPartido) {
	throw new Error('sample-data/jornada.json debe tener al menos un partido.');
}

export const RemotionRoot: React.FC = () => {
	return (
		<>
			{/*
			 * La composicion que se publica. No lleva `durationInFrames`: la
			 * calcula `calcularMetadataShort` a partir de los props, porque tres
			 * partidos no duran lo mismo que cuatro.
			 */}
			<Composition
				id="Short"
				component={Short}
				schema={shortSchema}
				calculateMetadata={calcularMetadataShort}
				fps={VIDEO.fps}
				width={VIDEO.width}
				height={VIDEO.height}
				defaultProps={{...jornada, opciones: OPCIONES_POR_DEFECTO}}
			/>

			<Composition
				id="MatchProbability"
				component={MatchProbability}
				schema={matchProbabilitySchema}
				durationInFrames={MATCH_PROBABILITY_DURATION}
				fps={VIDEO.fps}
				width={VIDEO.width}
				height={VIDEO.height}
				defaultProps={{
					partido: primerPartido,
					indice: 1,
					total: jornada.partidos.length,
				}}
			/>

			<Composition
				id="RankingCountdown"
				component={RankingCountdown}
				schema={rankingCountdownSchema}
				durationInFrames={duracionRankingCountdown(jornada.ranking.length)}
				fps={VIDEO.fps}
				width={VIDEO.width}
				height={VIDEO.height}
				defaultProps={{
					ranking: jornada.ranking,
					titulo: 'Quién gana la Champions',
				}}
			/>

			<Composition
				id="WordCaptionsPreview"
				component={WordCaptionsPreview}
				schema={wordCaptionsPreviewSchema}
				durationInFrames={180}
				fps={VIDEO.fps}
				width={VIDEO.width}
				height={VIDEO.height}
				defaultProps={{
					captions,
					texto:
						'Ocho partidos seis acertados y esta jornada hay un favorito que nadie espera',
				}}
			/>
		</>
	);
};
