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
            notes.write_text('''TUPAQ 0.3.0-preview.14: interfaz en español e inglés y comprobación de Windows.

- Preferencias → Idioma: Español o English, aplicado al instante y guardado entre aperturas.
- Traducción de navegación, preferencias, cabeceras, botones, ayudas, confirmaciones, progreso y errores de TUPAQ. Los diálogos nativos de archivos también dependen del idioma del sistema.
- El cambio conserva cola, biblioteca, selección, marcas, búsqueda, apariencia y fuente. No vuelve a consultar el teléfono ni modifica música.
- Títulos, artistas, álbumes, nombres de dispositivo, rutas y códigos de diagnóstico permanecen intactos. Las etiquetas del CSV siguen el idioma elegido.
- Traducciones locales, sin servicios externos. Se incluye el catálogo de controles estándar de Qt en español.
- Comprobación temporal del protocolo con un reloj de alta precisión también en Windows/Python 3.12. Mantiene el rechazo de confirmaciones prematuras y la aceptación de respuestas rápidas válidas.
- 146 pruebas y comprobación de cada ejecutable empaquetado, con cambio de idioma y persistencia verificados en simulación. Lectura explícita UTF-8 en la prueba del catálogo de traducciones.

Se mantienen las funciones de preview.12: importación/exportación, casillas y eliminación con confirmación, tres ambientes de cristal, tipografía global y Cancelar. Si Música ya recibe cambios, la cancelación termina y verifica el lote actual. Conserva catalogue-backups para comprobar operaciones pendientes.

Windows y Mac: no necesitas Python ni abrir iTunes. Cada paquete aparece después de pasar sus comprobaciones. Paquetes sin firma ni notarización. No se redistribuyen fuentes de Apple. La copia del catálogo no incluye todos los audios ni permite restaurarlos automáticamente. Instrucciones: docs/TRANSFERENCIAS.md.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
