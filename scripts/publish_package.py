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
            notes.write_text('''TUPAQ 0.3.0-preview.41: corrección del aviso de nuevas versiones en macOS.

- **Certificados SSL incluidos en macOS (y Windows):** empaqueta los certificados raíz de `certifi` dentro de `TUPAQ.app` y carga también `/etc/ssl/cert.pem` de macOS en `build_ssl_context()`, corrigiendo el error silencioso `CERTIFICATE_VERIFY_FAILED` que impedía comprobar GitHub Releases desde el paquete compilado de Mac.
- **Aviso visible en todas las pantallas:** el banner de nueva versión aparece ahora en la parte superior de cualquier pestaña (*Biblioteca*, *Importar*, *Archivos de apps*, *Diagnóstico* o *Preferencias*), no solo en *Biblioteca*.
- **Verificación en el ejecutable real:** la prueba `smoke` en GitHub Actions valida ahora dentro del `.app` montado de macOS (Apple Silicon e Intel) y del `.exe` de Windows que el almacén de certificados raíz esté cargado (`x509_ca > 0`).
- Conserva todas las novedades de `v0.3.0-preview.40` (copia bidireccional Música ↔ carpetas de iOS), `v0.3.0-preview.39` (peso total de selección y biblioteca) y el rediseño completo.
- Verificado con 302 pruebas automatizadas y renderizado de las 5 vistas en ambos temas sin dispositivo físico; la prueba con un iPhone real conectado por USB queda pendiente en el equipo del usuario.

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
