# Transferir audio con TUPAQ 0.3

La lectura del catálogo fue confirmada por el usuario con 0.2.0-preview.11.
La importación y la exportación son nuevas y experimentales: se han probado con
un dispositivo simulado y con la interfaz real empaquetada, aún no con un iPhone
físico. No hace falta instalar Python ni abrir iTunes. Windows necesita el servicio
y controlador USB de Apple que ya permite leer la biblioteca.

## Importar del ordenador a Música

1. Conecta un solo iPhone por USB y desbloquéalo.
2. Usa **Elegir canciones** o arrastra los archivos a TUPAQ.
3. En la pestaña del ordenador, selecciona las canciones y pulsa **Importar al
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

1. Pulsa **Leer biblioteca del iPhone**.
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
anclas existentes. **Ver respaldo** abre su carpeta local de datos de TUPAQ.
Es información privada de la biblioteca; no es un respaldo de todos los audios
ni del teléfono completo. No existe una restauración automática de esa copia.

También se conserva un `journal.json` con la fase, hashes, destinos y datos
necesarios para comprobar la operación. No guarda claves de emparejamiento,
respuestas Grappa ni claves del firmador. Estos archivos se conservan al cerrar;
el botón de diagnóstico no copia su contenido.

Si la confirmación final se pierde, una nueva importación queda bloqueada. Usa
**Revisar importación** para leer nuevamente la biblioteca y comprobar canciones
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

Las 57 pruebas incluyen replay de importación de los cinco perfiles base,
originales conservados, exportación byte por byte, nombres existentes,
rechazo por cambio de ancla, identidad sin configurar, manifest desconocido,
audio permanente alterado, interrupción después de aplicar cambios, verificación
sin reenvío y omisión de una transferencia previamente completada.

La prueba de la ventana empaquetada comprueba selección, botones, lock local,
hilo de transferencia, señales, progreso y miniatura con un transporte simulado.
Estas pruebas no demuestran que el iPhone del usuario acepte la primera sesión
ATC; esa comprobación debe hacerse ejecutando el paquete nuevo con el teléfono.
