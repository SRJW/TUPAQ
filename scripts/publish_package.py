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
            notes.write_text('''TUPAQ 0.3.0-preview.38: casillas de selección modernas, planas y nítidas en toda la aplicación.

- **Corrección visual en tablas (sin doble borde 3D):** elimina el doble pintado que dibujaba el indicador QSS debajo del `SelectionDelegate` y creaba un marco hundido en las casillas de *Biblioteca*, *Importar* y *Archivos de apps*.
- **Casillas planas con esquinas redondeadas (estilo macOS / Linear):** cuadro de 16×16 px con radio de 4.5–5 px, contorno uniforme y suave con realce al pasar el ratón, relleno terracota sólido sin halo gris al marcar y marca `✓` antialias con puntas redondeadas.
- **Coherencia en toda la app:** aplica el mismo estilo de casillas a los controles `QCheckBox` (*Seleccionar todo*, *Preferencias*, *Diagnóstico*) y a la vista de tarjetas *Álbumes / Artistas* (`QListWidget`), tanto en modo claro como en modo oscuro.
- Incluye todo el rediseño ligero de `v0.3.0-preview.37` y las funciones completas de `v0.3.0-preview.36`.
- Verificado con 295 pruebas automatizadas y renderizado de las 5 vistas en ambos temas sin dispositivo físico; la prueba con un iPhone real conectado por USB queda pendiente en el equipo del usuario.

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
