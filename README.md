# Importios

Aplicación de escritorio para Windows y macOS, en español, con ventana propia.
El objetivo es importar música local a la app Música del iPhone sin usar la
aplicación iTunes ni 3uTools.

**La transferencia todavía no está integrada ni verificada en un iPhone.**
La versión actual selecciona y analiza música, consulta la detección USB y
contiene una implementación independiente de la firma de metadatos validada
con vectores sintéticos. No modifica la biblioteca del teléfono.

## Descargar y abrir

[Versiones descargables](https://github.com/SRJW/importios/releases) ·
[Instrucciones de descarga](DESCARGAR.md)

- Windows 11: abre `Importios.exe` con doble clic.
- Mac con chip Apple: abre `Importios-macOS-arm64.dmg` y copia la app a Aplicaciones.
- Mac Intel: usa `Importios-macOS-x86_64.dmg`.

No se necesita instalar Python ni abrir una terminal. La aplicación tiene una
ventana propia y no usa el navegador. Las descargas aparecen cuando GitHub
termina las compilaciones. Todavía no tienen firma de desarrollador ni
notarización de Apple.

## Funciones actuales

- Elegir o arrastrar MP3, WAV, ALAC y AIFF; comprobar el códec real.
- Leer título, artista, álbum y duración sin cambiar el original.
- Omitir duplicados por contenido, quitar elementos y exportar CSV.
- Consultar dispositivos USB mediante **ListDevices** del servicio local de Apple.
  No inicia sesiones de sincronización, emparejamientos ni escrituras al iPhone.
- Calcular firmas candidatas de 21 bytes con un protocolo de solicitud fijo,
  usando una adaptación con licencia MIT de rustunes. Cuatro vectores conocidos
  coinciden; eso no demuestra aceptación por un dispositivo real.

En Windows, la detección necesita el controlador/servicio de Apple. Tener ese
controlador no requiere abrir iTunes para usar Importios. En macOS se consulta
el servicio usbmuxd del sistema. Detectar un dispositivo no confirma la confianza,
la versión de iOS ni la compatibilidad de importación.

La lista vive en memoria y se pierde al cerrar. Los archivos permanecen en su
ubicación original; no se convierten ni se envían a Internet. Límite por archivo:
256 MB. Se necesita Internet solo para obtener el programa y, si se trabaja desde
el código fuente, instalar las dependencias.

## Desarrollo

Python 3.11 o posterior. Los usuarios de los paquetes EXE/DMG no necesitan esto.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-desktop.txt
.venv/bin/python -m importios.native
```

Windows tiene `windows/Abrir-Importios.bat` y macOS `Abrir-Importios.command`
para ejecución desde el código. La antigua interfaz web se conserva como utilidad
de desarrollo: `.venv/bin/python -m importios --no-browser`.

## Comprobaciones y compilación

```sh
.venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen .venv/bin/python -m importios.native --smoke-fixtures tests/fixtures
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python scripts/build_desktop.py
```

La suite contiene 22 pruebas de formatos, HTTP local, descubrimiento USB simulado,
paquetes de investigación y firmas candidatas. La prueba nativa comprueba una
ventana Qt real, lectura en un hilo de trabajo, los cuatro formatos, duplicados,
archivos dañados, CSV, quitar/vaciar y las firmas. En Linux se ha probado también
el ejecutable empaquetado. Windows y macOS se validan en sus runners de GitHub;
no se deben dar por aprobados hasta comprobar los resultados de cada ejecución.

GitHub compila en Windows x64, Mac Apple Silicon y Mac Intel, prueba cada paquete
y verifica/monta los DMG. Las etiquetas `v…` publican versiones preliminares con
los paquetes como Assets. Las compilaciones normales guardan artefactos 30 días.

## Investigación y atribución

- [Hallazgos de las DLL aportadas y de la implementación independiente](research/IMPLEMENTACION-INDEPENDIENTE.md).
- [Análisis inicial de 3uTools](ANALISIS-3UTOOLS.md).
- [Avisos de terceros](third_party/README.md).

Las DLL y ejecutables de Apple/3uTools no se incluyen en el proyecto ni en los
paquetes. La firma independiente no es una llamada a sus binarios ni a sus servidores.
