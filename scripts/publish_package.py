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
            notes.write_text('''TUPAQ 0.3.0-preview.5: biblioteca unificada, recuento local, columnas y portadas.

- Solo Biblioteca y Preferencias en la barra lateral. Importar/exportar y la cola del ordenador comparten una página.
- Descargadas por defecto; Todo el catálogo conserva nube y pendientes. Incluye descargas protegidas de Apple Music. No fusiona canciones por título; evita referencias repetidas al mismo archivo.
- Formato y tamaño, con verificación de cabeceras/stat por USB para filas visibles. Cabeceras clicables y ordenación numérica sin perder la selección.
- Nuevas importaciones: portada JPEG separada con registro Artwork, entrega antes del audio y comprobación posterior. Fechas UTC para incorporación; se comprueba date_added.
- Preferencias → Actualizar portadas y fecha: para canciones ya importadas con registros de TUPAQ en este ordenador y originales coincidentes. Envía solo metadatos y JPEG; no duplica filas ni reenvía audio. Hasta 49 canciones por lote.
- 98 pruebas y comprobación de la aplicación empaquetada. Incluye nube/local, descargas protegidas, selección al ordenar, formatos reales, entrega de portada, fechas y actualización sin reinsertar canciones.

El usuario confirmó la incorporación básica a Música con la preview.4. **Las nuevas portadas, fechas y actualizaciones pasan replay de protocolo y aún deben comprobarse en el iPhone físico**, incluida su aparición visual en Recientes. Si se detiene una operación, conserva los respaldos y copia el diagnóstico.

No se envía Reset, eliminaciones ni se escribe SQLite en el teléfono. Una operación pendiente sigue bloqueando importaciones. La copia del catálogo no es un respaldo completo ni una restauración automática. No se inventan carátulas para archivos sin portada.

Windows y Mac: no necesitas Python ni abrir iTunes. Windows requiere el controlador/servicio USB de Apple. Paquetes sin firma de desarrollador ni notarización. Cada paquete se publica al pasar las pruebas de su plataforma. Instrucciones y límites: docs/TRANSFERENCIAS.md.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
