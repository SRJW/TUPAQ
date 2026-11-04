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
            notes.write_text('''TUPAQ 0.3.0-preview.8: casillas, búsqueda por formato y eliminación confirmada.

- Corrección de import:artwork-cache-token: conserva referencias opacas/nulas de portadas y reserva los IDs numéricos, sin bloquear por formatos existentes ajenos ni reutilizar los identificadores ocupados.
- Casillas para marcar canciones, selección de visibles y contador. Las marcas se conservan al ordenar o buscar y se limpian al cambiar de dispositivo.
- Búsqueda por formato/códec: .m4a, .mp3, wav, aiff, alac… combinables con canción, artista y álbum.
- Biblioteca simplificada: sin selector Descargadas/Exportables ni columna Archivo por USB.
- Eliminar hasta 100 canciones marcadas, con confirmación y comprobación de dispositivo, biblioteca, IDs y metadatos. Usa delete_track nativo; no borra archivos de audio por AFC. Comprueba los objetivos y las canciones restantes. Función nueva pendiente de prueba física.
- Opciones avanzadas de recuperación ocultas por defecto y explicadas. La copia del catálogo no incluye todos los audios ni permite una restauración automática.
- 122 pruebas, incluidos tokens heterogéneos, casillas, formatos, cancelación, selección obsoleta, dispositivo distinto, eliminación, daño colateral y confirmación perdida.

El usuario confirmó la importación con metadatos y portada en versiones anteriores. Esta revisión se valida con bibliotecas simuladas y la interfaz empaquetada; aún necesita prueba con el iPhone. No se envía Reset ni se escribe SQLite remoto. Conserva una copia de los audios que quieras guardar antes de eliminarlos.

Windows y Mac: no necesitas Python ni abrir iTunes. Windows requiere el controlador/servicio USB de Apple. Cada paquete se publica cuando pasa sus comprobaciones. Paquetes sin firma de desarrollador ni notarización. Fuente nativa San Francisco en macOS; no se redistribuyen archivos de fuentes Apple. Instrucciones: docs/TRANSFERENCIAS.md.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
