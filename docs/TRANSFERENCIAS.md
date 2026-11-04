# Transferir audio con TUPAQ 0.3

La lectura del catálogo fue confirmada por el usuario con 0.2.0-preview.11.
La importación y la exportación son nuevas y experimentales: se han probado con
un dispositivo simulado y con la interfaz real empaquetada, aún no con un iPhone
físico. No hace falta instalar Python ni abrir iTunes. Windows necesita el servicio
y controlador USB de Apple que ya permite leer la biblioteca.

## Importar del ordenador a Música

1. Conecta un solo iPhone por USB y desbloquéalo.
2. Entra en **Inicio** o **Importación USB**. Usa **Elegir canciones** o arrastra los archivos a TUPAQ.
3. En la lista del ordenador, selecciona las canciones y pulsa **Importar al
   iPhone**. Sin selección se usa toda la cola. Se admiten hasta 49 archivos y
   2 GiB por operación, con un máximo de 256 MiB por archivo.
4. Espera a que termine el envío y su comprobación. La miniatura cambia con la
   canción actual. Al finalizar se vuelve a leer la biblioteca.

Los archivos importados con éxito se quitan de la cola. Los originales del
ordenador no se modifican. Un archivo que TUPAQ ya haya importado y conserve
intacto en la misma biblioteca se omite tras comprobar su recibo y su hash.
Esto no es una búsqueda universal de duplicados de otras aplicaciones.

Perfiles implementados: MP3 Layer III (MPEG-1/2/2.5, hasta 48 kHz y 320 kb/s,
mono/estéreo); M4A con ALAC (16/20/24/32 bits, mono/estéreo) o AAC con código
MP4 admitido; WAV PCM entero y AIFF/AIFF-C NONE/sowt de 8/16/24 bits,
mono/estéreo. Los perfiles fuera de esos límites se rechazan antes del envío.
No hay conversión. Para MP3 no se inventan campos de duración/gapless: se usa
la forma sin esos campos del protocolo para que iOS interprete el archivo.

La portada incrustada se conserva dentro del original y se muestra en TUPAQ.
La versión actual no registra un asset separado de portada en Artwork de iOS;
no garantiza que Música muestre esa portada después de importar.

## Exportar del iPhone al ordenador

1. Conecta el iPhone: su biblioteca se carga automáticamente. Puedes entrar en **Biblioteca** o pulsar **Actualizar** para releerla.
2. Selecciona filas con archivo accesible en la columna **Archivo por USB**.
3. Pulsa **Exportar selección** y elige una carpeta del ordenador.
4. Espera a que finalice la comprobación. Los archivos se guardan con artista y
   título; los caracteres incompatibles se sustituyen y los nombres repetidos
   reciben un sufijo. No se sobrescriben archivos existentes.

El catálogo puede contener una canción sin un archivo accesible por AFC. Tener
metadatos o una descarga dentro de Música no garantiza que iOS exponga el audio
por ese servicio. Se aceptan rutas del catálogo dentro de Music/Fnn, Purchases
o Downloads, con comprobaciones de ruta y extensión. No se recorre el sistema
de archivos privado. Los paquetes HLS no se reconstruyen como M4A.

Un original `.m4p` accesible puede copiarse como tal: conserva su protección.
No se descifra DRM ni se promete reproducir ese original fuera de los equipos
autorizados. La exportación no envía operaciones ATC ni modifica el iPhone.

## Copia del catálogo y operaciones pendientes

Antes de importar se guardan dos copias coincidentes del catálogo y su WAL,
las preferencias y el catálogo de host usados para obtener la identidad y las
anclas existentes. En **Preferencias**, **Ver respaldo del catálogo** abre su carpeta local de datos de TUPAQ.
Es información privada de la biblioteca; no es un respaldo de todos los audios
ni del teléfono completo. No existe una restauración automática de esa copia.

También se conserva un `journal.json` con la fase, hashes, destinos y datos
necesarios para comprobar la operación. No guarda claves de emparejamiento,
respuestas Grappa ni claves del firmador. Estos archivos se conservan al cerrar;
el botón de diagnóstico no copia su contenido.

Si la confirmación final se pierde, una nueva importación queda bloqueada. Usa
**Preferencias → Revisar importación pendiente** para leer nuevamente la biblioteca y comprobar canciones
y hashes sin reenviar los metadatos ni el audio. Si no puede comprobarse, copia
el diagnóstico. No borres el registro para forzar otro envío: una operación
parcial no debe confundirse con una importación que no ocurrió.

## Protocolo y comprobaciones

