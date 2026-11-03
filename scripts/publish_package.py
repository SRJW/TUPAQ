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
            notes.write_text('''TUPAQ es el nuevo nombre de la aplicación. Corrige el error trust:SessionActiveError: se reutiliza la sesión de confianza abierta por el SDK, sin enviar una segunda solicitud StartSession ni crear un emparejamiento nuevo. Esta corrección tiene una prueba de regresión; falta verificar el resultado en el iPhone del usuario.

Interfaz nativa clara inspirada en Apple, tabla de biblioteca con celdas bajo demanda y botón Copiar diagnóstico. Incluye M4A (AAC/ALAC), portadas y lectura experimental del catálogo del iPhone.

**La importación a Música todavía no está integrada.** La lectura USB está pendiente de verificar en un iPhone físico. No hace falta instalar Python. Paquetes sin firma de desarrollador ni notarización de Apple.

Los archivos se añaden a esta versión solo después de pasar las comprobaciones de su plataforma. Si falta un EXE o DMG, esa compilación aún no terminó correctamente; consulta Actions. La disponibilidad de un paquete no depende de los otros runners.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
