import React from 'react';
import {AbsoluteFill, useCurrentFrame} from 'remotion';
import {COLORS} from '../theme';
import {rgba} from '../lib/color';

type Props = {
	/** Tinta el fondo con los colores de los protagonistas de la escena. */
	colores: readonly string[];
};

/**
 * Fondo que nunca se para.
 *
 * Regla de ritmo: siempre tiene que haber algo en movimiento en pantalla,
 * aunque el contenido este quieto. Aqui hay tres capas moviendose a
 * velocidades distintas y ninguna reclama atencion.
 */
export const MovingBackdrop: React.FC<Props> = ({colores}) => {
	const frame = useCurrentFrame();

	return (
		<AbsoluteFill style={{backgroundColor: COLORS.bg}}>
			{/* Manchas de color de los equipos, a la deriva. */}
			{colores.map((color, i) => {
				const fase = i * 2.1;
				const x = Math.sin(frame / 95 + fase) * 190;
				const y = Math.cos(frame / 130 + fase) * 240;
				const escala = 1 + Math.sin(frame / 75 + fase) * 0.12;

				return (
					<div
						key={`${color}-${i}`}
						style={{
							position: 'absolute',
							width: 1250,
							height: 1250,
							left: i === 0 ? -360 : 190,
							top: i === 0 ? 90 : 780,
							borderRadius: '50%',
							background: `radial-gradient(circle, ${rgba(color, 0.4)} 0%, ${rgba(color, 0)} 68%)`,
							transform: `translate(${x}px, ${y}px) scale(${escala})`,
							filter: 'blur(70px)',
						}}
					/>
				);
			})}

			{/* Trama diagonal en desplazamiento continuo. El contenedor va
			    sobredimensionado para que al trasladarse no asome ningun borde. */}
			<div
				style={{
					position: 'absolute',
					left: '-50%',
					top: '-50%',
					width: '200%',
					height: '200%',
					backgroundImage:
						'repeating-linear-gradient(115deg, rgba(255,255,255,0.035) 0px, rgba(255,255,255,0.035) 2px, transparent 2px, transparent 30px)',
					transform: `translateX(${(frame * 0.85) % 66}px)`,
				}}
			/>

			{/* Vinetas: hunden los bordes y empujan la vista al centro. */}
			<AbsoluteFill
				style={{
					background:
						'radial-gradient(ellipse at 50% 45%, transparent 38%, rgba(0,0,0,0.72) 100%)',
				}}
			/>
		</AbsoluteFill>
	);
};
