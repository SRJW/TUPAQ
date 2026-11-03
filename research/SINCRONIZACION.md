# Segunda fase: flujo de importación y dependencia pendiente

Análisis estático realizado el 3 de noviembre de 2026. Se usó la misma muestra
identificada en [el informe inicial](../ANALISIS-3UTOOLS.md). Todas las direcciones
de esta página son RVA de `idm_media.dll`, salvo que se indique otra cosa.

## Resultado

Se avanzó desde la identificación del módulo hasta seguir sus llamadas: apertura
de servicios, negociación, construcción de órdenes, serialización binaria,
procesamiento mediante funciones externas, escritura de archivos y respuesta a
manifiestos. La generación completa del archivo `.cig` y la rama alternativa
siguen sin resolverse. No se ha implementado ni probado una importación a iOS.

## 1. Conexión y negociación

`ios_add_media` (`0xc6d0`) llama a `0x9110`. Dentro de esa función se pasan
`com.apple.atc` (`0x922e`) y `com.apple.afc` (`0x9290`) a `0x4620`, y se preparan
conexiones con funciones auxiliares. La semántica final de todas esas auxiliares
no está reconstruida, pero las llamadas desde el punto de entrada están verificadas.

Después llama a `0x9390` (`0xca77`):

- Comprueba mensajes con `Command` y `SyncAllowed`.
- Construye un diccionario `RequestingSync`, con `Session` y `Params`.
- En los parámetros aparecen `HostInfo`, `Dataclasses`, `DataclassAnchors`,
  `SyncHostName`, `SyncedDataclasses`, `Version`, `LibraryID` y `Grappa`.
- Envía el diccionario a través de `0x5240` (`0x95dd`).
- Recibe y comprueba `ReadyForSync` o `SyncFailed`.
- Extrae datos de `Params → DeviceInfo → Grappa` usando `plist_get_data_val`
  (`0x971b–0x9733`).

Esta secuencia está observada en el código, no capturada en una sesión real.
Los valores constantes que usa la muestra no se deben asumir adecuados para una
implementación independiente ni para una biblioteca ya existente.

## 2. Construcción de órdenes

En `0xcc76` se llama a `0xa7b0`, que crea una estructura plist. Se observa:

- Una lista de operaciones con un elemento `operation = update_db_info` y
  un diccionario `db_info`, con `audio_language`, `subtitle_language` y
  `primary_container_pid`.
- Operaciones `operation = insert_track` construidas en un bucle.
- Campos de canción como `title`, `artist`, `album`, `total_time_ms`,
  `track_number`, `track_count`, `disc_number`, `year`, `is_song`,
  `artwork_cache_id` y campos de ordenación.
- Subestructuras identificadas mediante `avformat_info`, `item_stats` y
  `location`; aparecen `bit_rate`, `audio_format` y `sample_rate`.
- Una envoltura con `timestamp`, `operations` y `revision` (`0xafe0–0xb04a`).

La lista de campos no es una especificación completa: faltan reglas para
identificadores persistentes, valores enumerados, rutas y condiciones por versión.
En `0xcc87` la estructura se serializa mediante **`plist_to_bin`**. Por tanto,
en esta ruta no se trata simplemente de escribir etiquetas XML.

## 3. Dependencia concreta de la generación del bloque adicional

La inicialización en `0x7fe0` construye rutas con `itunesDll`, `CoreFP.dll`,
`AirTrafficHost.dll` e `iTunes.dll`. Se observan cargas con `LoadLibraryW`.

En `0x82d5–0x82f8` se guardan punteros calculados como bases de módulos más
desplazamientos fijos:

| Slot dentro de idm_media.dll | Destino calculado por la muestra |
| --- | --- |
| `0x23d90` | base del módulo cargado desde la ruta de iTunes.dll + `0x10630` |
| `0x23d88` | base del módulo cargado desde la ruta de AirTrafficHost.dll + `0x6560` |
| `0x23da0` | base del módulo cargado desde la ruta de AirTrafficHost.dll + `0x8650` |

No son API públicas resueltas por nombre: estos desplazamientos dependen de las
versiones exactas de esas bibliotecas.

En la rama local de `ios_add_media`:

1. Llama indirectamente al slot `0x23da0` (`0xccbe`) con un identificador y
   un bloque que procede de la negociación anterior.
2. Llama al slot `0x23d90` (`0xcceb`) pasando el búfer plist binario y su
   longitud, además de ubicaciones para recibir un búfer de salida y su longitud.
