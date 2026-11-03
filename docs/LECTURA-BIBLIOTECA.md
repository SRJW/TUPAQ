# Leer la biblioteca del iPhone y preparar la importación

Las versiones preliminares de escritorio incluyen el botón **Leer biblioteca del iPhone**.

1. Conecta un solo iPhone por USB, desbloqueado, a un ordenador que ya tenga
   autorización de confianza. En Windows se necesita el controlador de Apple.
2. Abre TUPAQ y pulsa **Leer biblioteca del iPhone**.
3. Espera la lectura. La pestaña del teléfono mostrará canciones o un mensaje
   de acceso/esquema no compatible. No hace falta aceptar ninguna sincronización.

Si aparece un error o la consulta devuelve cero resultados, pulsa **Copiar diagnóstico** y comparte ese texto (desde `v0.2.0-preview.9`). Indica
la etapa (`modules`, `usb`, `lockdown`, `trust`, `afc` o `catalogue`) y la clase
del error, sin incluir mensajes internos que puedan contener credenciales o
identificadores. No restablezcas la biblioteca ni la confianza para probar.
Estar conectado y desbloqueado no confirma que AFC o el catálogo estén accesibles.
Este diagnóstico ayuda a investigar la causa; no demuestra que se haya corregido
la conexión real del teléfono.

El usuario comprobó que la versión previa devolvía cero canciones aunque tenía
canciones descargadas. Eso no demuestra que la biblioteca esté vacía ni que la
lectura completa funcione. La versión 0.2.0-preview.9 añade un informe agregado
para identificar qué contiene el catálogo consultado y qué descarta el filtro.
Elimina además el INNER JOIN que descartaba música sin fila en `item_extra`:
esas filas se muestran como «Sin título». Se mantiene el filtro de música;
los demás tipos no se presentan como canciones sin saber qué representan.
El informe no contiene nombres de canciones, rutas locales, números de serie
ni registros de confianza. El título de la ventana incluye la versión.
Una prueba con base de datos y WAL copiados confirma que se incluyen registros
confirmados presentes solo en el WAL. No equivale a validar el teléfono real.

El informe de la versión 0.2.0-preview.9 reveló un registro con tipo 8 y esquema
2410000. El filtro anterior usaba erróneamente la máscara pública de MediaPlayer
(1). La versión 0.2.0-preview.11 utiliza el código interno de MediaLibrary (8),
por igualdad, tanto para seleccionar como para contar. Se contrastó con el
lector y las muestras de rustunes para iOS 27; la prueba del ejecutable ahora
lee una muestra de ese esquema mediante SQLite y muestra su canción.
Véase [la investigación y sus fuentes](../research/LECTURA-MEDIA-TYPE.md).

El usuario confirmó que la versión 0.2.0-preview.11 muestra correctamente su canción, artista, álbum y duración en el iPhone 13 Pro. La compatibilidad con todos los catálogos y las transferencias nuevas aún no está confirmada.
Los tests usan dispositivos y bases de datos sintéticos. Que las pruebas pasen
no significa que todos los iPhone permitan acceder al catálogo por esa ruta.

## Operaciones realizadas

Se abre lockdown con `autopair=False`. El SDK valida la confianza existente y
abre una sesión durante la creación del cliente, incluso con ese indicador en
`False`; la aplicación comprueba `paired` y `session_id` y reutiliza esa sesión.
No vuelve a llamar a `validate_pairing()`, porque enviaría otro `StartSession`
y produciría `trust:SessionActiveError`. Una prueba reproduce el fallo con el
lector anterior y confirma que la corrección valida solo una vez usando el
helper real del SDK fijado. El usuario confirmó después la lectura del catálogo.
Después se inicia el servicio AFC. Solo se consultan atributos y se abren archivos en modo `r`.
Se copia `MediaLibrary.sqlitedb` y su WAL, si existe, dos veces, con un límite de
128 MiB por archivo. Se comparan huellas y atributos; si difieren se rechaza la
copia. Esto detecta cambios durante las lecturas; no crea un bloqueo o snapshot
atómico dentro de iOS. La copia pasa por `quick_check` y validación de columnas.
SQLite consulta exclusivamente el archivo temporal local con `mode=ro`.

Las copias temporales se eliminan al terminar. No se envían a Internet, no se
exportan credenciales ni se crean emparejamientos automáticos. No se inicia ATC,
no se escriben órdenes de sincronización ni se sube audio al teléfono al pulsar Leer biblioteca. El botón Importar al iPhone de 0.3 inicia una operación distinta, descrita en [Transferencias](TRANSFERENCIAS.md).
La lectura admite hasta 100.000 canciones y puede tardar hasta dos minutos
más el cierre de conexiones. Un catálogo cambiante o inaccesible produce un error.

## Portadas y M4A

M4A es un contenedor. Se aceptan tanto AAC como ALAC y se muestra su códec real.
La aplicación extrae portadas incrustadas de MP3/M4A y de otros formatos con
etiquetas ID3 compatibles. Las reduce a miniaturas, sin modificar el original.
Se limita la imagen a 5 MiB comprimidos y 16 millones de píxeles. Un archivo sin
portada o con imagen no válida muestra una nota musical.

La miniatura se muestra durante la **preparación local** y, desde 0.3, durante el envío de esa canción al iPhone. La pestaña del teléfono
muestra el catálogo, sin descargar sus portadas en esta versión.

## Transferir archivos

La implementación experimental de 0.3 conserva la biblioteca existente y usa
una actualización incremental con su identidad y ancla actuales. Guarda una
copia local del catálogo antes de enviar metadatos; después verifica catálogo
y audio. No es un respaldo completo del teléfono ni una restauración automática.
Su alcance, uso y límites están en [Transferencias](TRANSFERENCIAS.md).
