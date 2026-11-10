# Letras dentro de Música — investigación del 10 de noviembre de 2026

Estado: preview.30 implementa la entrega nativa de **letras de texto** con canciones nuevas. Se habilita la parte 8 únicamente para entradas propias con un recurso preparado y checksum válido. Las 245 pruebas pasan y los tres paquetes nativos se publicaron correctamente. El usuario confirmó que una canción importada con preview.30 muestra la letra en Música de su iPhone, con las marcas LRC como texto. Es una confirmación reportada por el usuario; no se presenta como acceso directo de este entorno al dispositivo. **El karaoke no está implementado ni validado.**

## AMPDevicesAgent moderno: ruta USB identificada

El usuario aportó `AMPDevicesAgent.exe` 1.7.0.155, AMD64, 12.486.008 bytes, SHA-256 `9503c6084a662f594e79a22201dc579d127040ae38b56996b682d49e28710b10`, base `0x140000000`. Solo se leyó y desensambló; no se ejecutó ni cargó. Las direcciones siguientes son RVA:

- `466da8`: el despachador de letras admite Track (2) y Lyrics (5). Para el identificador combinado de una canción, selecciona Media y el subdirectorio `Lyrics`. El global elegido en `466eec` se inicializa con ese literal en `1bd008`.
- `464fd4` llama a `47ce44` para resolver Airlock y la clase Media y añade el subdirectorio. Esto no es una ruta deducida del envío de carátulas.
- `46691c`: obtiene el objeto Lyrics y llama a su serializador en `466c06`.
- `32f4f8`: llama a `CFStringCreateExternalRepresentation` con UTF-8 `0x08000100` y lossByte 0. El texto no se empaqueta en un plist ni en un contenedor XML.
- `47d118`: copia el AssetID para el nombre del recurso, sin añadir una extensión. El ajuste de separadores de `5bc1d4` no afecta a los identificadores decimales usados por TUPAQ. Resultado: `/Airlock/Media/Lyrics/<AssetID decimal>`.
- `466d28`: el callback recibe ese directorio, nombre y CFData; `467070` guarda los datos. El callback de finalización `466fa0` entrega la parte 8 a `464bd8`. Este elimina el bit finalizado y **espera las demás partes antes de enviar FileComplete** (`464d9e`); no se envían confirmaciones contradictorias para un mismo identificador combinado.
- `472304`: el constructor anuncia `item.lyrics.checksum`. El cálculo moderno `32f2ac` coincide con el algoritmo reconstruido abajo; el selector 1 termina en MD5, comprobado por la constante de primera ronda `d76aa478` y rotación 7 en `794f42` y `794f54`.

El código público de CoreFoundation se contrastó para la codificación: `CFString.c`, `CFStringEncodings.c` y `CFBuiltinConverters.c` en `swiftlang/swift-corelibs-foundation`. Aunque la función de representación externa pasa un flag genérico de BOM, el conversor UTF-8 `__CFToUTF8` no lo utiliza para anteponer bytes. Se envía UTF-8 estricto sin BOM añadido ni terminador; el checksum usa el texto exacto UTF-16BE sin BOM.

`scripts/inspect_amp_lyrics.py RUTA/AMPDevicesAgent.exe` reproduce las comprobaciones de instrucciones y rechaza otra versión. Requiere `pefile` solo para investigación. No se distribuye ningún ejecutable, DLL ni desensamblado de Apple.

## Comportamiento de preview.30

Se leen USLT o ©lyr de los originales. Para un archivo que solo lleva SYLT se puede entregar su texto, pero eso **no convierte sus tiempos en karaoke**. Los bytes originales, incluidos todos sus tiempos, no se modifican. Preferencias → Metadatos permite desactivar el envío adicional de letras; la opción está activa por defecto.

