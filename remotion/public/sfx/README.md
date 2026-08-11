# public/sfx/

Aquí van los efectos de sonido. **Los archivos no están en el repo y no se descargan
automáticamente**: hay que ponerlos a mano.

## Archivos esperados

| Archivo      | Para qué                                                | Duración |
| ------------ | ------------------------------------------------------- | -------- |
| `whoosh.mp3` | Transición entre bloques, corte a otro partido           | 200-400 ms |
| `ding.mp3`   | Cifra que se asienta, puesto que se revela               | 300-600 ms |
| `bajon.mp3`  | Caída de tono para el dato negativo o el cierre          | 400-800 ms |

Los nombres tienen que coincidir exactamente. Están declarados en `src/sfx.ts`.

## Cómo funciona

`<SfxCue sfx="whoosh" en={62} />` coloca el efecto en el frame 62.

Mientras el mp3 no exista en esta carpeta, `SfxCue` no renderiza nada y el vídeo sale
mudo. No falla. Esto es a propósito: los cues se pueden dejar puestos en las
composiciones desde el principio y el render sigue funcionando en limpio, también en
GitHub Actions.

La comprobación la hace `rutaSfx()` con `getStaticFiles()`, que conoce el contenido real
de `public/`. Sin ella, un `staticFile()` apuntando a un archivo que no existe revienta
a mitad de render con un error de red poco claro.

## Restricciones

Solo SFX aportados a mano, con derechos para usarlos. **Nada de himno de la Champions
ni música con copyright.** El canal se cae si se sube eso.
