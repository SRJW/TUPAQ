# TUPAQ

Antes llamado Importios. El código interno conserva el módulo `importios` y el repositorio actual.

Aplicación de escritorio para Windows y macOS, en español, con ventana propia.
El objetivo es importar música local a la app Música del iPhone sin usar la
aplicación iTunes ni 3uTools.

**La transferencia todavía no está integrada ni verificada en un iPhone.**
La versión actual selecciona y analiza música, incluye lectura USB del catálogo y
contiene una implementación independiente de la firma de metadatos validada
con vectores sintéticos. No modifica la biblioteca del teléfono.

![Ventana nativa de TUPAQ con audio sintético de prueba](docs/interfaz-nativa.png)

## Descargar y abrir

[Versiones descargables](https://github.com/SRJW/importios/releases) ·
[Instrucciones de descarga](DESCARGAR.md)

- Windows 11: abre `TUPAQ.exe` con doble clic.
- Mac con chip Apple: abre `TUPAQ-macOS-arm64.dmg` y copia la app a Aplicaciones.
- Mac Intel: usa `TUPAQ-macOS-x86_64.dmg`.

No se necesita instalar Python ni abrir una terminal. La aplicación tiene una
ventana propia y no usa el navegador. Las descargas aparecen cuando GitHub
termina la compilación de cada plataforma. Todavía no tienen firma de desarrollador ni
notarización de Apple.

## Funciones actuales

- Interfaz nativa clara inspirada en Apple, con tipografía del sistema. Sin motor web, animaciones ni sondeos periódicos.
- Tabla de biblioteca con celdas dibujadas bajo demanda, sin crear un objeto por celda.
- Errores de conexión por etapa y botón **Copiar diagnóstico**, también cuando la consulta devuelve cero resultados. Incluye versión, recuentos por tipo y presencia/tamaño del WAL, sin títulos ni credenciales ni identificadores del dispositivo.
- Las canciones sin fila de metadatos complementarios se muestran como «Sin título» en lugar de descartarse.

- Elegir o arrastrar MP3, WAV, M4A (AAC o ALAC) y AIFF; comprobar el códec real.
- Miniaturas de portadas incrustadas, en la lista y en el panel de preparación.
  Sin portada se muestra una nota musical; todavía no hay una transferencia real.
- Leer título, artista, álbum y duración sin cambiar el original.
- Omitir duplicados por contenido, quitar elementos y exportar CSV.
- Consultar dispositivos USB mediante **ListDevices** del servicio local de Apple.
  No inicia sesiones de sincronización, emparejamientos ni escrituras al iPhone.
- **Leer biblioteca del iPhone**: usa la autorización de confianza existente y AFC
  para obtener dos copias consecutivas del catálogo y su WAL. Si no coinciden,
  rechaza la lectura. Consulta una copia local con SQLite en modo de solo lectura
  y muestra título, artista, álbum y duración. No escribe en la biblioteca remota.
  Esta ruta no se ha probado todavía con un iPhone físico.
- Calcular firmas candidatas de 21 bytes con un protocolo de solicitud fijo,
  usando una adaptación con licencia MIT de rustunes. Cuatro vectores conocidos
  coinciden; eso no demuestra aceptación por un dispositivo real.

En Windows, la detección necesita el controlador/servicio de Apple. Tener ese
controlador no requiere abrir iTunes para usar TUPAQ. En macOS se consulta
el servicio usbmuxd del sistema. Detectar un dispositivo no confirma la confianza,
la versión de iOS ni la compatibilidad de importación.

La lista vive en memoria y se pierde al cerrar. Los archivos permanecen en su
ubicación original; no se convierten ni se envían a Internet. Límite por archivo:
256 MB. Se necesita Internet solo para obtener el programa y, si se trabaja desde
el código fuente, instalar las dependencias.

## Recursos de la interfaz

La interfaz usa Qt Widgets nativo y carga el componente de comunicación con iOS
al solicitar la biblioteca. No tiene motor de navegador ni consulta el teléfono
en bucle. La tabla del catálogo conserva sus filas y dibuja celdas bajo demanda.
Se prueba el acceso a la primera y última canción de una lista sintética de
100.000 filas.

Medición orientativa en Linux, desde el código, con Qt offscreen y ventana vacía:
76,9 MiB RSS y 0 % CPU durante una muestra de tres segundos en reposo.
No es una medición del EXE/DMG en Windows/macOS ni del coste de cargar una
biblioteca; ese consumo aún debe medirse en esos equipos.

## Desarrollo

Python 3.11 o posterior. Los usuarios de los paquetes EXE/DMG no necesitan esto.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-desktop.txt
.venv/bin/python -m importios.native
```

Windows tiene `windows/Abrir-TUPAQ.bat` y macOS `Abrir-TUPAQ.command`
para ejecución desde el código. La antigua interfaz web se conserva como utilidad
de desarrollo: `.venv/bin/python -m importios --no-browser`.

## Comprobaciones y compilación

```sh
.venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen .venv/bin/python -m importios.native --smoke-fixtures tests/fixtures
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python scripts/build_desktop.py
```

La suite contiene 41 pruebas de formatos, HTTP local, descubrimiento USB simulado,
paquetes de investigación y firmas candidatas. La prueba nativa comprueba una
ventana Qt real, lectura en un hilo de trabajo, los AAC/ALAC dentro de M4A, portadas, duplicados,
archivos dañados, CSV, quitar/vaciar y las firmas. En Linux se ha probado también
el ejecutable empaquetado. Windows y macOS se validan en sus runners de GitHub;
no se deben dar por aprobados hasta comprobar los resultados de cada ejecución.

GitHub compila en Windows x64, Mac Apple Silicon y Mac Intel, prueba cada paquete
y verifica/monta los DMG. Cada paquete se publica de forma independiente cuando
pasa sus comprobaciones; una plataforma fallida puede quedar sin descarga. Los pushes a `main` y las ejecuciones manuales compilan la app. Las etiquetas
`v…` publican versiones preliminares con
los paquetes como Assets. Las compilaciones normales guardan artefactos 30 días.

## Investigación y atribución

- [Corrección de cero canciones: código interno de MediaLibrary frente a MediaPlayer](research/LECTURA-MEDIA-TYPE.md).

- [Hallazgos de las DLL aportadas y de la implementación independiente](research/IMPLEMENTACION-INDEPENDIENTE.md).
- [Análisis inicial de 3uTools](ANALISIS-3UTOOLS.md).
- [Avisos de terceros](third_party/README.md).

Las DLL y ejecutables de Apple/3uTools no se incluyen en el proyecto ni en los
paquetes. La firma independiente no es una llamada a sus binarios ni a sus servidores.