La implementación Python adapta mecanismos MIT de
[rustunes 057ee8fc](https://github.com/fbiba/rustunes/tree/057ee8fc9c9da65795a6f14497fc408c2fe23c76),
sin ejecutar su CLI ni DLL de Apple/3uTools. Usa framing ATC LE con plists
binarios, el intercambio Grappa ya implementado y operaciones `insert_track`
precedidas por `update_db_info` con los identificadores existentes.

La identidad sale de iTunesPrefs existentes, no de un identificador de biblioteca
nuevo. La ancla Media sale de SQLite y debe coincidir con ReadyForSync; la ancla
VoiceMemo se conserva desde el catálogo de host y solo se admite el perfil 1
calificado en la referencia. Se adquiere el lock AFC de sincronización y se
comprueba que el área de operaciones esté vacía. Una diferencia detiene el envío;
no se sustituye por ResetSync.

Antes de enviar las operaciones se vuelven a comprobar catálogo y preferencias.
La operación y su firma se escriben y verifican antes de anunciarlas. Se valida
todo el manifest antes de completar audio o rechazar assets auxiliares. Solo se
rechazan assets de artwork/Genius de canciones previamente conocidas; no audio
ajeno ni identificadores desconocidos.

Cada audio se sube al Airlock, se verifica por lectura y SHA-256, se renombra y
se completa mediante ATC. Se espera SyncFinished. Después se comprueba el avance
del ancla, los IDs wire frente a `item_store.sync_id` (no `item_pid`), los nuevos
metadatos/rutas, los bytes permanentes y la conservación de canciones anteriores.
SQLite solo abre copias locales; nunca se abre la base del iPhone para escribir.

El código no envía eliminaciones ni reset de la biblioteca. Esto no reemplaza
la validación física de un protocolo privado: un fallo, desconexión o cambio de
catálogo puede dejar una operación pendiente. No se reintenta automáticamente.

## Validación disponible

Las 86 pruebas incluyen replay de importación de los cinco perfiles base,
originales conservados, exportación byte por byte, nombres existentes,
rechazo por cambio de ancla, identidad sin configurar, manifest desconocido,
audio permanente alterado, interrupción después de aplicar cambios, verificación
sin reenvío y omisión de una transferencia previamente completada.

La prueba de la ventana empaquetada comprueba selección, botones, lock local,
hilo de transferencia, señales, progreso y miniatura con un transporte simulado.
Estas pruebas no demuestran que el iPhone del usuario acepte la primera sesión
ATC; esa comprobación debe hacerse ejecutando el paquete nuevo con el teléfono.

## Error `import:host-catalogue-layout`

La preview.1 exigía una cabecera de exactamente 244 bytes y una versión menor
concreta para iTunesDB/iTunesCDB. La preview.2 recorre las secciones desde la
longitud de cabecera declarada (con límites), admite contenedores comprimidos
y reconcilia los identificadores y anclas con el catálogo SQLite actual. No
inventa identidades ni omite las comprobaciones de sincronización. Los dos
catálogos de host pueden tener anclas Media guardadas distintas. Desde la
preview.3, ese valor no se compara numéricamente con el actual: la operación
utiliza el de SQLite, que debe coincidir con ReadyForSync.

Se probó el flujo completo con cabecera alternativa y ancla de host anterior
en un teléfono simulado. No se dispone de la cabecera real del teléfono del
usuario, por lo que aún no confirma que resuelva su caso particular. Si sigue
fallando, **Copiar diagnóstico** incluye tamaños, versiones y compresión
del contenedor, sin su contenido ni sus identificadores privados.

## Miniaturas y conexión automática

Preferencias permite escoger Sistema/Claro/Oscuro y activar la detección
automática. Esta consulta ListDevices cada cinco segundos y lee el catálogo
al detectar una conexión nueva, sin iniciar importaciones. Las lecturas se
serializan con las transferencias. Las portadas se cargan para las filas visibles,
primero desde Artwork/Originals con rutas validadas y después desde tags
MP3/M4A/WAV/AIFF acotados a 8 MiB. Los datos de audio se saltan por posición;
no se envía música a Internet. Una portada ausente, protegida o inaccesible usa
un icono musical. La caché mantiene hasta 256 miniaturas de 96 px.

## Error `import:host-anchor-ahead`

La preview.2 rechazaba el catálogo de host si su contador Media superaba
el de la biblioteca actual. Esa relación no está justificada: iTunesCDB/iTunesDB
son copias del estado del host, y no determinan la ancla actual del servicio
de sincronización. La preview.3 elimina esa condición y conserva estas barreras:

- La identidad del catálogo de host debe coincidir con SQLite y las preferencias existentes.
- VoiceMemo conserva el perfil admitido (1); no se sustituye ni se resetea.
- RequestingSync usa la ancla de SQLite. ReadyForSync debe devolver exactamente ese valor.
- Se vuelve a capturar el catálogo después de ReadyForSync y antes de escribir el delta; debe conservar identidad, ancla y canciones.
- El delta usa la ancla actual + 1; después se verifica el catálogo y los archivos. Nunca se envía Reset.

Pruebas: contador guardado menor, igual, mayor y máximo u32; contadores distintos
en iTunesCDB/iTunesDB; respuesta del teléfono distinta incluso si coincide con
el contador adelantado del host; cambio de catálogo después de ReadyForSync;
identidad y perfil VoiceMemo incompatibles. Los últimos casos siguen deteniendo
el envío antes de escribir los metadatos o el audio. Son pruebas simuladas;
la corrección aún debe comprobarse en el iPhone del usuario.

El error específico `host-anchor-ahead` de la preview.2 se produce en la
comprobación previa: no se ha anunciado un delta ni enviado audio. No hay que
borrar la biblioteca ni los registros para probar la versión corregida.

Referencias independientes MIT: [ATC, anclas de host y actuales](https://github.com/fbiba/rustunes/blob/057ee8fc9c9da65795a6f14497fc408c2fe23c76/docs/02-atc-sync-protocol.md),
sección 6; [vinculación del CDB para inserciones](https://github.com/fbiba/rustunes/blob/057ee8fc9c9da65795a6f14497fc408c2fe23c76/crates/rustunes/src/engine/execution/native_insert.rs),
`bind_copied_cdb`. La referencia no impone la desigualdad que causaba este rechazo.

## Canción atenuada y `import:manifest-own-parts`

La preview.3 exigía que el manifiesto pidiera exclusivamente audio (AssetParts 1).
El protocolo también contempla audio con el bit de Genius desactivado (5).
La preview.4 admite exactamente 1/5. Continúa rechazando portadas, letras y bits
desconocidos cuando no se han declarado ni preparado esos componentes. No
envía FileError para el audio propio ni inventa archivos para satisfacer bits.
El diagnóstico anterior no incluía el número solicitado, por lo que no permite
confirmar cuál pidió este iPhone. Si es otro valor, el nuevo diagnóstico lo incluye
como `asset_parts`, sin títulos ni identificadores privados.

Este error se produce después de anunciar los metadatos y antes de subir
el audio: el teléfono puede conservar una entrada atenuada y avanzar el ancla.
La recuperación usa una simulación que aplica los metadatos ANTES del manifiesto,
además de la anterior simulación de finalización.

### Qué hacer con la operación de la preview.3

1. Abre la preview.4 en el mismo ordenador y conserva sus datos de TUPAQ.
2. Conecta y desbloquea el mismo iPhone. Conserva el archivo original en el ordenador.
3. Ve a **Preferencias → Completar importación pendiente**. No vuelvas a añadir
   la canción mediante Importar mientras su operación siga pendiente.
4. Si el original cambió de carpeta, usa **Elegir canciones** para seleccionarlo
   y vuelve a Completar. Solo se admite el mismo contenido, comprobado por SHA-256.
5. Espera la verificación final. Si se detiene, copia el diagnóstico completo,
   incluyendo la línea Datos del protocolo si aparece. No borres canciones o registros
   para forzar un reintento.

La recuperación es **experimental y aún no está validada en un iPhone físico**.
Comprueba que exista un único registro pendiente, sus copias originales, identidad
de biblioteca, incremento de una única ancla y conservación de canciones anteriores.
Se detiene ante un estado mixto, rutas inesperadas, archivos de envío existentes,
fuentes modificadas, objetos desconocidos o entradas cloud/placeholder.

- Si todas las entradas tienen su audio y los hashes coinciden, solo verifica.
- Si siguen representadas pero sin archivo, valida IDs wire y grupos originales,
  estado local soportado y la identidad. Abre una sesión de delta vacío con
  Request/Ready iguales al ancla actual y FinishedSyncingMetadata con esa MISMA
  ancla: no inserta filas, no firma ni escribe operaciones, no incrementa la
  revisión. Solo entrega audio si el manifiesto de esa sesión lo solicita
  para los IDs propios con partes admitidas. Espera una finalización posterior
  a la entrega y comprueba catálogo y hashes permanentes.
- Si iOS retiró todas las entradas propias, verifica que no haya archivos ni
  filas de esas canciones, conserva el registro como `resolved-items-removed`
  e inicia una importación nueva con catálogo actual, nuevo contador y nuevos IDs.
  Se vuelve a capturar el estado bajo lock antes del envío para evitar una carrera.
  No se borran los grupos vacíos que iOS haya conservado.

La aceptación nativa del delta vacío para entregar audio pendiente está
**sin calificar** en la referencia independiente; los replay locales no prueban
que el iPhone la acepte. Una respuesta sin manifiesto, una finalización temprana
o una verificación fallida conserva la operación pendiente. No hay fallback
a SQL, Reset ni eliminación de canciones.

Referencia MIT: [contrato de audio/Genius y estado pendiente](https://github.com/fbiba/rustunes/blob/057ee8fc9c9da65795a6f14497fc408c2fe23c76/crates/music-protocol/src/protocol/ancillary.rs),
[sesión vacía](https://github.com/fbiba/rustunes/blob/057ee8fc9c9da65795a6f14497fc408c2fe23c76/crates/music-protocol/src/protocol/session.rs),
[entrega pendiente](https://github.com/fbiba/rustunes/blob/057ee8fc9c9da65795a6f14497fc408c2fe23c76/crates/music-protocol/src/protocol/session/pending_completion.rs).
