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
            notes.write_text('''TUPAQ 0.3.0-preview.34: exportación estricta por formato sin archivos colados y selector de selección más claro.

- Impide que al exportar con un formato seleccionado (`MP3`, `M4A`, `AAC`, `ALAC`, `WAV` o `AIFF`) se cuelen canciones de otro formato:
  - El lector del catálogo (`library_fields.format_label`) y el filtro (`search.format_aliases`) ya no confían en códigos `audio_format` del catálogo cuando contradicen la extensión real del archivo en el iPhone.
  - Al pulsar **Exportar** con un filtro de formato activo, TUPAQ solo exporta canciones marcadas de ese formato y nunca arrastra canciones ocultas marcadas previamente de otros formatos.
  - Durante la exportación (`export_selected`), TUPAQ comprueba tanto la extensión como la cabecera y los bytes reales del audio (diferenciando incluso `AAC` frente a `ALAC` dentro de `.m4a` y archivos con extensión engañosa) antes de guardar cada copia; si un archivo no coincide con el formato seleccionado, se omite sin escribirse en la carpeta de destino y se actualiza su formato real en la tabla.
- Renombra la casilla «Seleccionar visibles» a una etiqueta clara y contextual: «Seleccionar todo» sin filtros, «Seleccionar todos los MP3» (o el formato activo) al filtrar por formato, y «Seleccionar resultados» al buscar o filtrar por carátula/letra, con traducción al inglés y texto de ayuda.
- Verificado con pruebas automatizadas sin dispositivo físico; la prueba con un iPhone real conectado por USB queda pendiente en el equipo del usuario.

MP3, WAV, M4A (AAC/ALAC) y AIFF para Música; cualquier formato dentro de `/Documents` de apps compatibles. Windows necesita el servicio/controlador USB de Apple. Paquetes sin firma ni notarización. No se distribuyen fuentes ni DLL de Apple o 3uTools.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
