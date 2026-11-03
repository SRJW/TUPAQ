# Investigación del catálogo que devolvía cero canciones

## Resultado

El diagnóstico recibido de TUPAQ 0.2.0-preview.9 contenía un registro de tipo
8 en `item`, esquema 2410000 y un WAL presente. TUPAQ lo descartaba con
`(item.media_type & 1) != 0`. Ese filtro confundía dos representaciones distintas:
la máscara pública de MediaPlayer y el código interno del catálogo MediaLibrary.
Es un error del lector. Las pruebas anteriores tenían el mismo error en sus
datos sintéticos: daban a una canción el tipo 1.

La versión 0.2.0-preview.11 selecciona `item.media_type = 8`, por igualdad,
en la consulta y en todos los recuentos de música. No aplica una máscara de bits
ni acepta cualquier tipo como canción. El informe expone el código/comparación
empleados y conserva los recuentos de todos los tipos para investigar diferencias.

## Fuentes contrastadas

1. [Cabecera pública de MediaPlayer, SDK iOS 18.0, MPMediaItem.h](https://github.com/xybp888/iOS-SDKs/blob/master/iPhoneOS18.0.sdk/System/Library/Frameworks/MediaPlayer.framework/Headers/MPMediaItem.h#L19).
   Es una copia de la cabecera del SDK, alojada en un repositorio de terceros.
   Declara `MPMediaTypeMusic = 1 << 0`. Esto describe la API pública, no la
   columna interna `item.media_type` del catálogo de iOS 27.
2. [Lector de catálogo de rustunes, commit 057ee8fc, línea 1700](https://github.com/fbiba/rustunes/blob/057ee8fc9c9da65795a6f14497fc408c2fe23c76/crates/music-protocol/src/catalogue/sqlite.rs#L1700).
   Exige `media_type == 8` para la música local que sincroniza. Su lista de
   versiones verificadas incluye 2410000. Son resultados del proyecto original,
   no pruebas físicas ejecutadas en este entorno.
3. [Datos de prueba del mismo proyecto](https://github.com/fbiba/rustunes/blob/057ee8fc9c9da65795a6f14497fc408c2fe23c76/crates/music-protocol/src/test_support/catalogue.rs#L100)
   y [documentación del catálogo](https://github.com/fbiba/rustunes/blob/057ee8fc9c9da65795a6f14497fc408c2fe23c76/docs/04-media-library-database.md).
   Las canciones usan tipo 8; la documentación identifica la misma ruta
   `iTunes_Control/iTunes/MediaLibrary.sqlitedb`, sus compañeros WAL y el
   tipo 8 de las canciones en los contadores de las listas.
4. [libgpod, commit 4a8a33ef, itdb_sqlite.c](https://github.com/fadingred/libgpod/blob/4a8a33ef4bc58eee1baca6793618365f75a5c3fa/src/itdb_sqlite.c#L941).
   Se revisó como contraste histórico. Es código de 2011, usa un esquema distinto
   y escribe `media_kind` desde `track->mediatype` (canción 1, audiolibro 8).
   No confirma los códigos de `item.media_type` del esquema moderno. Aplicar
   esas equivalencias al catálogo de iOS 27 repetiría la confusión.

La coincidencia del diagnóstico con la ruta, esquema y tipo de la referencia
moderna permite corregir un fallo concreto sin cambiar de transporte. No hay
evidencia en este informe de que sea necesario otro emparejamiento, una ruta
alternativa, ejecutar DLL de 3uTools o reparar el catálogo.

## Verificación de la corrección

- Se añadió `tests/fixtures/library-ios27.sql`, una reducción sintética del
  esquema relevante, con versión 2410000 y una canción de tipo 8. No contiene
  metadatos del usuario. Las columnas y el tipo se contrastaron con la referencia.
- Al corregir los datos de prueba **antes** del lector, la suite del catálogo
  produjo siete fallos, incluidos dos subcasos. El caso de un único tipo 8
  reprodujo el resultado incorrecto: `music_items = 0`.
- Después de corregir el filtro, las 41 pruebas pasaron. Comprueban título,
  artista, álbum, duración, exclusión de valores no admitidos y conservación
  de música sin una fila complementaria de metadatos.
- Una prueba crea una base con un único registro de tipo 8 que existe solo en
  el WAL confirmado. Simula AFC, copia base y WAL dos veces y verifica una
  canción devuelta y cuatro aperturas exclusivamente en modo `r`.
- La prueba del ejecutable construye el catálogo de referencia y lo lee con
  SQLite en el hilo de biblioteca, entrega el resultado por la señal Qt y
  comprueba la fila visible y el diagnóstico. El servicio USB sigue simulado.

## Límites

El informe del usuario demuestra que la versión anterior accedió a un catálogo
legible y encontró un registro. El nuevo filtro debe incluir ese tipo de
registro. No demuestra por sí solo que ese catálogo represente toda la biblioteca
visible en Música ni que la importación esté implementada. Debe comprobarse el
título devuelto en el teléfono/ordenador del usuario. Este entorno no tiene
acceso USB físico a su iPhone. No se han realizado escrituras en el dispositivo.
