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
            notes.write_text('''TUPAQ 0.3.0-preview.4: audio/Genius y recuperación de importación pendiente.

- Admite solicitudes de audio con Genius desactivado (AssetParts 1/5). Los bits de portada/letras no preparados siguen deteniendo el envío y el diagnóstico incluye el valor numérico recibido.
- Preferencias → Completar importación pendiente usa el registro de TUPAQ y el archivo original: si la canción sigue esperando audio, intenta entregarlo sin volver a insertarla; si iOS ya retiró todas las entradas, verifica su ausencia antes de una importación nueva.
- Conserva el bloqueo de nuevas importaciones mientras haya una operación sin comprobar. Revisar importación continúa siendo una comprobación de solo lectura.
- 86 pruebas, incluida simulación con metadatos aplicados antes del manifiesto, audio/Genius, recuperación sin duplicados, fuente movida/modificada, entradas cloud, colisiones y finalización temprana. Prueba de la interfaz empaquetada y del botón de recuperación.

**La entrega de audio y la recuperación siguen siendo experimentales y no están verificadas en un iPhone físico.** La referencia también deja sin calificar la aceptación nativa de la sesión vacía para completar audio. Si se detiene, conserva los registros y copia el diagnóstico completo. No borres la biblioteca ni los respaldos para forzar otro intento.

Para el error de la preview.3: abre esta versión en el mismo ordenador, conecta el mismo iPhone, conserva el original y pulsa Preferencias → Completar importación pendiente. Si moviste el original, añádelo con Elegir canciones y vuelve a Completar. No uses Importar para reenviar la misma canción mientras haya una operación pendiente.

Mantiene importación MP3/M4A AAC-ALAC/WAV/AIFF, exportación verificada, barra lateral, temas, lectura automática y miniaturas por USB. No envía Reset, eliminaciones ni escribe SQLite en el teléfono. La copia del catálogo no es un respaldo de todos los audios ni una restauración automática. Todavía no registra las portadas separadas en Artwork de Música.

No necesitas Python ni abrir iTunes. Windows requiere el servicio/controlador USB de Apple. Paquetes sin firma de desarrollador ni notarización. Cada descarga se publica al pasar las comprobaciones de su plataforma. Instrucciones y límites: docs/TRANSFERENCIAS.md.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
