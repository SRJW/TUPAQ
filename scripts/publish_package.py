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
            notes.write_text('''TUPAQ 0.3.0-preview.19: interfaz tonal, interacciones cuidadas y tipografía fija.

- Composición completamente renovada: navegación compacta, tarjeta protagonista del iPhone, tres acciones grandes y biblioteca a todo el ancho. Detalles abre una ventana secundaria; se elimina la tercera columna permanente.
- Modo Tonal verde azulado, espaciado y radios amplios, estados vacíos con acciones y preferencias organizadas en tarjetas.
- Transiciones breves al navegar, respuesta de controles y mezcla de carátulas sin cuadros vacíos. Reducir movimiento detiene todo inmediatamente y se conserva entre aperturas. Sin animaciones decorativas continuas; la biblioteca no se desvanece al actualizar.
- Zona de arrastre visible: los archivos van a la cola y no se importan automáticamente. Atajos habituales para buscar y abrir canciones.
- Windows usa PP Mori instalada automáticamente: Regular, Medium, SemiBold y Bold. Se eliminan el selector de fuentes, Agregar y Aplicar. Mac conserva la fuente del sistema.
- Mori tiene licencia personal: sus archivos no se incluyen en estos paquetes. Extrae tu Mori.zip, instala los cuatro pesos desde Windows y vuelve a abrir TUPAQ. Si falta, se usa y se identifica la fuente del sistema. Instrucciones en docs/INTERACCION.md.
- Se conservan las funciones de música, selección, orden, importación/exportación y sus comprobaciones. Las letras dentro de Música del iPhone siguen pendientes de validar.

Pruebas automatizadas y comprobación de cada paquete antes de publicarlo. No necesitas Python ni abrir iTunes. Paquetes sin firma ni notarización. No se redistribuyen fuentes de Apple ni Mori con licencia personal.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
