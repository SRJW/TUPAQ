# Transferir audio con TUPAQ 0.3

La lectura del catálogo fue confirmada por el usuario con 0.2.0-preview.11.
El usuario confirmó la incorporación de canciones con la preview.4. Los cambios
de portada y fecha de la preview.5, las actualizaciones de metadatos y la
recuperación mantienen carácter experimental y requieren comprobación física. No hace falta instalar Python ni abrir iTunes. Windows necesita el servicio
y controlador USB de Apple que ya permite leer la biblioteca.

## Importar del ordenador a Música

1. Conecta un solo iPhone por USB y desbloquéalo.
2. Entra en **Biblioteca**. Usa **Elegir canciones** o arrastra los archivos a TUPAQ.
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
Desde la preview.5 también se prepara un asset JPEG separado para Artwork,
se registra con un ID de caché libre y se verifica tras el envío. Los originales
JPEG válidos se conservan; las portadas PNG se proyectan a un JPEG separado.
El audio no se reescribe. Se incluyen date_created/date_modified como fechas
plist y se comprueba item.date_added; la aparición en Recientes aún necesita
confirmación visual en el iPhone.

## Exportar del iPhone al ordenador

1. Conecta el iPhone: su biblioteca se carga automáticamente. Puedes entrar en **Biblioteca** o pulsar **Actualizar** para releerla.
2. Marca las casillas de las canciones que quieras exportar. Seleccionar una fila sin marcarla solo abre sus detalles.
3. Pulsa **Exportar** y elige una carpeta del ordenador.
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

La importación no envía eliminaciones ni reset de la biblioteca. Desde preview.8 existe una acción Eliminar separada, que requiere marcar canciones y confirmar. Esto no reemplaza
la validación física de un protocolo privado: un fallo, desconexión o cambio de
catálogo puede dejar una operación pendiente. No se reintenta automáticamente.

## Validación disponible

Las 130 pruebas incluyen replay de importación de los cinco perfiles base,
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

1. Abre la preview.4 o posterior en el mismo ordenador y conserva sus datos de TUPAQ.
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

## Vista unificada, descargas y columnas (preview.5)

Biblioteca reúne la tabla del iPhone, la cola de importación y ambas acciones.
Preferencias es la única otra opción lateral. La cola se muestra al añadir
archivos y puede redimensionarse respecto a la tabla del iPhone.

La vista inicial usa item_state: pertenencia a biblioteca, ausencia de placeholder
y has_non_purgeable_asset o has_non_purgeable_subscription_protected_local_asset.
Así las descargas protegidas de Apple Music cuentan aunque no tengan un audio
exportable por AFC. Los registros de nube o aún sin audio no se cuentan como
descargadas. Desde preview.7 el catálogo bruto se conserva internamente para verificar transferencias, sin ofrecerlo como lista de canciones reales. Dos títulos iguales con archivos
diferentes siguen siendo dos canciones; dos referencias a la misma ruta se
cuentan una vez. No se elimina ninguna fila del teléfono. Si el esquema no
expone esos estados, se muestran referencias USB y se indica que el estado
de descarga no está disponible: eso no certifica que los archivos existan.

Formato y tamaño se leen inicialmente de item_playback/item_extra cuando están
disponibles. Para las filas visibles se comprueba el contenedor real mediante
cabeceras y átomos MP4 acotados; se salta mdat y no se descarga todo el audio.
stat aporta el tamaño real por USB. El tooltip indica el origen y un valor
desconocido se muestra como —. Las cabeceras permiten ordenar en ambos sentidos,
con orden numérico para duración/tamaño y selección persistente por canción.

## Portadas y fecha de incorporación

En una importación nueva, la portada incrustada válida (hasta 5 MiB, 16 millones
de píxeles) se prepara como JPEG independiente. Para PNG se limita la proyección
a 1600 px; el audio original, incluida su portada incrustada, no se modifica.
La nueva caché se asigna por encima de los IDs source300 ocupados en el catálogo.
Cada entrada declara su caché y checksum (un JPEG proyectado +17 para M4A, +1
para ID3). El manifiesto debe pedir exactamente lo declarado, con Genius opcional:
1/5 sin portada, 3/7 con portada, 2/6 para actualizar solo portada.

El JPEG se escribe primero en Airlock/Media/Artwork/ID y se verifica por hash.
Después se entrega audio y una única confirmación conjunta. Tras la sesión
se comprueban el registro de Artwork y los bytes de Originals, además del audio.
Las fechas de creación/modificación de la entrada son fechas plist UTC del
momento de importación y se verifica date_added contra la fecha prevista.
Las fechas de otras canciones deben conservarse. Eso prueba el valor recibido
en el replay; la vista Recientes de Música debe verificarse en un iPhone físico.