La letra se limita a 256 KiB, se prepara en un archivo local privado y se comprueba su hash al enviarla y al releerla por AFC. El journal guarda hashes y rutas, no el texto de la letra. La copia privada del catálogo sí puede contener letras, igual que el archivo auxiliar preparado. No se suben a Internet.

Solo se admiten los manifiestos exactos de componentes declarados para cada entrada propia: audio/letra (9) o audio/carátula/letra (11), con Genius opcional (13 o 15). Una solicitud ajena o inesperada no se acepta por habilitar el bit 8. La entrega de texto precede a la confirmación del identificador combinado. Se compara después el texto completo registrado en `lyrics`, su SHA-256, tamaño UTF-8 y checksum normalizado a uint32, vinculados por el item_pid que corresponde al sync_id enviado. Se relee el catálogo hasta tres veces si está asentando la letra, sin reenviar metadatos ni audios.

Una letra ausente, distinta o con checksum incorrecto no se declara verificada. Se conserva el registro y la información de audio presente. Revisar operación pendiente puede observarlo sin repetir la inserción. La recuperación de una entrada sin audio utiliza su mismo ID, original y letra preparados. No se cambian letras preexistentes de otras canciones ni se escribe SQLite en el dispositivo.

Esta primera implementación añade letras con **canciones nuevas**. Volver a elegir una canción ya importada no actualiza su letra ni la duplica. La herramienta antigua de reparar portadas/fecha tampoco añade letras retroactivamente.

Pruebas: MP3 USLT, M4A AAC/ALAC ©lyr, acentos, emojis y CRLF exactos, con y sin portada, recursos corruptos, letras omitidas o alteradas por el receptor simulado, checksum erróneo, límites, esquema desconocido, recuperación, registro previo intacto y duplicados. Ninguna de estas pruebas sustituye la comprobación de la pantalla de Música en un iPhone.

## Letras sincronizadas: resultado y límite actual

El usuario aportó un M4A ALAC de ejemplo. Se examinó su estructura sin ejecutarlo ni modificarlo: contiene 57 marcas LRC en `©lyr`, ordenadas, entre 16,31 y 273,66 segundos, y una única pista de audio ALAC. No contiene tiempos por palabra ni una pista de texto temporizado independiente. Su letra mide 2.477 bytes UTF-8. No se publica el audio ni el texto de la canción en el repositorio.

La captura de Música muestra las marcas LRC literalmente. Después, el usuario probó preview.30 y confirmó: aparece la letra, pero los tiempos siguen siendo texto. Esto verifica el caso de letra de texto; no demuestra karaoke ni interpretación de esos tiempos por Música. También se probó el archivo real completo contra el receptor simulado: audio, portada y letra exacta se verificaron y el hash del original permaneció igual.

Se preparó una **copia privada de experimento**, separada del original y del repositorio, con la letra convertida a TTML estándar por líneas. Conserva 55 líneas no vacías y los límites derivados de los 57 marcadores; no inventa tiempos por palabra. Su título y álbum indican que es una prueba. Se comprobó la igualdad de todos los bytes `mdat` del audio, de la carátula y del archivo original sin modificar. El recurso preparado para el envío coincide con el TTML de la copia. No se cambia un flag de disponibilidad de iOS para fingir un resultado ni se omite la verificación si iOS devuelve otro contenido.

**Resultado físico del ensayo TTML v1:** el usuario confirmó texto sin sincronizar y aportó una captura con las palabras de párrafos consecutivos unidas. A los 8 segundos se mostraba el texto aun cuando la primera marca estaba en 16,31 segundos. El ensayo no activó karaoke. La concatenación tiene un defecto identificable en el generador: se serializaban `</p><p>` adyacentes sin separadores literales. La v2 añade saltos entre párrafos y `xml:space="preserve"`; seis pruebas y el archivo real comprueban que aplanar los nodos conserva 55 líneas. Esa comprobación es de XML, **no es una prueba del renderizador de Música ni una solución de sincronización**. Se preguntó también si TUPAQ dio por comprobada la importación para distinguir una transformación en el catálogo de una presentación de texto en el reproductor.

