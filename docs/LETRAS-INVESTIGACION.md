# Letras dentro de Música — investigación del 10 de noviembre de 2026

Estado: la letra incrustada se conserva al importar, pero todavía no se ha validado su entrega como componente nativo a Música. Esta investigación no habilita la parte 8 del manifiesto ni cambia los envíos USB.

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

## Lo que falta para habilitar el envío

- Identificar el formato y codificación del recurso USB, su ruta de entrega y la confirmación de recepción. La conversión UTF-8 de la rama de nube encontrada en `0xf7a060` no demuestra el formato USB.
- Contrastar la cadena con un componente moderno del host. El `AMPDevicesAgent` del Mac que ya sincroniza correctamente es una referencia más útil que asumir que todos los detalles del host antiguo se mantienen.
- Comprobar la transferencia con una canción de prueba y leer después el texto y checksum del catálogo. Confirmar también su visualización dentro de Música en el iPhone físico.

No se edita `MediaLibrary.sqlitedb` en el teléfono, no se declara una parte sin poder entregarla y no se publica una versión que afirme soporte nativo de letras antes de comprobarlo. Los originales siguen transfiriéndose sin modificar sus etiquetas.
