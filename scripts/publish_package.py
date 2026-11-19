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
            notes.write_text('''TUPAQ 0.3.0-preview.35: pase completo de coherencia visual en las cinco pantallas (claro y oscuro).

- **Importar:** corrige el recorte del título «Formatos compatibles» y del chip `ALAC`, y alinea con el mismo ancho calculado las dos tarjetas de la columna derecha («Formatos compatibles» y «Sincronización») en español e inglés.
- **Navegación y temas:** unifica el estado activo del menú lateral y del submenú de Preferencias en modo claro y oscuro (fondo petróleo coherente + indicador lateral en el acento de TUPAQ), y actualiza la miniatura del tema «Sistema» a una vista partida mitad clara / mitad oscura.
- **Cabeceras y Diagnóstico:** añade subtítulo coherente a Biblioteca, elimina el botón redundante de Diagnóstico en su barra superior, compacta la píldora de estado USB en Diagnóstico y añade el detalle de transporte en la tarjeta de Conexión USB.
- **Tablas coherentes:** añade insignias de formato tipo chip (`FormatBadgeDelegate`) en Biblioteca y Cola de importación, esquinas redondeadas en miniaturas de carátulas, icono contenedor suave cuando falta portada y alineación tipográfica consistente (formatos centrados; duración, tamaño y fecha alineados a la derecha).
- **Archivos de apps:** incorpora barra de migas de pan clicables (`Documentos › …`), icono de flecha arriba en «Subir nivel» y contador de elementos/selección integrado en la barra de ruta.
- **Barra de estado contextual:** adapta el mensaje inferior a la sección abierta cuando no hay ninguna transferencia activa.
- Verificado con pruebas automatizadas y renderizado de vistas en ambos temas sin dispositivo físico; la prueba con un iPhone real conectado por USB queda pendiente en el equipo del usuario.

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
