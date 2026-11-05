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
            notes.write_text('''TUPAQ 0.3.0-preview.17: carátulas originales y detección de letras.

- Se elimina «Tus álbumes» del lateral.
- La vista previa utiliza la carátula original accesible, sin recorte, y muestra resolución, formato y peso de la imagen original. Vista al 100% con desplazamiento; miniaturas ligeras en la lista.
- Detección de letras incrustadas USLT/SYLT y ©lyr en MP3, WAV, AIFF y M4A; icono de texto y lectura del contenido en Detalles.
- Se distinguen letras incrustadas en el archivo, registradas en Música y disponibles en línea. La importación conserva las letras dentro del audio original, pero su visualización en Música del iPhone NO está garantizada: la parte de registro nativo sigue pendiente de validar. Consulta docs/LETRAS.md.
- Solo la selección actual conserva la imagen original y el texto. Lecturas con límites, resultados antiguos descartados y pausa antes de las transferencias.

Pruebas automatizadas y comprobación de cada paquete antes de publicarlo. No se dispone de iPhone físico en este entorno. Windows y Mac no necesitan Python ni abrir iTunes. Paquetes sin firma ni notarización; no se redistribuyen fuentes de Apple. Conserva catalogue-backups; no incluye todos los audios ni es una restauración automática.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
