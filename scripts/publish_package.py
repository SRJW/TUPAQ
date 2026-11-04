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
            notes.write_text('''TUPAQ 0.3.0-preview.12: cristal, cancelación y confirmación de importaciones sucesivas.

- Composición inspirada en las referencias de Apple Music: portada grande, acciones a su derecha, paneles translúcidos, álbumes en la barra lateral y barra inferior integrada. Nocturno, Aurora y Atardecer en Preferencias. Fondo atmosférico en caché, sin motor web ni desenfoque continuo.
- Cancelar importación antes de enviar cambios; cancelar exportación conservando archivos completos y eliminando el temporal parcial. Si Música ya recibe metadatos, se finaliza y verifica el lote actual completo: no es una interrupción inmediata ni una reversión.
- Corregida una carrera que rechazaba confirmaciones rápidas durante el último FileComplete o guardado local. Se conservan el rechazo de confirmaciones prematuras y la verificación del catálogo y audio.
- Lectura del catálogo cambiante: hasta tres intentos, dos lecturas coincidentes y una copia conservada. Mensajes separados para lectura, operaciones pendientes y envío. No se borra el historial para desbloquear.
- Solo se resuelve un registro anterior a cambios cuando catálogo y ausencia de todos sus destinos lo demuestran. Los estados ambiguos siguen bloqueados.
- Biblioteca visible durante actualización. Casillas, orden, búsqueda por formato y eliminación con confirmación. Windows: fuente global mediante Aplicar; Mac: fuente nativa del sistema.
- 142 pruebas, incluidas cinco importaciones consecutivas simuladas, cancelación y confirmación rápida, más comprobación de cada aplicación empaquetada.

El usuario confirmó importaciones con metadatos y portada en revisiones anteriores. Estas correcciones se validan en simulación y necesitan comprobación con el dispositivo; no puede atribuirse con certeza el fallo histórico sin su diagnóstico. No borres catalogue-backups: sus registros permiten comprobar operaciones pendientes.

Windows y Mac: no necesitas Python ni abrir iTunes. Cada paquete aparece después de pasar las comprobaciones de su plataforma. Paquetes sin firma ni notarización. No se redistribuyen fuentes de Apple. La copia del catálogo no incluye todos los audios ni permite restaurarlos automáticamente. Instrucciones: docs/TRANSFERENCIAS.md.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
