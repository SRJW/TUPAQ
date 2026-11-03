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
            notes.write_text('''TUPAQ 0.3.0-preview.3: corrección de import:host-anchor-ahead.

Se elimina una comparación incorrecta del contador guardado en el catálogo de host. RequestingSync continúa usando el contador actual de SQLite, que debe coincidir con ReadyForSync. Se conserva la segunda captura previa al delta y la comprobación posterior: el contador del host nunca sustituye al actual y no se envía Reset.

El error host-anchor-ahead de la preview.2 ocurría antes de anunciar metadatos o enviar audio. No borres tu biblioteca ni los registros para probar esta corrección.

Mantiene la interfaz y funciones de la preview.2:

- Barra lateral organizada, apariencia Sistema/Claro/Oscuro y preferencias guardadas.
- Detección del iPhone y lectura automática de su biblioteca al conectarlo.
- Miniaturas de la biblioteca por USB, con lecturas parciales y caché limitada.
- Corrección de la restricción de cabecera fija que provocaba import:host-catalogue-layout. Se mantiene la validación contra la biblioteca actual; si el formato sigue sin admitirse, el diagnóstico añade tamaños/versiones sin datos privados.
- 73 pruebas y comprobación de la interfaz empaquetada, incluida conexión simulada y ambos temas.

Conserva la importación y exportación experimental por USB:

- Importar al iPhone: MP3, M4A AAC/ALAC, WAV y AIFF en perfiles admitidos, sin convertir los originales; miniatura y progreso.
- Delta ATC firmado con la identidad existente, copia local previa del catálogo y verificación posterior de las canciones y sus archivos. No envía un reset ni escribe SQLite en el teléfono.
- Exportar selección: copia los originales accesibles por USB, verifica sus bytes y evita sobrescribir archivos existentes. Un original protegido conserva su protección.
- Revisar importación: comprueba una operación cuya confirmación se perdió; bloquea nuevos envíos mientras quede una operación sin verificar.

**La lectura del catálogo ya fue confirmada por el usuario. Las transferencias todavía no se han validado en un iPhone físico.** Pasan pruebas con un dispositivo simulado y la prueba de la interfaz empaquetada. La copia del catálogo no es un respaldo completo del teléfono ni una restauración automática.

Importación: hasta 49 archivos y 2 GiB por operación; 256 MiB por archivo. Requiere identidad de biblioteca configurada, anclas/preferencias compatibles y área de sincronización vacía. Si falta esa información, se detiene sin enviar un delta. No se registra todavía la portada en el catálogo de Artwork; los bytes de las portadas incrustadas se conservan en el archivo.

No necesitas Python ni abrir iTunes. Paquetes sin firma de desarrollador ni notarización de Apple. Cada paquete se añade solo cuando pasa las comprobaciones de su plataforma. Instrucciones y límites: docs/TRANSFERENCIAS.md.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
