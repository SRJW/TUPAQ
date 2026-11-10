# preview.28: carátulas, marcos y diagnóstico opcional

## Por qué fallaba verify-artwork-original

La preview.26 introdujo una comparación incorrecta de `artwork_type` entre `artwork_token` y `artwork`. La prueba simulaba tipo 6 en ambas filas y ocultaba el caso real: iOS puede usar tipo 1 en el token de la canción y tipo 6 en el original que comparte con su álbum. La unión devolvía cero imágenes aunque el archivo estuviera transferido.

Se corrigió el lector y la simulación. Además, la verificación de la transferencia consulta ahora los originales del identificador de caché enviado, con origen local 300 y variante original 0, después de comprobar que la canción registra ese mismo identificador. No usa la imagen preferida para mostrar ni una carátula de álbum como prueba. Se exige un único original válido para ese identificador y debe tener exactamente el tamaño y SHA-256 del JPEG enviado; una imagen corrupta sigue deteniendo la comprobación. Un error informa cuántos candidatos se localizaron, leyeron y resultaron diferentes, sin rutas, títulos ni identificadores privados.

El audio se verifica antes de la carátula y ese resultado se guarda. Si falla solo la portada, el mensaje puede distinguirlo de una transferencia de audio sin confirmar; la operación no se declara completada. Una operación de preview.27 ya entregada puede reconciliarse mediante lectura con el lector corregido, sin reenviar audio ni eliminar respaldos.

Referencia contrastada: [rustunes, catálogo y carátulas, apartados 10.3 y 10.4](https://github.com/fbiba/rustunes/blob/057ee8fc/docs/04-media-library-database.md). El original JPEG se conserva íntegro; no se acepta una imagen diferente para ocultar el error.

## Desplegables

Redondear la lista con CSS no redondeaba el contenedor nativo de Windows. El contenedor lleva ahora ventana sin marco, sin sombra rectangular del sistema, sin borde QFrame, fondo translúcido y máscara redondeada que se actualiza al mostrar o redimensionar. Se mantienen teclado, Escape y selección.

Se añade una comprobación en el Windows real de GitHub Actions: inspecciona los bits de marco de su HWND, prueba teclado y Escape, y captura el desplegable en ambos temas. Las pruebas Linux offscreen comprueban la región de recorte, pero ese backend no dibuja las máscaras del sistema; no se presenta su captura como prueba visual de Windows.

Se retiraron las dos líneas que explicaban la fuente del sistema. La tipografía continúa usando la del sistema operativo.

## Qué hace la comprobación de lectura

El botón antes llamado «Comprobar todo» se llama «Comprobar lectura de audios». Es opcional: obtiene una copia de lectura del catálogo y lee los audios completos, sin guardarlos ni modificarlos en el iPhone. Compara hashes cuando existe un registro propio asociado a esa biblioteca, canción y ruta. Sin ese registro, leer un archivo no demuestra que coincida con un original del ordenador. Con miles de canciones puede tardar bastante.

No se ejecuta dentro de la importación ni es un paso previo obligatorio. Las comprobaciones de una importación se limitan al estado del catálogo y al lote afectado. Se comprobó que ejecutar el diagnóstico no modifica los archivos ni crea registros de transferencia, y que importar no llama a ese diagnóstico.

## Alternativas estudiadas

| Vía | Qué permite | Ajuste al objetivo de TUPAQ |
| --- | --- | --- |
| Protocolo USB de sincronización y AFC, actual | Registrar canciones, entregar audio y portada, comprobar su resultado | Mantiene la aplicación independiente. La corrección actual repara el lector y evita repetir el envío cuando ya está confirmado. |
| Copiar archivos únicamente por AFC | Mover archivos a zonas compartidas | Copiar un MP3 no basta para registrarlo en la biblioteca de Música. |
| Finder / Apple Devices / iTunes | Sincronización mediante el cliente de Apple | Es una alternativa externa, pero no cumple el requisito de gestionar todo desde TUPAQ. |
| API pública MPMediaLibrary | Añadir elementos del catálogo por productID | Su método AddItem no recibe un MP3/WAV local. No ofrece un sustituto del envío USB de archivos arbitrarios. |
| Otro motor de sincronización integrado, como rustunes | Implementación independiente del protocolo documentado | Requiere portar, integrar y probar el motor en Windows, Mac y el iPhone concreto. No hay evidencia para prometer que un cambio completo de motor sea más seguro que corregir el fallo reproducido. |

Se contrastaron las APIs públicas de [MPMediaLibrary en los bindings de macios](https://github.com/dotnet/macios/blob/main/src/mediaplayer.cs), método `addItemWithProductID:completionHandler:`, y el flujo de transferencia y comprobación de [rustunes](https://github.com/fbiba/rustunes). No se incorporan binarios ni DLL de otros programas.

## Validación y límites

231 pruebas automáticas aprobadas en desarrollo. Casos nuevos: tipos reales 1/6; preferencia visual antigua frente al original correcto; reconciliación del error anterior sin reenvío; imagen realmente corrupta; diagnóstico de lectura separado de importar; eliminación de textos de fuente y recorte de las cuatro esquinas del popup. La verificación por USB en el iPhone físico sigue pendiente.
