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
            notes.write_text('''TUPAQ 0.3.0-preview.42: corrección de `export_app:ConnectionTerminatedError` al copiar canciones a carpetas del iPhone.

- **Reconexión automática y modo secuencial de un solo canal:** al copiar canciones de *Música* a `/Documents` de una app de iOS, primero lee el catálogo sin mantener `house_arrest` inactivo; si iOS o el USB cierra un socket (`ConnectionTerminatedError`), cierra limpiamente ambas sesiones, pasa automáticamente a modo de un solo canal secuencial (lee una canción → cierra Música → escribe y verifica en la app → cierra la app) y reintenta la pista hasta 3 veces sin perder lo ya copiado.
- **Escrituras más estables (256 KB) y sin doble lectura USB:** reduce el tamaño de paquete AFC de escritura de 1 MB a 256 KB para evitar cortes en `house_arrest` (especialmente en Windows) y elimina la doble lectura redundante del audio por USB manteniendo verificación SHA-256 local y remota.
- **Sin límite artificial de 30 minutos** en exportaciones grandes al PC o a carpetas del iPhone, y diagnóstico detallado por etapa (`catalogue`, `open_app`, `read_audio`, `write_app`) si se desconecta el cable físicamente.
- Conserva todas las novedades de `v0.3.0-preview.41` (aviso de actualizaciones en macOS con certificados SSL) y anteriores.
- Verificado con 303 pruebas automatizadas y renderizado de las 5 vistas en ambos temas sin dispositivo físico; la prueba con un iPhone real conectado por USB queda pendiente en el equipo del usuario.

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
