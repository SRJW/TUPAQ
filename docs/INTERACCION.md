# Interacción y tipografía · revisión 25

La aplicación usa siempre `QFontDatabase.GeneralFont` del sistema. En Windows
normalmente corresponde a Segoe UI; en macOS se resuelve la fuente nativa, que
solo se identifica como San Francisco cuando realmente se ha resuelto así.
No se detecta ni selecciona Mori, aunque esté instalada. No hay controles para
cargar o cambiar fuentes y se ignoran preferencias antiguas de familia/archivo.

Los tamaños de texto usan puntos, conservan el escalado del sistema y mantienen
el ancho y espaciado naturales de las letras. Los botones reservan el ancho del
texto, icono y márgenes. La navegación usa iconos y texto en horizontal; no dibuja
etiquetas en un rectángulo estrecho. Columnas y alturas se ajustan a las métricas.
La configuración alcanza tablas, cabeceras, controles, inspector y diálogos.

## Apariencia e interacción

Las cuatro vistas son Biblioteca, Importar, Diagnóstico y Preferencias. Claro
usa superficies marfil y selección verde azulado; Oscuro usa verde profundo y
selección cálida. Las acciones principales comparten el acento naranja opcional.
Los estados pendientes o desconocidos no se presentan como comprobados.

Claro/Oscuro/Sistema, acento, reducir transparencia y reducir movimiento se conservan.
Reducir transparencia usa superficies opacas y suprime los reflejos del fondo;
no se utiliza desenfoque continuo ni se lee el escritorio de otras aplicaciones.

Respuestas de hover de 120 ms y transiciones de navegación/carátulas de 180 ms.
Se conserva un único fotograma temporal, limitado a ocho millones de píxeles físicos,
y se libera al terminar o redimensionar. Reducir movimiento termina las transiciones
inmediatamente. No hay temporizadores decorativos permanentes.

La actualización de la biblioteca mantiene las filas, marcas, selección, búsqueda,
carátulas y desplazamiento hasta recibir una lectura válida. No se desvanece ni
cambia de página por una lectura automática. La detección de cambios consulta
atributos del catálogo/WAL cada 30 segundos cuando USB está libre; solo después
se vuelve a leer el catálogo si ha cambiado. Necesita detección automática activa.

Ctrl/Cmd+F abre Biblioteca y enfoca la búsqueda; Ctrl/Cmd+O elige archivos. Archivos
y carpetas se preparan en el hilo lector, con límites antes de enviar datos. La
importación automática requiere activación explícita y el mismo dispositivo leído.
La pausa se aplica al terminar el lote o archivo actual. Cancelar una escritura
ya iniciada espera su comprobación; no corta una transacción nativa.

[Ver capturas claras y oscuras](DISENO-25.md). Los ejemplos tienen datos sintéticos;
la fuente de cada captura se identifica en `diseno-25/render-info.json`. Las capturas
por plataforma generadas en CI no incluyen archivos de fuentes.
