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
            notes.write_text('''TUPAQ 0.3.0-preview.18: estado USB claro y diagnóstico de letras de solo lectura.

- Punto verde cuando se detecta un iPhone por USB; gris al desconectarlo, si el servicio USB falla o si se conectan varios dispositivos. El color funciona en los temas claros/oscuros y en español/inglés.
- Las respuestas tardías de una lectura anterior ya no vuelven a mostrar conectado un dispositivo retirado, ni repueblan su biblioteca.
- El diagnóstico compara, solo en la copia local, hasta 32 textos con hipótesis CRC32/Adler32. Devuelve únicamente recuentos; no copia letras, identificadores ni valores privados al informe.
- Se conserva la detección y lectura de letras incrustadas. Mostrarlas dentro de Música del iPhone sigue pendiente de validar; esta versión no activa una entrega experimental de letras.

Pruebas automatizadas y comprobación de cada paquete antes de publicarlo. Windows y Mac no necesitan Python ni abrir iTunes. Paquetes sin firma ni notarización; no se redistribuyen fuentes de Apple. Conserva catalogue-backups.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
