# Letras y carátulas originales — preview.17

## Qué puedes usar

- Al añadir canciones se detecta USLT y SYLT en etiquetas ID3 (MP3, WAV, AIFF), y ©lyr en M4A AAC/ALAC. Un icono de texto sobre la miniatura y un estado en Detalles indican su presencia. «Ver letra incluida» abre el texto en modo lectura. SYLT se consulta como texto, sin prometer karaoke.
- La importación copia el archivo sin modificarlo y comprueba su hash: conserva la letra incrustada. La aplicación no busca letras en Internet ni envía el texto a diagnósticos o respaldos.
- En el iPhone, el catálogo puede registrar texto o indicar disponibilidad en línea. No se presenta una bandera de disponibilidad en línea como prueba de descarga. La lectura de etiquetas del archivo seleccionado puede detectar letras incrustadas aunque el catálogo no las registre. No se abre cada audio de la biblioteca para buscarlas.
- El inspector usa la carátula original accesible de mayor resolución entre el catálogo y las etiquetas del archivo. Muestra dimensiones, formato y bytes de esa imagen, nunca los del PNG reducido de la tabla. Conserva las proporciones y ofrece una vista al 100% (un píxel de imagen por píxel físico de pantalla).

## Límite actual de la integración con Música

**Conservar ©lyr o USLT dentro del archivo no garantiza que Música muestre las letras.** El registro nativo de letras personalizadas sigue pendiente; esta versión no afirma haberlo implementado.

La documentación del protocolo observada en rustunes (commit 057ee8fc9c9da65795a6f14497fc408c2fe23c76) distingue una entrada `lyrics` con checksum y una parte de activo independiente, bit 8. No documenta suficientemente el algoritmo del checksum, la ruta de entrega ni la codificación del activo. Su propia implementación tampoco declara letras. Referencias: `docs/04-media-library-database.md` (tabla de etiquetas, letras como parte separada), `docs/02-atc-sync-protocol.md` (máscaras AssetParts) y pruebas de ancillary.

No se declara esa parte por conjetura, no se escribe SQL en el teléfono y no se altera la comprobación del manifiesto. Para completar el registro hace falta una captura autorizada de una transferencia correcta con letras o una especificación verificable, seguida de una prueba física que confirme la letra en Música. No se necesita borrar respaldos ni repetir importaciones para detectar la letra incrustada.

## Recursos y verificación

Las miniaturas mantienen su caché pequeña. Solo la selección actual conserva los bytes originales de carátula y el texto. Límite de carátula: 20 MiB / 36 megapíxeles; lectura de etiquetas remotas seleccionadas: 24 MiB; texto visible: 256 KiB. Una imagen inaccesible o demasiado grande usa el estado correspondiente. No se recupera una resolución que no exista en la fuente. Las lecturas de vista previa se cancelan antes de iniciar una transferencia o releer el catálogo.

Pruebas con imágenes y etiquetas sintéticas: dimensiones y peso original, proporciones, vista al 100%, prioridad de la imagen mayor, estados de letras, lectura MP3/M4A/WAV/AIFF, límites, descarte de resultados antiguos y acceso AFC solo lectura. La visualización final en Música de un iPhone físico no está verificada aquí.
