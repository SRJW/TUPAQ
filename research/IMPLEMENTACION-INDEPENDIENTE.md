# Cuarta fase: componentes recibidos y cálculo independiente

## Archivos aportados

Se reconstruyeron `itunesDll.zip.001` a `.004` en orden numérico. El ZIP pasó
la verificación CRC y contiene 23 entradas, incluyendo el directorio. Se
extrajeron los archivos sin ejecutarlos. Las versiones y SHA-256 de los tres
componentes principales se guardaron en `uploaded-support-evidence.json`.

| Componente | Versión indicada | Arquitectura |
| --- | --- | --- |
| AirTrafficHost.dll | 17.492.0.29 | x86, 32 bits |
| iTunes.dll | 12.1.0.71 | x86, 32 bits |
| CoreFP.dll | 2.7.50 | x86, 32 bits |

Se inspeccionaron las entradas de iTunes.dll en RVA `0x10630` y de
AirTrafficHost.dll en RVA `0x6560` y `0x8650`. En esta muestra hay prólogos de
función en esos puntos. Eso no demuestra por sí solo las firmas de sus argumentos.
El código contiene saltos indirectos y flujos ofuscados; no se ha reconstruido
el algoritmo completo siguiendo estas DLL. Tampoco se pueden cargar DLL x86
directamente en un proceso x64; la muestra de idm_media.dll anterior era x64.
No se ha intentado hacerlo ni se ha construido un puente que ejecute las DLL.

Se encontraron nombres de resolución dinámica `WIn9UJ86JKdV4dM`, `X46O5IeS` y
`YlCJ3lg` en iTunes/AirTrafficHost, que coinciden con exportaciones de CoreFP.
No se ha establecido el grafo completo ni el contrato de esas funciones.

## Vía independiente encontrada

Se revisó el proyecto público [fbiba/rustunes](https://github.com/fbiba/rustunes),
commit `057ee8fc9c9da65795a6f14497fc408c2fe23c76`, con licencia MIT.
Su biblioteca `music-protocol` documenta una solicitud de host fija y una firma
candidata implementada con AES-CBC, AES-ECB y HMAC-SHA1, sin DLL de Apple ni
servicio HTTP de 3uTools. Documentación relevante:

- `crates/music-protocol/src/protocol/signing.rs`
- `docs/02-atc-sync-protocol.md`, sección 11.4
- `crates/music-protocol/tests/fixtures/grappa-fixed-vectors.plist`

La documentación de ese proyecto declara pruebas de importación a Música en un
iPhone 16 Pro Max con iOS 27.0.1 y 27.2 desde Linux. **Son afirmaciones y
resultados del proyecto original, no pruebas ejecutadas por Importios.**
El proyecto es Linux-only; no se ha incorporado su CLI como si funcionara ya en
Windows/macOS. Parte de su gestión de archivos usa interfaces POSIX específicas.

## Implementación realizada en Importios

`importios/sync/signing.py` es una adaptación Python del firmador MIT, con su
atribución y licencia. No se copió código del proyecto sin licencia go-tunes.
Se usó PyCryptodomex para AES y la biblioteca estándar para HMAC-SHA1.
La solicitud fija es exactamente la publicada por rustunes; se rechaza cualquier
otra solicitud o respuesta que no tenga la envoltura admitida.

La implementación:

1. Acepta una respuesta de sesión de 83 bytes, con prefijo `01 01` y byte 18 `40`.
2. Descifra su bloque de 64 bytes con AES-CBC según el contrato fijo publicado.
3. Deriva la clave de la sesión usando AES-ECB y las transformaciones publicadas.
4. Calcula el bloque de 21 bytes sobre los **bytes exactos** de los metadatos.
5. Permite cerrar la sesión e impide firmar después de cerrarla.

No imprime claves ni respuestas y no persiste material derivado. Python no
permite garantizar que se borren todas las copias de memoria al cerrar una sesión.
No autentica la respuesta ni soporta las otras solicitudes del software de Apple.

## Validación ejecutada

- Cuatro vectores sintéticos del proyecto original: los cuatro resultados de
  21 bytes coinciden exactamente.
- SHA-256 de los 84 bytes de solicitud coincide con el contrato publicado.
- Rechazo de modificaciones de cada byte de solicitud y de envolturas no admitidas.
- Rechazo de operaciones vacías y mayores de 4 MiB.
- Diferencia entre firmas de metadatos con finales de línea o bytes diferentes.
- Rechazo de uso posterior al cierre de la sesión.
- Suite completa de Importios: **22 pruebas pasadas**, incluyendo las anteriores
  y las pruebas de audio, protocolo HTTP local, USB simulado y análisis de paquetes.

Son pruebas sin dispositivo. El resultado demuestra que se reprodujo la fórmula
publicada; no demuestra aceptación por un iPhone ni completa la importación.

## Interfaz y paquetes

Se implementó una ventana nativa Qt para Windows y macOS. El punto de entrada
`desktop.py` ya no abre el navegador. Lee música en un hilo de trabajo, permite
exportar CSV y consultar dispositivos mediante el servicio USB local. La consulta
solo envía `ListDevices`: no inicia una sincronización ni escribe al teléfono.

El ejecutable empaquetado se comprobó en Linux y GitHub compila y prueba cada
plataforma de destino. La prueba de cada paquete abre una ventana Qt en modo
sin pantalla y comprueba selección, metadatos, duplicados, errores, CSV,
quitar/vaciar y los cuatro vectores del firmador. No equivale a una prueba manual
con el iPhone del usuario.

## Lo que sigue pendiente del objetivo completo

Ya no falta una fórmula candidata independiente para el bloque de metadatos.
Sí faltan la implementación e integración de la sesión completa: autorización de
servicios, lectura del catálogo, preservación de identidad y anclas vigentes,
órdenes de inserción, subida del audio/portada, cierre, lectura de verificación
y recuperación ante fallos. El firmador solo cubre una parte de ese proceso.

La interfaz no ofrece una importación ficticia ni llama al servicio de 3uTools.
La importación completa a Música en un iPhone 13 Pro con iOS 27 **no se ha
implementado ni verificado**. El entorno de esta tarea es Linux, sin acceso al
USB del ordenador del usuario ni a un teléfono de ensayo. No se usará la
biblioteca personal para experimentar ni se dará el objetivo por terminado.