El usuario confirmó que **TUPAQ terminó como importación comprobada**. Por tanto, su comprobación de letra/texto se completó, aunque Música no resaltó los tiempos. La verificación de transferencia no debe describirse como verificación de karaoke.

Se contrastó después la referencia abierta AMLL (`9db9236818464ce83f696ee9c5ff0e5395cb744a`): su perfil por líneas utiliza el atributo de contenido `itunes:timing="Line"` y claves `itunes:key="L1"`. La primera copia solo tenía TTML genérico. La variante v3 añade esos atributos documentados y una sección de metadatos vacía, sin cambiar flags del catálogo de iOS ni inventar tiempos por palabra. La documentación y alcance de ese ensayo están en `PRUEBA-TTML.md`. Sigue pendiente la interpretación física de v3; esta referencia de formato no prueba que la ruta USB admita karaoke.

El ejecutable sí contiene la propiedad `ttml` en la serialización del objeto Lyrics (RVA `32f78c`, clave en `9ac9f8`). **No se ignora esa pista ni se presenta como prueba de karaoke USB**: el lector local encontrado construye el objeto en `331823`; el constructor `32f0f8` inicializa los flags TTML a cero en `32f16a`. El emisor USB `32f4f8` transmite el CFString, sin los flags de esa serialización de objeto. El metadato enviado en `472304` contiene el checksum; no se encontró en esta cadena un anuncio de tiempos o una activación de karaoke.

El esquema iOS de referencia distingue texto `lyrics` de `time_synced_lyrics_available` y de las disponibilidades del catálogo Apple. Marcar a mano esos indicadores no entrega los recursos con tiempos y no se implementa. Tampoco se envía XML o timestamps como si su mera presencia garantizase que Música los interprete.

Pendiente: encontrar/contrastar una ruta receptora de iOS que registre tiempos, distinta de limitarse a incluir XML en la letra de texto; después verificar tanto su registro temporal como el resaltado durante la reproducción en Música. El primer ensayo TTML fue negativo y no hay evidencia suficiente para prometer que el flujo de texto encontrado resuelva karaoke. No se añaden metadatos o flags adivinados para anunciar soporte inexistente.

El usuario confirma que tiene canciones con letras visibles importadas previamente con Música y Finder en su Mac. Son una referencia positiva: el objetivo es reproducir ese registro, además de conservar las etiquetas del archivo.

## Hallazgo nuevo: checksum de la letra en el host

Se analizó estáticamente la `iTunes.dll` que aportó el usuario, SHA-256 `09c79c46f5bf77ce6ca7872ceaa9807104df03311c4ea3ea90abbcbdc35cc7c8`, PE i386, base `0x10000000`. No se cargó ni ejecutó el código de Apple y no se distribuye el binario.

La cadena encontrada distingue la operación nativa de metadatos del flujo de subida a la nube investigado anteriormente:

1. La rutina de escritura de letras, RVA `0xf5c250`, llama a `0x9e0980` en `0xf5c3da` y guarda el resultado en `record+0x68` en `0xf5c3e4`.
2. El constructor de metadatos comprueba ese campo en `0x26236a`, lo lee en `0x26239f` y lo coloca en el diccionario `lyrics`, clave `checksum`, entre `0x26239f` y `0x2623d4`.
3. `0x9e0980` copia los caracteres UTF-16 del CFString y llama a `0x9e0a30`. No se encontró normalización, recorte ni conversión de saltos de línea en esta cadena.
4. `0x9e0a30` reserva exactamente dos bytes por unidad UTF-16, invierte los bytes de cada unidad (a big endian) y selecciona el algoritmo 1 mediante `0x46ec10`.
5. El selector 1 lleva a las funciones `0x46e040`, `0x46e080` y `0x46e0a0`. La salida tiene 16 bytes. El recorrido del actualizador llega a `0x127e200`, cuyo primer paso usa la constante MD5 `0xd76aa478` y la rotación 7. No se identifica MD5 solo por las constantes de inicialización, que también comparte MD4.
6. El finalizador produce un descriptor con algoritmo, longitud y digest. Se toman los cuatro words del digest, interpretados como enteros de 32 bits big endian, y se combinan con XOR. Un resultado cero para texto no vacío se convierte en 1. Un texto vacío devuelve 0.

