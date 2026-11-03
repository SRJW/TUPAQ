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
            notes.write_text('''TUPAQ 0.2.0-preview.9: permite copiar el diagnóstico también al obtener cero resultados. El informe incluye recuentos del catálogo, tipos de contenido y presencia/tamaño del WAL, sin títulos de canciones ni credenciales ni identificadores del dispositivo. La ventana muestra la versión.

Las canciones sin metadatos complementarios ya no se descartan silenciosamente. Hay pruebas de ese caso, de resultados vacíos y de cambios confirmados que solo existen en el WAL copiado. Aún no se ha identificado la causa exacta de los cero resultados del iPhone del usuario ni confirmado la lectura completa.

**La importación a Música todavía no está integrada.** La lectura completa está pendiente de confirmar en el iPhone. No hace falta instalar Python. Paquetes sin firma de desarrollador ni notarización de Apple.

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
