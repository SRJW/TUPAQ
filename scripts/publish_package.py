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
            notes.write_text('''TUPAQ 0.3.0-preview.26: importación, carátulas y controles pulidos.

- Corregida la creación de la carpeta de carátulas con la API real de pymobiledevice3: makedirs, sin la llamada inexistente mkdir. El fallo podía dejar los metadatos anunciados sin entregar el audio.
- Al reintentar con los mismos originales, se intenta completar una única operación antigua detenida por AttributeError en esa fase. Se conservan los respaldos y se vuelven a comprobar identidad, catálogo, ancla y archivos. Las operaciones ajenas, ambiguas o modificadas permanecen bloqueadas para revisión.
- La carátula incrustada en el archivo prevalece en miniaturas y detalles. Un archivo leído sin imagen no hereda la de otro álbum; los enlaces ambiguos de la caché se rechazan.
- Desplegables, listas emergentes, menús, casillas, diálogos y barras de desplazamiento con controles coherentes en claro y oscuro. Fuente del sistema resuelta también en el estilo de la interfaz.
- 224 pruebas automáticas: reproducción de la operación pendiente, reintento sin duplicados, importaciones repetidas sin carpeta de carátulas, bloqueo ante cambios del catálogo y navegación por teclado.

Las pruebas usan un teléfono simulado con la interfaz del SDK instalado. Falta confirmar estos cambios por USB en el iPhone físico. No borres catalogue-backups: conserva el registro necesario para comprobar una transferencia interrumpida. Para recuperar el caso descrito, vuelve a seleccionar los mismos originales y pulsa Importar.

MP3, WAV, M4A (AAC/ALAC) y AIFF; sin FLAC. Windows necesita el servicio/controlador USB de Apple. Paquetes sin firma ni notarización. No se distribuyen fuentes ni DLL de Apple o 3uTools.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
