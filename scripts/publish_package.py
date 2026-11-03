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
            notes.write_text('''TUPAQ 0.2.0-preview.10 corrige la causa identificada de los cero resultados: el catálogo interno usa item.media_type=8 para música, pero el lector aplicaba la máscara pública de MediaPlayer (1). Ahora tanto la consulta como los recuentos usan la igualdad con 8. La investigación y sus fuentes están en research/LECTURA-MEDIA-TYPE.md.

Se corrigieron los datos de prueba y se añadió una muestra sintética del esquema 2410000. Las 41 pruebas incluyen el caso de una canción tipo 8 presente solo en el WAL; la prueba del ejecutable lee SQLite y verifica la fila a través del hilo y la tabla Qt. Falta confirmar en el iPhone del usuario el título obtenido y la cobertura de su biblioteca.

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
