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
            notes.write_text('''TUPAQ 0.3.0-preview.7: interfaz compacta, archivos reales y recuperación.

- Diseño inspirado en Peel: barra lateral, búsqueda, biblioteca y cola central e inspector de canción plegable. Solo Biblioteca y Preferencias.
- Oculta referencias a audios eliminados tras comprobar las carpetas USB. Conserva descargas protegidas sin ruta exportable. Nube y pendientes no aparecen como canciones descargadas.
- Duración desde catálogo o cabeceras reales; un dato desconocido se muestra como —. Formato, tamaño y columnas ordenables.
- Antes de importar revisa operaciones pendientes: un audio con ID, ruta y SHA-256 correctos permite continuar sin duplicarlo. Si falta o está dañado, conserva el bloqueo y explica la causa. Portadas/fechas pendientes se distinguen del audio.
- Fuente nativa San Francisco en macOS; Preferencias muestra la fuente real. Windows admite fuentes locales autorizadas y declara la alternativa cuando SF no está disponible. No se redistribuyen archivos de Apple por las restricciones de su licencia estándar.
- Prueba de resolución tipográfica independiente de las fuentes instaladas en cada sistema; diagnóstico de CI acotado para conservar el final del error.
- 108 pruebas y comprobación de la aplicación empaquetada, incluidas pérdida de confirmación, archivos ausentes/corruptos, duración, interfaz y tipografía.

El usuario confirmó importación con metadatos y portada. Los cambios de esta versión se validan con simulación y necesitan prueba física en el iPhone. No se envían Reset ni eliminaciones ni se escribe SQLite remoto. Conserva los registros de operaciones pendientes; la copia del catálogo no es un respaldo completo.

Windows y Mac: no necesitas Python ni abrir iTunes. Windows requiere el controlador/servicio USB de Apple. Paquetes sin firma de desarrollador ni notarización. Cada paquete aparece cuando pasa las comprobaciones de su plataforma. Instrucciones y límites: docs/TRANSFERENCIAS.md.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
