# Crear la prueba TTML en Windows

**Resultado de la primera prueba física, reportado por el usuario:** Música mostró
texto sin sincronizar y sin separaciones entre las líneas. Este método no ha
activado karaoke. La herramienta no debe anunciarse como solución para karaoke.

La revisión `Crear-prueba-TTML-v2.exe` añade saltos literales entre los párrafos y
`xml:space="preserve"`. La prueba de regresión comprueba que aplanar los nodos XML
conserva las separaciones. Esto corrige la copia generada; no prueba cómo la
representará Música ni resuelve la entrega de tiempos al reproductor.

Si el visor del chat no descarga el M4A o ZIP, se puede generar la copia localmente
con `Crear-prueba-TTML.exe`, publicado como archivo adicional de preview.30.
La herramienta contiene código genérico; no contiene música, letras de canciones,
archivos del usuario ni datos de su biblioteca.

1. Abre el ejecutable y elige el **M4A original con letra LRC**.
2. Elige dónde guardar la copia con nombre nuevo.
3. Importa esa copia con TUPAQ preview.30. Su título termina en `[Prueba TTML]`.
4. Comprueba si Música interpreta los tiempos o muestra XML/texto sin sincronizar.

No requiere Python ni instalación. Solo lee y crea archivos locales: no se conecta
al iPhone, no importa canciones por sí sola y no envía archivos a Internet.
El original no se modifica. Se verifican los bytes completos del audio `mdat`,
los otros metadatos, la carátula y el hash del original; no se sobrescriben destinos.

El experimento solo convierte los tiempos por línea existentes a TTML estándar.
No genera tiempos por palabra ni demuestra soporte de karaoke en Música.
No se cambia la importación normal ni la verificación de TUPAQ.

Pruebas en `tests/test_lyrics_trial.py`: Unicode/XML, límites temporales,
conservación de audio y etiquetas, rechazo de destinos existentes y de letras
no admitidas. El flujo de compilación también abre el Tk incluido en el ejecutable
de Windows antes de publicar el archivo adicional; no sustituye una prueba de iOS.