### Actualizar canciones ya importadas

1. Abre TUPAQ en el ordenador donde se hizo la importación y conecta el mismo iPhone.
2. Conserva los originales. Si los moviste o quieres limitar el lote, añádelos
   con Elegir canciones (máximo 49 por actualización, 2 GiB de originales).
3. Entra en Preferencias → Actualizar portadas y fecha.
4. Espera la comprobación final. Si falla, usa Copiar diagnóstico y conserva
   los registros; no fuerces otra importación.

Solo se toman recibos completados cuya biblioteca, IDs, metadatos, rutas y
hashes de audio coincidan. Se envían update_track de fecha/caché y el JPEG;
no insert_track, audio nuevo, eliminaciones ni SQL remoto. Sin portada incrustada
se actualiza solo la fecha. Se verifican los audios antes y después. Una
actualización sin confirmar se revisa antes de otro envío; si el audio coincide
pero falla solo la portada o fecha, se registra como metadatos por revisar. Estas actualizaciones todavía requieren validación física.

Referencia independiente MIT: [campos de fecha y protocolo de Artwork](https://github.com/fbiba/rustunes/blob/057ee8fc9c9da65795a6f14497fc408c2fe23c76/docs/04-media-library-database.md),
secciones 4 y 10. El cliente no modifica ArtworkDB del host ni la SQLite del teléfono.


## Interfaz y recuperación (preview.7)

La referencia visual vigente es Peel: panel lateral compacto, lista central con
búsqueda por canción/artista/álbum y un inspector derecho plegable. Los controles
Importar/Exportar comparten Biblioteca. Se conserva una vista clara opcional.
macOS utiliza su fuente nativa San Francisco; Preferencias identifica la familia
resuelta. No se redistribuyen fuentes de Apple en Windows. Se admite seleccionar
un archivo local autorizado; el usuario necesita derechos de uso aplicables.

Al leer la biblioteca se enumeran los nombres de cada carpeta de audio validada
una sola vez (máximo 512 carpetas); no se descargan los audios. Una referencia a
un archivo ausente se excluye. Un fallo de acceso no se interpreta como borrado,
y las descargas protegidas sin ruta AFC conservan su indicador de estado local.
Desde preview.8 se retira el segundo filtro y la columna de acceso USB. La vista única mantiene el filtrado por estado local y presencia, conservando las descargas protegidas que iOS no expone como archivo.

Una duración desconocida se muestra como —. Se usa total_time_ms, o duración en
muestras / frecuencia de item_playback; las filas visibles comprueban también
cabeceras WAV, AIFF, MP4, MP3 y FLAC, sin leer todo el audio. Un valor positivo
menor a un segundo se muestra como 0:01 en vez de aparentar duración nula.

Antes de importar se revisan recibos anteriores contra la biblioteca conectada.
Un audio propio con ID, ruta, tamaño y SHA-256 correctos queda como
observed-present: evidencia de que existe ahora, distinta de la confirmación
original de la sesión. Puede verificarse aunque el ancla haya avanzado. Se
comprueban por separado metadatos/portada y se informa si siguen pendientes.
Un fallo cosmético no exige reenviar audio ya correcto. La deduplicación por
contenido incluye estos recibos y vuelve a comprobar sus bytes antes de omitirlos.

Si faltan bytes, cambió la identidad o la operación está en una fase incierta,
no se envía otra importación: el diagnóstico añade la causa guardada y la
comprobación fallida actual. No se borra el recibo para desbloquear la interfaz.
Los recibos vinculados a otra biblioteca se conservan sin bloquear el iPhone actual.
Un preflight interrumpido sin escrituras se cierra localmente. Un lote cuyos IDs
y todos sus archivos propios ya están ausentes puede retirarse del estado pendiente
tras comprobar también el área temporal. Revisar importación ejecuta estas mismas
comprobaciones de solo lectura y no abre una nueva sesión ATC.


## Marcar, buscar y eliminar (preview.8)

Las casillas seleccionan canciones por identidad, incluso al ordenar o buscar.
Seleccionar visibles afecta solo a los resultados actuales; el contador incluye
las marcas ocultas por la búsqueda. La confirmación de eliminación permite
revisar la lista completa. Al desconectar o cambiar de iPhone se borran las marcas.
El buscador admite formatos con o sin punto, códec y términos de metadatos juntos:
`.m4a`, `mp3`, `wav`, `alac`, `.m4a artista`. Una cabecera de archivo comprobada
prevalece sobre una extensión incorrecta. Eliminar los filtros visuales de acceso
no convierte una descarga protegida en un original exportable.

**Eliminar** admite de 1 a 100 canciones marcadas. Pide confirmación con Cancelar
como opción predeterminada. La copia automática del catálogo no guarda sus audios:
exporta previamente los originales que quieras conservar.

Antes de escribir se comprueban el dispositivo mediante un token efímero en memoria,
el DBPID y primary de la biblioteca, los item_pid y sync_id y los metadatos/rutas
de la selección. Un cambio detiene la operación. Bajo el bloqueo de sincronización
se guarda una copia del catálogo y preferencias y se entrega un delta firmado:
update_db_info seguido exclusivamente de delete_track con IDs wire. Los IDs
SQLite con signo se proyectan a su representación nativa de 64 bits sin signo.
No se escribe SQL remoto ni se desvinculan archivos de audio desde el ordenador.
Las solicitudes de assets de objetivos eliminados se rechazan antes de confirmar
ningún asset. Solo se pueden declinar auxiliares conocidas de canciones supervivientes.

Tras SyncFinished se exige el avance de ancla y que el conjunto de items sea
exactamente el anterior menos los marcados. Los IDs wire, títulos, artistas,
álbumes, duraciones, rutas y fechas conocidas de las demás canciones deben
conservarse. iOS puede limpiar los archivos después; no se afirma espacio liberado.
Si se pierde la confirmación, Revisar operación pendiente comprueba el catálogo
sin volver a enviar eliminaciones ni audio. Una eliminación incierta no se repite
automáticamente. Estas comprobaciones no equivalen a validar todas las tablas o
listas de reproducción de todas las versiones de iOS; falta prueba física.

## Para qué sirven las opciones avanzadas

Se muestran solo al activar **Preferencias → Mostrar opciones avanzadas de recuperación**.
La importación normal ya guarda registros y comprueba operaciones anteriores.

- **Revisar operación pendiente:** consulta el estado actual, comprueba audio o
  eliminaciones registradas y resuelve las que puede demostrar. No reenvía música.
- **Completar importación pendiente:** intenta entregar el audio que falta de una
  importación registrada, usando el original. No sirve para repetir eliminaciones.
- **Actualizar portadas y fecha:** actualiza esos metadatos de canciones importadas
  por TUPAQ en este ordenador, con originales y registros coincidentes.
- **Ver respaldo del catálogo:** abre los registros y copias de base de datos
  previas a los cambios. Son útiles para comprobar e investigar un problema,
  pero no incluyen todos los audios ni ofrecen una restauración automática.

## Referencias de portada existentes

Una referencia source300 no tiene por qué ser una cadena decimal canónica mayor
que 99. Los valores nulos u opacos se conservan sin interpretarlos como nuevos
IDs ni impedir la importación. Los enteros y cadenas decimales representables
reservan sus IDs, incluidos cero y alias con ceros iniciales. Se preserva una
huella tipada de todos los tokens durante la comprobación previa a escribir.
La asignación usa un ID libre y busca huecos si el máximo de 32 bits ya está
ocupado. Las portadas nuevas siguen requiriendo registro y bytes SHA-256 correctos.


## Actualización visual y tipografía (preview.10)

Al releer el catálogo, las filas anteriores siguen visibles con el aviso
Actualizando biblioteca. Se muestra el resultado completo cuando termina la lectura,
conservando las marcas, la canción seleccionada y la primera fila visible cuando
siguen existiendo. Las carátulas se reutilizan dentro del límite de 256 iconos; se
invalidan si cambian su referencia, ruta o metadatos relacionados. Una lectura fallida
conserva la vista anterior y el diagnóstico. Desconectar el teléfono sigue limpiando
la lista. El mensaje de una importación completada permanece en la barra inferior.

El diseño usa paneles y gradientes estáticos inspirados en Apple Music. El resumen
con portada se sitúa sobre la biblioteca; Detalles permite ocultarlo. La tabla
continúa siendo virtual y las portadas se leen solo para las filas visibles.
Mantiene Qt nativo y fondos estáticos para limitar el trabajo de repintado.

En Windows se puede elegir una familia instalada o un archivo TTF/OTF/TTC/OTC de
hasta 128 MiB. La muestra es una previsualización; **Aplicar** confirma el cambio
en todos los widgets, incluidos botones y cabeceras. Cargar un archivo inválido
conserva la fuente actual. La elección se guarda únicamente tras aplicar y el
archivo elegido debe seguir disponible en aperturas posteriores. Las fuentes
propias no se copian a los paquetes distribuidos. En macOS se ignoran elecciones
personalizadas anteriores y se usa siempre la fuente nativa del sistema.
