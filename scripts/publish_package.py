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
            notes.write_text('''TUPAQ 0.3.0-preview.16: diseño Estudio y verificación de metadatos.

- Nueva distribución de tres columnas basada en la referencia elegida: dispositivo y navegación, biblioteca central y panel derecho con carátula y propiedades. Identidad Encuentro y acento naranja.
- Estudio usa tonos neutros. Se conservan los otros estilos, fuente e idioma. Detalles permite ampliar la tabla; las acciones se reorganizan en ventanas pequeñas. Se mantienen casillas, búsqueda, orden y cola en la misma página.
- Frecuencia, bits y tasa de bits se muestran solo con datos disponibles; las cabeceras se leen dentro del presupuesto anterior. No se añaden controles ficticios de reproducción o edición.
- Corrección del falso fallo reproducido con acentos NFC/NFD visualmente idénticos. No cambia los originales ni lo enviado. Mayúsculas, espacios, acentos diferentes y audio corrupto siguen rechazándose.
- Si los metadatos aún no coinciden, hasta tres lecturas finales permiten comprobar una actualización tardía. No se reenvía música y se conservan las capturas y verificaciones.
- Revisar operación pendiente comprueba el envío existente sin duplicarlo. El diagnóstico identifica campos sin revelar sus valores y se conserva tras actualizar la biblioteca.
- 154 pruebas y comprobación de cada aplicación empaquetada, incluidos iconos de Windows y Mac, interfaz y transferencia simulada.

El usuario confirmó que la canción aparece en Música tras el error de preview.15. Sin el archivo ni las diferencias exactas no puede confirmarse la causa de ese caso. Primero usa Preferencias → Mostrar opciones avanzadas de recuperación → Revisar operación pendiente. Si aún quedan metadatos por revisar, copia el diagnóstico completo de esta versión. Conserva catalogue-backups.

Windows y Mac: no necesitas Python ni abrir iTunes. Cada paquete aparece después de pasar sus comprobaciones. Paquetes sin firma ni notarización. No se redistribuyen fuentes de Apple. La copia del catálogo no incluye todos los audios ni permite restaurarlos automáticamente. Instrucciones: docs/TRANSFERENCIAS.md.
''', encoding='utf-8')
            created = subprocess.run(['gh','release','create',tag,'--repo',repo,'--title',
                'TUPAQ '+tag,'--notes-file',str(notes),'--prerelease','--verify-tag'])
            # Another successful platform can create the release concurrently.
            if created.returncode:
                subprocess.run(view, check=True)
    subprocess.run(['gh','release','upload',tag,str(package),'--repo',repo,'--clobber'], check=True)


if __name__ == '__main__':
    main()
