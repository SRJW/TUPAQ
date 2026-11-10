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
            notes.write_text('''TUPAQ 0.3.0-preview.30: envío nativo de letras de texto con canciones nuevas.

- Implementado el recurso de letras USB, además de conservar las etiquetas originales. Se leen USLT y ©lyr; el texto de SYLT puede enviarse sin activar karaoke.
- Basado en el análisis estático de AMPDevicesAgent 1.7.0.155: UTF-8, ruta específica Lyrics, checksum y confirmación conjunta de componentes.
- Verificación del texto completo y checksum registrados en el catálogo. Letras omitidas, alteradas o corruptas no se declaran verificadas.
- Preferencias → Metadatos: opción para importar letras incrustadas, activa por defecto. Los originales no se modifican ni se descargan letras.
- Recuperación con los mismos IDs, conservación de letras anteriores y prevención de duplicados. Volver a elegir una canción ya importada no actualiza sus letras retroactivamente.
- 245 pruebas en desarrollo, incluidos fallos de entrega, MP3/M4A, Unicode, carátulas, manifiestos y conservación de tiempos SYLT.
- Corregida la espera de la prueba de animación en runners Mac ocupados: comprueba su finalización natural con límite, manteniendo la duración de producción de 180 ms. No se fuerza ni omite la animación para aprobar la prueba.

Esta versión es candidata para validación: el registro se prueba en un teléfono simulado y se comprueba en el catálogo del dispositivo conectado; la visualización en Música del iPhone físico sigue pendiente. No se afirma soporte de letras sincronizadas ni karaoke. La referencia TTML encontrada no demuestra su entrega por USB. Investigación y límites en docs/LETRAS-INVESTIGACION.md.

Prueba una canción nueva con letra incrustada y comprueba después su visualización en Música. Si falla, conserva catalogue-backups y copia el diagnóstico. No repitas una inserción pendiente ni elimines sus registros. Una copia de catálogo no sustituye una copia de los audios.

MP3, WAV, M4A (AAC/ALAC) y AIFF; sin M4P ni FLAC. Windows necesita el servicio/controlador USB de Apple. Paquetes sin firma ni notarización. No se distribuyen fuentes ni DLL de Apple o 3uTools.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
