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
            notes.write_text('''TUPAQ 0.3.0-preview.45: tema nativo **Apple Music** en *Preferencias → Apariencia*.

- **Nuevo estilo visual «Apple Music» (Claro, Oscuro y Sistema):** en *Preferencias → Apariencia → Estilo visual* ahora puedes alternar entre **TUPAQ** y **Apple Music**. Incluye la paleta oficial de Apple Music con acento carmesí (`#FA233B` / `#FB5C74`), superficies gris grafito (`#121214` / `#1C1C1E` en oscuro) y blanco/gris perla (`#FFFFFF` / `#F5F5F7` en claro), barra lateral estilo macOS/iPadOS con iconos acentuados y píldoras sólidas de navegación, insignias de formato/Lossless coherentes y miniaturas de vista previa adaptadas.
- Conserva todas las novedades de `v0.3.0-preview.44` (archivos de hasta 128 GB en *Archivos de apps* con verificación rápida), `v0.3.0-preview.43` (filtro por formato/tipo y agrupación en la columna **Tipo**) y anteriores.
- Verificado con 306 pruebas automatizadas y renderizado de las 5 vistas en ambos temas sin dispositivo físico; la prueba con un iPhone real conectado por USB queda pendiente en el equipo del usuario.

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