3. Copia ese resultado a otro búfer.
4. Más adelante entrega el plist y el bloque adicional por separado a la
   auxiliar `0x2230`, con las rutas `.plist` (`0xcff9`) y `.plist.cig` (`0xd017`).

La auxiliar `0x2230` abre un archivo con modo `3`, emite una operación AFC
`0x10` con los datos y después cierra el archivo. Esto distingue estas referencias
de una simple búsqueda o eliminación de rutas.

**Hallazgo:** el bloque `.cig` en esa rama se obtiene mediante una función
externa aplicada al plist, después de preparar contexto con información de la
sesión. No se ha identificado su algoritmo: no se afirma que sea SHA-1, HMAC,
una firma concreta o un valor constante. No se debe sustituir por datos inventados.

El inventario completo de los 535 elementos extraídos no incluye archivos con
los nombres `iTunes.dll`, `AirTrafficHost.dll` ni `CoreFP.dll`. Sí incluye
`iTunesdll/libitab64.dll` y `asrp64.dll`; la equivalencia entre estos archivos y
las bibliotecas cargadas no está demostrada. Puede haber dependencias preparadas
o descargadas durante la instalación o ejecución; no se ejecutó ese proceso.

Existe además una rama alternativa en `0xcd3f`, que llama a `0xa150`, construye
paquetes y usa `0x8bd0`. El seguimiento de esta última confirma transporte HTTP
mediante `curl_easy_init`, `curl_easy_setopt` y `curl_easy_perform`.
En `0x8c51–0x8c5c` se pasa el primer argumento de la auxiliar a la opción
`CURLOPT_URL` (`10002`); en `0x8cd6–0x8cf7` se establecen `CURLOPT_POSTFIELDS`
(`10015`) y `CURLOPT_POSTFIELDSIZE` (`60`) con un paquete binario.
La URL se recibe desde el llamador, no es una constante de esta auxiliar.
No se ha establecido su hostname, si siempre es remoto o cuándo se elige esa
rama. No se realizó ninguna petición al destino. El transporte tiene opciones
de verificación TLS desactivadas en la muestra; ese comportamiento no se ha
reutilizado ni se propone para Importios.

Esto distingue dos dependencias posibles: procesamiento mediante bibliotecas
locales y procesamiento a través de un servicio HTTP. No demuestra que podamos
sustituir uno por otro ni usar el servicio de 3uTools desde nuestra aplicación.

## 4. Entrega de archivos y cierre de metadatos

Después de escribir los archivos de sincronización:

- En `0xd01f` se llama a `0xb060`, que construye y envía
  `Command = FinishedSyncingMetadata`, con `Session`, `Params`, `SyncTypes`
  y `DataclassAnchors`.
- En `0xd02a` se llama a `0xc320`, que examina `AssetManifest` y
  `SyncFinished`. Para un manifiesto, recorre `Params → AssetManifest → Media`,
  lee `AssetID` y puede construir respuestas `FileError`.
- Aparecen etapas posteriores de carga de audio/portadas bajo `/Airlock/Media/`
  y `/Airlock/Media/Artwork/`. La auxiliar `0xb1a0` lee archivos locales y
  escribe bloques usando operaciones AFC.

No se ha reconstruido la máquina de estados completa, la correlación de todos
los identificadores ni el tratamiento de cancelaciones y recuperación. Estos
puntos importan para conservar una biblioteca existente.

## Validación de esta entrega

- Se ejecutó `inspect_media.py` sobre la DLL extraída y se guardó
  `media-evidence.json` con referencias y llamadas por región.
- Se comprobó que la herramienta rechaza una muestra alterada, para evitar
  aplicar direcciones fijas a una versión diferente.
- Las conclusiones sobre las llamadas indirectas y sus búferes se contrastaron
  leyendo las instrucciones y sus registros, no solo buscando cadenas.
- Ninguna prueba de esta fase envió datos a un dispositivo ni ejecutó código de 3uTools.

## Límite actual y continuación

Hay dos tareas concretas pendientes: identificar las versiones de los módulos
que usa la rama local para seguir sus funciones internas y reconstruir el contrato
del procesamiento alternativo HTTP. Ambas son investigación adicional; copiar las DLL o llamar
sus funciones con parámetros adivinados no resuelve la compatibilidad.

Antes de integrar un escritor en Importios hacen falta una especificación
suficiente del intercambio, generación legítima del bloque adicional y una prueba
controlada en un dispositivo/biblioteca de ensayo. **No se ha demostrado soporte
para iOS 27 ni se necesita usar la biblioteca personal del usuario en esta fase.**
