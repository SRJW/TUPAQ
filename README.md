# Importios

Programa en desarrollo para preparar música local con el objetivo de importarla
a la app Música del iPhone desde Windows o macOS.

## Descargar para Windows o Mac

GitHub Actions está configurado para generar **Importios.exe** y discos **DMG**
para Mac con chip Apple e Intel. Estas distribuciones incluyen Python y sus
dependencias; el usuario no tiene que instalarlo ni ejecutar comandos.
Consulta [DESCARGAR.md](DESCARGAR.md) para descargar desde GitHub.

Cada compilación prueba los cuatro formatos y ejecuta la aplicación empaquetada
antes de subirla. En macOS también verifica y abre el ejecutable del DMG montado.
Las etiquetas `v…` publican los paquetes en Releases como versiones preliminares.
Los paquetes aún no tienen firma de desarrollador ni notarización de Apple.

## Qué funciona en esta versión

- Selección múltiple y arrastre de archivos MP3, WAV, ALAC y AIFF.
- Comprobación del formato real, incluyendo ALAC dentro de archivos `.m4a`.
- Lectura de título, artista, álbum, duración y características del audio.
- Detección de duplicados por contenido y exportación de la lista en CSV.
- Análisis local con copias temporales que se eliminan después de cada lectura.

**No transfiere canciones, no detecta dispositivos desde la interfaz y no modifica
la biblioteca del iPhone.** La transferencia a Música en iOS 27 sigue pendiente de
investigación y prueba. El EXE es portátil y el DMG contiene la aplicación para
copiarla a Aplicaciones; su disponibilidad depende del resultado de GitHub Actions.

## Ejecutar desde el código (solo para desarrollo)

Esta versión de desarrollo necesita Python 3.10 o posterior y el lanzador `py`
de [python.org](https://www.python.org/downloads/windows/).

1. Guarda el proyecto completo en una carpeta y extrae el ZIP si corresponde.
2. Abre `windows/Abrir-Importios.bat` con doble clic.
3. En el primer inicio se prepara una instalación local y se descarga Mutagen
   desde PyPI. Hace falta Internet para ese paso.
4. Se abrirá la interfaz en tu navegador. No hace falta conectar el iPhone.
5. Para detener el programa, pulsa **Cerrar Importios** en la interfaz.

El lanzador no requiere permisos de administrador. La ejecución real del lanzador
en Windows aún está pendiente de validar; las pruebas actuales se ejecutan en Linux.

## macOS y Linux

Con Python 3.10 o posterior, desde la carpeta del proyecto:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m importios
```

En macOS también se incluye `Abrir-Importios.command`, pendiente de probar allí.

## Privacidad y límites

La aplicación escucha solo en `127.0.0.1` y no envía canciones a Internet.
El navegador entrega cada archivo seleccionado al proceso local para analizarlo.
Los originales no se modifican. La lista vive en la memoria de la página y se
pierde al recargarla o cerrarla; se puede guardar como CSV. Límite por archivo:
256 MB. No se convierte el audio ni se muestran portadas en esta versión.

## Pruebas

Las pruebas usan audio sintético real de un segundo incluido en `tests/fixtures`.
Comprueban los cuatro formatos, metadatos, huellas de duplicados,
rechazo de AAC y archivos dañados, y peticiones HTTP a la aplicación.

```sh
.venv/bin/python -m unittest discover -s tests -v
```

La prueba adicional de navegador necesita FFmpeg, Chromium y las dependencias de desarrollo:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m tests.browser_smoke
```

Se ha validado en Linux: seis pruebas automatizadas y un recorrido en Chromium
que añade los cuatro formatos, omite duplicados, muestra errores, exporta CSV,
quita canciones y vacía la lista.

Consulta [VIABILIDAD.md](VIABILIDAD.md) para el estado de la integración con iOS.
