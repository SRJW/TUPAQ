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
            notes.write_text('''TUPAQ 0.3.0-preview.15: identidad Encuentro integrada.

- Nuevo icono aprobado: formas escalonadas en naranja, marfil y ciruela.
- Aplicado en ventana, barra lateral y barra inferior. Botones y foco con acentos naranja de contraste legible.
- Icono ICO con siete tamaños incrustado en el EXE de Windows; ICNS en el paquete de Mac para Finder y Dock. Ambos se comprueban antes de publicar.
- El PNG de marca se incluye en la aplicación y se comparte entre las superficies de la interfaz. Las carátulas reales y el indicador de música sin portada se conservan.
- Se mantienen idiomas Español/English, fuentes, apariencia, biblioteca, cola y comprobaciones de transferencia. 146 pruebas y comprobación de cada ejecutable empaquetado.

Windows y Mac: no necesitas Python ni abrir iTunes. Cada paquete aparece después de pasar sus comprobaciones. Paquetes sin firma ni notarización. No se redistribuyen fuentes de Apple. La copia del catálogo no incluye todos los audios ni permite restaurarlos automáticamente. Instrucciones: docs/TRANSFERENCIAS.md.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
