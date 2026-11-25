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
            notes.write_text('''TUPAQ 0.3.0-preview.43: filtro por formato/tipo de archivo y agrupación por tipo en **Archivos de apps**.

- **Columna «Tipo» con formato real y agrupación al ordenar:** la tabla de *Archivos de apps* muestra ahora el formato específico de cada elemento (`Archivo MP3`, `Archivo FLAC`, `Archivo PDF`, `Carpeta`, etc.) y permite agrupar todos los archivos por tipo/extensión al pulsar la cabecera **Tipo**.
- **Selector de filtro por formato/tipo en Archivos de apps:** nuevo desplegable junto al buscador (`Todos los tipos`) que lista dinámicamente las categorías y extensiones presentes en la carpeta abierta con su conteo (`Carpetas (N)`, `Audio (N)`, cada extensión como `MP3 (N)`, `FLAC (N)` y `Sin extensión (N)`), combinable en tiempo real con la búsqueda por texto y con traducción inmediata Español / English.
- Conserva todas las novedades de `v0.3.0-preview.42` (reconexión automática y modo secuencial de un solo canal al copiar canciones a carpetas del iPhone) y anteriores.
- Verificado con 304 pruebas automatizadas y renderizado de las 5 vistas en ambos temas sin dispositivo físico; la prueba con un iPhone real conectado por USB queda pendiente en el equipo del usuario.

MP3, WAV, M4A (AAC/ALAC) y AIFF nativos para Música (más conversión opcional de FLAC/OGG/Opus/WMA vía `ffmpeg`); cualquier formato dentro de `/Documents` de apps compatibles. Windows necesita el servicio/controlador USB de Apple. Paquetes sin firma ni notarización. No se distribuyen fuentes ni DLL de Apple o 3uTools.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