Modelo independiente, sin código nativo:

```
texto vacío: 0
otro texto:
    digest = MD5(UTF16BE(texto), sin BOM ni terminador)
    resultado = word0 XOR word1 XOR word2 XOR word3
    checksum = resultado si es distinto de 0; si no, 1
```

Se implementó en `importios/sync/lyrics.py`. MD5 se usa como checksum de compatibilidad, no como medida de seguridad. Se conservan exactamente acentos, pares sustitutos para caracteres no BMP y saltos de línea. No se adivina un checksum a partir del tamaño del archivo o del texto UTF-8.

## Reproducción

`scripts/inspect_lyrics_checksum.py RUTA/iTunes.dll` necesita `pefile` solo para investigar. El script valida el hash y perfil del archivo y comprueba 27 secuencias de instrucciones que enlazan escritura, lectura, conversión, MD5 y reducción. Devuelve un informe pequeño, sin ejecutar el binario ni abrir USB. Rechaza otra versión de la DLL.

Vectores del modelo:

| Texto | Checksum hexadecimal |
| --- | --- |
| vacío | `00000000` |
| `a` | `cbc4ca42` |
| `Letra de prueba` | `44e236d3` |
| `Primera línea\nSegunda línea` | `8d3a162e` |
| `A\r\nB` | `712e7391` |
| `🎵 café` | `bdc4a67d` |

La prueba de reducción cero es sintética; no se presenta como un texto real encontrado con digest reducido cero.

## Comprobación contra un catálogo existente

Se añadió `md5_fold_utf16be` al sondeo de lectura `lyrics_checksum_probe`. Compara hasta 32 filas que ya contienen texto y checksum no nulo en la copia local del catálogo. Incluye checksums guardados como enteros negativos de 32 bits. El informe devuelve únicamente cantidades y coincidencias: no devuelve letras, títulos, identificadores ni valores de checksum. No modifica el catálogo ni lee todos los archivos de audio.

Una coincidencia en las canciones del usuario importadas con Finder permitiría contrastar este cálculo antiguo con su biblioteca actual. Aunque coincidieran todas, `usb_contract_verified` sigue siendo falso: eso por sí solo no determina cómo se entrega el recurso.

La implementación publicada de rustunes también se volvió a consultar en HEAD `4511f49aed021152f579568f116fd7d329dcdef6` (0.1.1). Sigue documentando la parte Lyrics = 8 y `lyrics.checksum`, sin implementar ni declarar la parte de letras. Por tanto, no se presenta esa referencia como una solución completa para las letras.

## Pendientes de la investigación anterior, actualizados

- Formato, codificación, ruta y confirmación de texto: identificados en el nuevo AMPDevicesAgent de Windows, sin asumir el formato de la rama de nube antigua.
- Contraste con host moderno: realizado; no hace falta otro binario del Mac para implementar el envío de texto.
- Lectura de texto/checksum tras el envío: implementada y probada en simulación. Confirmación visual de letra de texto en iPhone físico: reportada por el usuario con preview.30.
- Karaoke: investigación abierta, sin afirmar compatibilidad a partir del registro de texto.

No se edita `MediaLibrary.sqlitedb` en el teléfono ni se declara una parte sin preparar su contenido. La preview.30 es una implementación candidata para validación en dispositivo; no presenta como realizadas pruebas físicas inexistentes. Los originales siguen transfiriéndose sin modificar sus etiquetas.
