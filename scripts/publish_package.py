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
            notes.write_text('''TUPAQ 0.3.0-preview.40: copia bidireccional entre la app Música del iPhone y carpetas de iOS (visibles en Archivos).

- **Música del iPhone → Carpeta del iPhone (`/Documents`):** en *Biblioteca*, el botón **Exportar** ofrece ahora **Exportar al ordenador…** y **Copiar a carpeta del iPhone…**. Permite elegir la app compatible (VLC, Documents, foobar2000, Pages, etc.), una subcarpeta opcional, organización plana o `Artista / Álbum / 01 - Canción`, política de conflictos (`Omitir` incremental, `Renombrar`, `Reemplazar`) y carátula incrustada. Copia canción por canción sin dejar archivos en tu PC, con pausa, cancelación y verificación SHA-256.
- **Carpeta del iPhone → Música del iPhone:** en *Archivos de apps*, el nuevo botón **Enviar a Música** toma los archivos de audio o carpetas seleccionadas del iPhone y los carga directamente en la cola de *Importar* (aprovechando conversión automática de FLAC/OGG/Opus/WMA, detección de duplicados y editor de metadatos/carátula), limpiando los temporales al cerrar TUPAQ y sin alterar los archivos originales en iOS.
- Conserva el resumen de peso en *Biblioteca* (`v0.3.0-preview.39`), casillas planas redondeadas (`v0.3.0-preview.38`) y el rediseño ligero completo.
- Verificado con 301 pruebas automatizadas y renderizado de las 5 vistas en ambos temas sin dispositivo físico; la prueba con un iPhone real conectado por USB queda pendiente en el equipo del usuario.

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
