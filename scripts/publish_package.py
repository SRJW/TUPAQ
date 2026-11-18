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
            notes.write_text('''TUPAQ 0.3.0-preview.31: correcciones en el filtrado de canciones por formato.

- El filtro de formato de la biblioteca ya solo evalúa el formato real de la canción y no coincidencias parciales en título, artista o álbum (por ejemplo, canciones con «Wave», «Palace» o «Isaac» dejaban pasar MP3 al filtrar por WAV, ALAC o AAC).
- Corregida la equivalencia de variantes AIFF: ahora los archivos `AIFF-C` y `.aif` sin etiqueta de catálogo (o marcados como `PCM`) aparecen correctamente al filtrar por `AIFF`.
- Corregido el reconocimiento de contenedor `M4A` para archivos `.alac` y pistas con contenedor `M4A`.
- Cuando la inspección USB por cabecera confirma que un archivo no tiene un formato válido (`format_source='header'`), deja de mostrarse por su extensión de nombre.
- Al completarse la comprobación USB de cabecera de una fila visible, si su formato real contradice el filtro activo, la lista se vuelve a filtrar automáticamente.
- El lector del catálogo ya no marca `format_source='catalogue'` cuando `item_playback.audio_format` tiene un código no reconocido.

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
