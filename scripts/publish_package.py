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
            notes.write_text('''TUPAQ 0.3.0-preview.25: nuevo diseño claro/oscuro y tipografía del sistema.

- Cuatro vistas: Biblioteca, Importar, Diagnóstico y Preferencias. Superficies marfil o verde profundo, navegación horizontal de icono y texto, acentos naranjas y selección verde azulado.
- Windows y Mac usan siempre la fuente de su sistema. Se elimina la selección de Mori y cualquier selector de fuentes; tamaños en puntos, letras sin comprimir y controles calculados con métricas reales.
- Archivos y carpetas completas, cola con estado por canción, progreso real, pausa segura entre lotes/archivos e historial privado agregado.
- Filtros por formato, carátula o letra; selección persistente y acciones de importar, exportar y eliminar.
- Preferencias funcionales: carpeta inicial, política de títulos, envío de carátulas, completar carátulas en copias exportadas, idioma, acento, reducir transparencia/movimiento e importación automática opcional (desactivada inicialmente y vinculada al mismo iPhone).
- Actualización opcional al detectar cambios: sondeo de atributos DB/WAL cada 30 segundos, sin vaciar la vista ni competir con transferencias.
- Diagnóstico de conexión, catálogo, volumen de datos y lectura completa; compara hashes cuando existen recibos propios y muestra pendiente cuando no hay evidencia. No inventa salud del dispositivo ni velocidad USB.
- Formatos: MP3, WAV, M4A (AAC/ALAC) y AIFF. FLAC no se incluye.
- 215 pruebas automáticas aprobadas en desarrollo y 10.000 archivos preparados con la interfaz nueva. Las simulaciones no sustituyen una prueba USB con el iPhone físico.

Galería y alcance: docs/DISENO-25.md. Se conservan los límites y comprobaciones de las transferencias nativas. Las letras dentro de Música del iPhone siguen pendientes de validar. Los originales del ordenador se conservan; la copia del catálogo no sustituye una copia de sus audios.

No necesitas Python ni abrir iTunes. Windows necesita el servicio/controlador USB de Apple. Paquetes sin firma ni notarización. No se distribuyen fuentes de Apple ni Mori, ni DLL de Apple/3uTools.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
