"""Publish each tested platform independently so other runners cannot block it."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    package = Path(sys.argv[1]).resolve()
    if not package.is_file():
        raise RuntimeError('Verified package is missing')
    tag = os.environ['GITHUB_REF_NAME']
    repo = os.environ['GITHUB_REPOSITORY']
    view = ['gh', 'release', 'view', tag, '--repo', repo]
    if subprocess.run(view, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        with tempfile.TemporaryDirectory() as directory:
            notes = Path(directory)/'notes.md'
            notes.write_text('''TUPAQ 0.3.0-preview.10: biblioteca estable, tipografía global y estilo Apple Music.

- Sin vaciar la biblioteca mientras se actualiza después de importar. Conserva selección, casillas, posición de lectura y carátulas válidas. Ante un error mantiene la vista anterior con aviso.
- Diseño inspirado en Apple Music: portada y resumen sobre la lista, paneles suaves, acento rosa y barra inferior de transferencias. Fondos estáticos, sin motor web ni desenfoque continuo.
- Windows: elegir una fuente instalada o archivo TTF/OTF/TTC/OTC, ver una muestra y pulsar Aplicar. El cambio alcanza toda la interfaz, incluidas cabeceras y botones. Guardado solo al aplicar; un archivo inválido conserva la fuente anterior.
- Mac: siempre fuente del sistema, sin personalización de familia.
- 130 pruebas y comprobación de la aplicación empaquetada. Pruebas de actualización lenta/fallida, posición de lectura, selección, caché y aplicación global de fuentes.
- Propuestas futuras documentadas: cola persistente e historial, vistas Álbumes/Recientes y avisos de posibles duplicados.

El usuario confirmó que la preview.8 funciona con su iPhone. Esta revisión modifica la presentación y tipografía; los cambios visuales se validan en simulación y necesitan su comprobación con el dispositivo. Conserva las comprobaciones de importación, exportación y eliminación; eliminar sigue requiriendo casillas y confirmación.

Windows y Mac: no necesitas Python ni abrir iTunes. Cada paquete aparece después de pasar las comprobaciones de su plataforma. Paquetes sin firma ni notarización. No se redistribuyen archivos de fuentes de Apple. La copia del catálogo no incluye todos los audios ni permite restaurarlos automáticamente. Instrucciones: docs/TRANSFERENCIAS.md.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
