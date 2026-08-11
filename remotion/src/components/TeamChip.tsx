import React from 'react';
import {contrastRatio, textOn} from '../lib/color';
import {COLORS, DISPLAY_FONT} from '../theme';

type Props = {
	nombre: string;
	colorPrimario: string;
	colorSecundario: string;
	/** 0 = fuera, 1 = colocado. Normalmente viene de un muelle. */
	progreso?: number;
	/** Direccion de entrada. `null` para que solo aparezca sin desplazarse. */
	deslizarDesde?: 'izquierda' | 'derecha' | null;
	/** Cuerpo en px. Si se omite, se ajusta a la longitud del nombre. */
	tamano?: number;
};

/**
 * Nombre de equipo sobre un bloque de su color primario.
 *
 * Es la unica representacion visual de un club que hay en todo el proyecto: no
 * se usan escudos ni logos, solo texto y color, y ambos salen del JSON.
 */
export const TeamChip: React.FC<Props> = ({
	nombre,
	colorPrimario,
	colorSecundario,
	progreso = 1,
	deslizarDesde = null,
	tamano,
}) => {
	const cuerpo = tamano ?? (nombre.length > 12 ? 42 : 52);

	const desplazamiento =
		deslizarDesde === null
			? 0
			: (1 - progreso) * (deslizarDesde === 'izquierda' ? -520 : 520);

	// Un primario muy oscuro (el azul marino del Inter) se funde con el fondo
	// negro y el bloque desaparece. En ese caso se perfila con el secundario.
	const necesitaPerfil = contrastRatio(colorPrimario, COLORS.bg) < 1.7;

	return (
		<div
			style={{
				backgroundColor: colorPrimario,
				borderBottom: `${Math.round(cuerpo * 0.17)}px solid ${colorSecundario}`,
				outline: necesitaPerfil ? `3px solid ${colorSecundario}` : 'none',
				padding: `${Math.round(cuerpo * 0.3)}px ${Math.round(cuerpo * 0.54)}px ${Math.round(cuerpo * 0.23)}px`,
				transform: `translateX(${desplazamiento}px)`,
				opacity: progreso,
				whiteSpace: 'nowrap',
			}}
		>
			<span
				style={{
					fontFamily: DISPLAY_FONT,
					fontSize: cuerpo,
					lineHeight: 1,
					letterSpacing: 1,
					textTransform: 'uppercase',
					color: textOn(colorPrimario),
				}}
			>
				{nombre}
			</span>
		</div>
	);
};
