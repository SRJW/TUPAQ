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
            notes.write_text('''TUPAQ 0.3.0-preview.36: nueve nuevas funcionalidades de música, archivos de apps, diagnóstico de batería y comodidad general.

- **Aviso de actualizaciones:** comprueba GitHub Releases (`SRJW/TUPAQ`) al abrir la app o bajo demanda desde Preferencias y muestra un aviso con botón para abrir la descarga oficial en el navegador (nunca descarga ejecutables automáticamente).
- **Archivos de apps mejorados:** añade buscador en vivo dentro de `/Documents`, botón y atajo `F2` para renombrar archivos o carpetas, y selector de política de conflictos (`Si existe: Omitir / Renombrar / Reemplazar`) al copiar o exportar.
- **Salud real de la batería en Diagnóstico:** lee la telemetría real `IOPMPowerSource` vía `DiagnosticsService` (salud real en %, ciclos de carga, capacidad máxima vs. diseño en mAh, carga actual, temperatura en °C y voltaje en V).
- **Conversión automática de FLAC (y OGG/Opus/WMA/MKA/WebM) al importar:** activa desde Preferencias la conversión al vuelo mediante `ffmpeg` hacia `M4A · ALAC` (sin pérdida) o `M4A · AAC` (256 kbps), conservando metadatos, portada y letra sin tocar jamás los archivos originales.
- **Exportación organizada, sin límite de 1.000 canciones e incremental:** elige entre exportar todo en una carpeta o en estructura `Artista/Álbum/01 - Canción.ext`, amplía el límite de exportación hasta 50.000 canciones y añade modo respaldo incremental para omitir lo ya exportado sin crear duplicados `(2)`.
- **Detector de duplicados:** señala en la cola de importación qué canciones ya están en el iPhone (`Ya en el iPhone` + botón `Quitar repetidas`) y añade el filtro «Posibles duplicados» en la Biblioteca.
- **Editor de metadatos y portada antes de importar:** corrige título, artista, álbum, artista del álbum, género, año, pista/disco o elige una portada personalizada directamente en la cola sin alterar tus archivos originales del ordenador.
- **Playlists (`MediaLibrary.sqlitedb` + `.m3u8`):** lee las listas de reproducción del iPhone para filtrar y exportar una playlist completa en su orden exacto junto a su archivo `.m3u8`.
- **Vista por Álbumes / Artistas y vista previa de audio:** alterna entre `Canciones`, `Álbumes` y `Artistas` para marcar o filtrar discos/artistas completos al instante, y reproduce una vista previa de audio desde el panel de Detalles.
- Verificado con pruebas automatizadas (294 tests, incluida conversión real de FLAC con `ffmpeg`) y renderizado en ambos temas sin dispositivo físico; la prueba con un iPhone real conectado por USB queda pendiente en el equipo del usuario.

MP3, WAV, M4A (AAC/ALAC) y AIFF nativos para Música (más conversión opcional de FLAC/OGG/Opus/WMA vía `ffmpeg`); cualquier formato dentro de `/Documents` de apps compatibles. Windows necesita el servicio/controlador USB de Apple. Paquetes sin firma ni notarización. No se distribuyen fuentes ni DLL de Apple o 3uTools.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
