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
            notes.write_text('''TUPAQ 0.3.0-preview.39: peso total de la selección y de la biblioteca en el pie de Biblioteca.

- **Resumen de peso en Biblioteca:** al lado del contador de canciones y seleccionadas muestra en tiempo real el tamaño acumulado de la selección y el peso total de la biblioteca del iPhone (`Selección: X · Biblioteca: Y`, o `Biblioteca: Y` si no hay canciones marcadas). Respeta el filtro de formato activo y se actualiza automáticamente si los tamaños llegan desde el iPhone por USB.
- **Traducción ES / EN completa:** añade la traducción al inglés del resumen de peso (`Selection: X · Library: Y`), corrige la traducción del contador de canciones en la cabecera (`{count} songs`) y ordena las plantillas de `i18n` por especificidad para que ningún patrón genérico intercepte textos con `:`.
- Conserva todas las mejoras visuales de `v0.3.0-preview.38` (casillas planas redondeadas sin doble borde) y `v0.3.0-preview.37` (rediseño ligero), junto a todas las funciones de `v0.3.0-preview.36`.
- Verificado con 296 pruebas automatizadas y renderizado de las 5 vistas en ambos temas sin dispositivo físico; la prueba con un iPhone real conectado por USB queda pendiente en el equipo del usuario.

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
