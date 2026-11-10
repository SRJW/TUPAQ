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
            notes.write_text('''TUPAQ 0.3.0-preview.28: carátulas verificadas correctamente y desplegables sin marco antiguo.

- Corregida una regresión: iOS puede usar tipo 1 para el token de la canción y tipo 6 para su imagen. Ya no se exige una igualdad incorrecta entre ambos tipos.
- La carátula transferida se verifica por su identificador de caché local exacto y sus bytes, independientemente de la portada preferida para mostrar. Una imagen corrupta sigue sin aceptarse.
- Las operaciones afectadas por el fallo anterior pueden comprobarse mediante lectura sin reenviar ni duplicar canciones. Se conservan los respaldos.
- Ventana desplegable sin borde nativo rectangular y con máscara redondeada; comprobación adicional de HWND y teclado en Windows real.
- Retiradas las explicaciones sobre la fuente. Windows y Mac continúan usando su fuente del sistema.
- «Comprobar todo» se aclara como «Comprobar lectura de audios»: es opcional, solo lee, puede tardar y no se ejecuta al importar.
- 231 pruebas aprobadas en desarrollo; documentación de alternativas de importación en docs/CORRECCIONES-28.md.

Para un envío ya realizado con preview.27, actualiza y usa Revisar operación pendiente, o vuelve a seleccionar los mismos originales: se comprueba el resultado antes de reenviar. Conserva catalogue-backups. Una copia de catálogo no sustituye una copia de los audios. La prueba por USB en el iPhone físico sigue pendiente.

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
