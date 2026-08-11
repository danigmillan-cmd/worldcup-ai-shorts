import {Config} from '@remotion/cli/config';

Config.setEntryPoint('./src/index.ts');
Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);

// Remotion usa CRF 18 por defecto (calidad de master): ~44 MB para 48s. YouTube
// reencoda de todas formas, asi que 23 es transparente a la vista y deja el
// archivo en un tercio, que importa para el tiempo de subida y los artefactos
// de CI. Sube la calidad puntualmente con `--crf 18`.
Config.setCrf(23);

// El pipeline final corre en Ubuntu headless (GitHub Actions). Nada aqui puede
// depender de una GUI ni de rutas de Windows.
Config.setConcurrency(null); // null = Remotion decide segun los cores disponibles
