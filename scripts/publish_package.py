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
            notes.write_text('''TUPAQ 0.3.0-preview.37: rediseño estético ligero en todas las pantallas (claro y oscuro).

- **Biblioteca ligera (+40% más canciones visibles):** reemplaza la tarjeta alta del dispositivo y los botones de ancho completo por una cabecera compacta de una sola fila (`Biblioteca`, píldora inline del iPhone y acciones proporcionadas), y unifica el control segmentado encapsulado **Canciones | Álbumes | Artistas** en la misma fila que el buscador y los filtros.
- **Menos bordes y mejor jerarquía tipográfica:** títulos de canción en peso medio, artista/álbum en tono secundario suave, divisoras horizontales muy sutiles, acento terracota limpio con contraste WCAG AA en modo claro (`#c44f08`), fondo más limpio y pie lateral simplificado sin doble marco.
- **Diagnóstico en cuadrícula 2×2 sin recortes:** identidad del dispositivo inline en cabecera, **Almacenamiento** y **Batería** (barra verde-petróleo) lado a lado arriba, **Comprobaciones** (insignias compactas) y **Conexión USB / formatos** abajo, con **Copiar diagnóstico** y **Opciones avanzadas** siempre visibles sin scroll.
- **Importar con una sola acción principal:** el botón naranja se adapta dinámicamente (`Elegir archivos…` si la cola está vacía; `Importar al iPhone` cuando hay canciones listas), zona de arrastre más esbelta e insignias de estado (`StatusBadgeDelegate`) en la cola (`Preparada`, `Ya en el iPhone`, `Convertida`).
- Conserva intactas todas las funcionalidades de `v0.3.0-preview.36` (aviso de actualizaciones, Archivos de apps con buscador/renombrar/conflictos, salud real de batería, conversión opcional de FLAC con `ffmpeg`, exportación organizada/incremental >1.000 canciones, duplicados, editor de metadatos/portada, playlists `.m3u8`, vista por Álbumes/Artistas y vista previa de audio).
- Verificado con 295 pruebas automatizadas y renderizado de las 5 vistas en ambos temas sin dispositivo físico; la prueba con un iPhone real conectado por USB queda pendiente en el equipo del usuario.

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
