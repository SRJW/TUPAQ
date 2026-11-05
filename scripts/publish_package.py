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
            notes.write_text('''TUPAQ: numeración opcional compatible, lotes grandes comprobados e interfaz tonal.

- Corregido import:metadata-numbering: los totales de pistas o discos sin una posición, o menores que ella, ya no detienen la importación. Se conserva la posición válida y se omite el total incoherente solo en los datos del envío; no se reescribe el archivo original. Se prueban MP3, WAV, AIFF, M4A ALAC y AAC y un envío de 51 canciones en dos lotes.

- Importar y eliminar hasta 50.000 canciones por selección, divididas en transacciones nativas de hasta 49 y 100 canciones respectivamente. Cada lote se comprueba antes del siguiente; una cancelación o un error detiene el resto.
- Prueba de 10.000 importaciones y 10.000 eliminaciones en un iPhone simulado; también 1.000 archivos mezclados con portadas y 10.000 archivos preparados en la interfaz. Corregidas colisiones de rutas dentro del mismo lote y acumulación de trabajo en la interfaz.
- 196 pruebas automáticas aprobadas en la revisión de desarrollo. Estos resultados no sustituyen una prueba USB con un iPhone físico ni garantizan cero fallos. Informe y reproducción en docs/ESTRES.md.

- Composición completamente renovada: navegación compacta, tarjeta protagonista del iPhone, tres acciones grandes y biblioteca a todo el ancho. Detalles abre una ventana secundaria; se elimina la tercera columna permanente.
- Contraste del botón principal comprobado sobre su imagen renderizada al pasar el cursor, en claro y oscuro.
- Modo Tonal verde azulado, espaciado y radios amplios, estados vacíos con acciones y preferencias organizadas en tarjetas.
- Transiciones breves al navegar, respuesta de controles y mezcla de carátulas sin cuadros vacíos. Reducir movimiento detiene todo inmediatamente y se conserva entre aperturas. Sin animaciones decorativas continuas; la biblioteca no se desvanece al actualizar.
- Zona de arrastre visible: los archivos van a la cola y no se importan automáticamente. Atajos habituales para buscar y abrir canciones.
- Windows usa PP Mori instalada automáticamente: Regular, Medium, SemiBold y Bold. Se eliminan el selector de fuentes, Agregar y Aplicar. Mac conserva la fuente del sistema.
- Mori tiene licencia personal: sus archivos no se incluyen en estos paquetes. Extrae tu Mori.zip, instala los cuatro pesos desde Windows y vuelve a abrir TUPAQ. Si falta, se usa y se identifica la fuente del sistema. Instrucciones en docs/INTERACCION.md.
- Corregida la prueba de tipografía de macOS para reconocer .AppleSystemUIFont como alias de San Francisco. No se sustituye la fuente del sistema.
- Creación del DMG más robusta: reintentos limitados para errores temporales de recursos al verificar y desmontar la imagen de solo lectura; nunca se omite su verificación.
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
