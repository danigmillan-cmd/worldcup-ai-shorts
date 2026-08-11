import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {muelleFirme} from '../lib/animacion';

type Props = {
	/** Valor final. El contador rueda de 0 hasta aqui. */
	valor: number;
	/** Frame absoluto en el que arranca. */
	desde: number;
	duracion?: number;
	decimales?: number;
	prefijo?: string;
	/** Se pinta mas pequeno pegado al numero: "%", "pts"... */
	sufijo?: string;
	/** Tamano del sufijo en px. Por defecto, la mitad del cuerpo. */
	tamanoSufijo?: number;
	style?: React.CSSProperties;
};

const formateador = (decimales: number) =>
	new Intl.NumberFormat('es-ES', {
		minimumFractionDigits: decimales,
		maximumFractionDigits: decimales,
	});

/**
 * Numero que rueda de 0 al valor final.
 *
 * Usa `muelleFirme` (con `overshootClamping`) a proposito: un muelle con rebote
 * haria que un 41 pasara por 46 antes de asentarse. En una escala o una
 * posicion el rebote da vida; en una cifra parece un error de calculo.
 */
export const AnimatedCounter: React.FC<Props> = ({
	valor,
	desde,
	duracion = 34,
	decimales = 0,
	prefijo,
	sufijo,
	tamanoSufijo,
	style,
}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();

	const progreso = muelleFirme(frame, fps, {desde, duracion});
	const actual = valor * progreso;

	const cuerpo =
		typeof style?.fontSize === 'number' ? style.fontSize : undefined;

	return (
		<span
			style={{
				// Cifras de ancho fijo: sin esto el numero baila mientras rueda.
				fontVariantNumeric: 'tabular-nums',
				...style,
			}}
		>
			{prefijo}
			{formateador(decimales).format(actual)}
			{sufijo ? (
				<span
					style={{
						fontSize: tamanoSufijo ?? (cuerpo ? cuerpo * 0.5 : undefined),
						marginLeft: 2,
					}}
				>
					{sufijo}
				</span>
			) : null}
		</span>
	);
};
