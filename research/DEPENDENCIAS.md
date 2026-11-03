# Tercera fase: destino HTTP y límite de la muestra disponible

## Resultado concreto

Se siguió el argumento de URL desde tres llamadas de `3uTools.exe` a
`ios_add_media`. En esos puntos la aplicación usa la función de RVA `0x72b370`
para preparar una dirección. Se identificaron estas constantes:

| RVA en 3uTools.exe | Contenido |
| --- | --- |
| `0x12b2390` | `https://a1-s.3u.com` |
| `0x12b23a8` | `https://a2-s.3u.com` |
| `0x12b23c0` | `?pc_vs=` |
| `0x12b1420` | `9.09.009` |

En los puntos examinados se pasa cero al selector de la función, que toma
la segunda dirección. La función también usa el getter de versión en RVA
`0x727bc0`. Esta es una reconstrucción estática de la preparación de URL:
no demuestra disponibilidad actual, autorización ni comportamiento del servidor.
**No se enviaron peticiones a esos destinos.**

La llamada a `ios_add_media` de RVA `0x7e842c` recibe esa cadena como séptimo
argumento, preparado en `[rsp+0x30]`. También se observó la misma preparación
en los llamadores de RVA `0x7c316c` y `0x8055ee`.

## Sobre del protocolo HTTP

La auxiliar de transporte en `idm_media.dll`, RVA `0x8bd0`, calcula un CRC de
16 bits sobre el cuerpo. Se comprobó que las 256 entradas de su tabla, en RVA
`0x1bbb0`, coinciden con CRC-16/XMODEM (polinomio `0x1021`, inicio cero).
El bucle actualiza el acumulador desplazándolo a la izquierda ocho bits y
usando el byte alto XOR el siguiente byte como índice de la tabla.

| Offset del paquete | Tamaño | Interpretación observada |
| --- | --- | --- |
| 0 | 4 | Magic `0x35467891`, little endian |
| 4 | 1 | Tipo de mensaje |
| 5 | 1 | Campo dependiente del tipo; no se asume que siempre sea un estado |
| 6 | 2 | CRC del cuerpo, little endian |
| 8 | 4 | Longitud del cuerpo, little endian |
| 12 | variable | Cuerpo |

La rama de procesamiento prepara tipo `0xd0` (RVA `0xa1af`), espera tipo
`0xd1` (`0xa3a4–0xa3aa`) y lee una longitud de cuatro bytes al comienzo del
cuerpo, seguida del resultado opaco (`0xa3ac–0xa3d8`). El resultado termina
en el búfer que la ruta principal entrega a la escritura de `.cig`.
La respuesta `0xc9` tiene un código leído en el byte 5 (`0xa3ff–0xa403`).

Esto describe el transporte de un resultado, **no el algoritmo que lo genera**.
El CRC detecta errores del paquete; no sustituye el bloque `.cig` ni demuestra
autenticidad de su contenido.

## Código añadido y comprobaciones

- `inspect_support.py`: comprueba las huellas de los dos módulos, extrae las
  constantes por RVA, contrasta toda la tabla CRC y verifica la presencia de las
  bibliotecas de soporte en el árbol extraído.
- `support-evidence.json`: resultado de ejecutar esa inspección sobre la muestra.
- `packet.py`: lector independiente y exclusivamente local de paquetes de ese
  formato. Comprueba longitud, magic y CRC, y puede leer un resultado opaco de
  tipo `0xd1`. No contiene cliente HTTP ni genera archivos `.cig`.
- Seis pruebas nuevas con paquetes sintéticos: vector CRC conocido, lectura de
  un resultado, corrupción, truncamientos, bytes sobrantes, límites y tipos
  inesperados. Sumadas a las seis pruebas de la aplicación: **12 pruebas pasadas**.

No se han capturado paquetes reales de una importación ni probado este lector
contra respuestas reales del servidor. Los tests verifican la implementación
local del formato reconstruido; no la compatibilidad con el servidor o con iOS.

## Qué falta para continuar con la generación

La muestra contiene el cliente que consume el resultado y prepara la sesión.
La ruta local delega parte del trabajo en funciones de versiones concretas de
`iTunes.dll` y `AirTrafficHost.dll`, y prepara una ruta a `CoreFP.dll`.
La comprobación automatizada corrigió el inventario de la fase anterior:
**sí existe `itunesFlashDll/AirTrafficHost.dll`**. No aparecen `iTunes.dll` ni
`CoreFP.dll`. El cargador estudiado construye rutas bajo `itunesDll`, por lo que
no está demostrado que use la copia de `itunesFlashDll`.

La copia encontrada es x64, con SHA-256
`0cc9d950b8d7cad674cf7e568f4b0887dfa86bebc583f39aab483e47c925bf0a`.
Exporta `ATHostConnectionGetGrappaSessionId`,
`ATHostConnectionSendMetadataSyncFinished` y `ATHostConnectionSendSyncRequest`.
Se inspeccionaron sus regiones en RVA `0x6560` y `0x8650`, pero no se ha
establecido que correspondan a los puntos de entrada que espera `idm_media.dll`.
La presencia de esta DLL no resuelve la ausencia de la función que la ruta local
obtiene desde `iTunes.dll + 0x10630`.

Se revisó además `iTunesdll/libitab64.dll`: exporta `buyapp`, `get_region`,
`libitab_free`, `login` y `logout`, y tiene contenido Go. No se ha identificado
como sustituto de las funciones locales anteriores. `libitunesfix.dll` exporta
funciones de reparación/controladores; su presencia tampoco aporta el algoritmo.

**El siguiente insumo necesario para seguir esa ruta es la copia exacta de los
componentes cargados desde `itunesDll` por una instalación de 3uTools**, junto con sus versiones y
huellas. No basta con descargar DLL arbitrarias con los mismos nombres: las
llamadas observadas usan desplazamientos fijos dentro de los módulos.

Si esos componentes no existen en la instalación, hará falta observar en un
entorno Windows de prueba cómo se selecciona o prepara el soporte de sincronización.
No hay un entorno Windows de análisis conectado a esta tarea. Instalar 3uTools
en el ordenador personal o sincronizar la biblioteca del usuario no es requisito
de esta investigación estática.

## Estado de Importios

El procesamiento remoto no se ha utilizado y el algoritmo local no está en los
archivos disponibles. Por tanto, no se ha integrado un escritor al iPhone.
La compatibilidad con iOS 27 sigue sin demostrarse. No se ha modificado ninguna
biblioteca musical ni se han redistribuido módulos de 3uTools.
