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
            notes.write_text('''TUPAQ 0.3.0-preview.33: nueva sección «Archivos de apps» para gestionar la carpeta Documentos de apps instaladas en el iPhone.

- Lista las aplicaciones de usuario instaladas en el iPhone que habilitan el intercambio de archivos de iOS (`UIFileSharingEnabled`) mediante `installation_proxy` y abre su carpeta `/Documents` por USB mediante `house_arrest` (`VendDocuments`).
- Permite explorar subcarpetas, subir de nivel y crear carpetas nuevas dentro de `/Documents`.
- Permite añadir archivos de cualquier tipo y carpetas completas (mediante selector o arrastrando y soltando), copiando por bloques con barra de progreso, cancelación, comprobación de tamaño y SHA-256 por lectura y sin sobrescribir archivos existentes en el iPhone.
- Permite exportar al ordenador archivos o carpetas seleccionados sin sobrescribir archivos locales existentes y sin seguir enlaces simbólicos.
- Permite eliminar archivos o carpetas dentro de `/Documents` siempre con confirmación explícita y sin permitir nunca eliminar la raíz `/Documents`.
- Verificado con pruebas automatizadas sin dispositivo físico; la prueba con un iPhone real conectado por USB queda pendiente en el equipo del usuario.

MP3, WAV, M4A (AAC/ALAC) y AIFF para Música; cualquier formato dentro de `/Documents` de apps compatibles. Windows necesita el servicio/controlador USB de Apple. Paquetes sin firma ni notarización. No se distribuyen fuentes ni DLL de Apple o 3uTools.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
