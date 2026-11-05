# Lotes grandes · 0.3.0-preview.23

## Qué se probó

Las pruebas se ejecutaron en Linux con Python y Qt 6.10.2. El teléfono era un
simulador de AFC/ATC que aplica las solicitudes nativas reales de TUPAQ a un
catálogo SQLite y a archivos de audio sintéticos. No se conectó un iPhone físico.
Se ejercitaron el planificador, las sesiones, el protocolo de importación y
eliminación, los recibos y la comprobación final del catálogo y de los audios.

| Prueba | Resultado | Tiempo observado |
| --- | --- | --- |
| Importar 1.000 y eliminar las mismas 1.000 | Completada; original no seleccionado intacto | 9,453 s en total |
| Importar 10.000 | 10.000 comprobadas, 205 lotes | 167,289 s |
| Eliminar esas 10.000 | 10.000 comprobadas, 100 lotes | 58,200 s |
| Preparar 10.000 archivos en la interfaz | 10.000 filas; sin errores de lectura | 8,819 s |

Estos tiempos corresponden a **archivos de prueba diminutos y almacenamiento
local**, no representan la velocidad de un cable USB ni la de música real.
[Resultado de 1.000](stress/transfers-1000.json),
[resultado de 10.000](stress/transfers-10000.json) y
[resultado de interfaz](stress/preparation-10000.json).

La prueba de 10.000 conservó exactamente la canción previa, su audio y el cierre
de todos los manejadores del simulador. Las copias y los recibos ocuparon
503.520.908 bytes en esa ejecución: el crecimiento del catálogo importa aunque
los audios sintéticos sean pequeños. No se borran respaldos automáticamente.

La prueba de interfaz incluyó 150 M4A con portada y 9.850 MP3. Solo se decodificaron
96 miniaturas iniciales de hasta 64 píxeles. La carátula original de la selección
sigue cargándose aparte. Un temporizador de 10 ms midió una pausa máxima de
277 ms; el proceso alcanzó aproximadamente 189 MiB de memoria residente máxima.
Son medidas de esta máquina, no garantías para Windows, macOS o cualquier equipo.

La revisión final pasó **192 pruebas automáticas**, la comprobación de la interfaz
desde el código y la del ejecutable Linux empaquetado con PyInstaller. Las
compilaciones nativas de Windows y macOS se verifican por separado en GitHub Actions.

## Problemas encontrados y corregidos

La primera prueba de 10.000 se detuvo en 1.029: dos canciones del mismo lote
podían recibir la misma ruta aleatoria antes de subir los archivos. El planificador
ahora reserva cada destino inmediatamente y reintenta las colisiones. Se añadió
una regresión determinista y después pasó la ejecución completa de 10.000.

Preparar miles de archivos ordenaba repetidamente la tabla, decodificaba demasiadas
portadas y podía inundar la cola de eventos. Ahora se ordena al terminar, se limita
el trabajo de miniaturas y hay contrapresión entre el lector y la interfaz.
Se limita también la lista visible de errores a 100 más un resumen, conservando
el número real de fallos. La confirmación de eliminación muestra el total exacto
y una vista detallada de hasta 100 títulos; no crea un diálogo de miles de líneas.

## Fallos y cancelación

Las pruebas automáticas cubren también:

- Desconexión en el tercer lote: conserva los 200 borrados comprobados y detiene
  el resto; no reintenta el lote fallido automáticamente.
- Cancelación tras comenzar un envío nativo: termina y comprueba ese lote antes
  de parar. Repetir la selección omite los originales ya importados que coinciden
  con sus recibos y su hash; no los vuelve a insertar.
- Pérdida de la respuesta final de una importación: la siguiente operación
  reconcilia el recibo con el catálogo y el audio antes de continuar.
- Cambio de teléfono o de identidad de catálogo entre lotes: parada antes de
  escribir en la nueva biblioteca.
- Falta de espacio local, selección duplicada, colisiones y límites de tamaño.
- Resultado parcial en la interfaz: solo retira de la cola las canciones
  comprobadas. El resto permanece disponible para una operación posterior.

Los puntos de interrupción reproducidos son específicos; no equivalen a probar
todos los fallos posibles de USB, iOS, disco o alimentación.

## Límites conservados

Hasta **50.000 canciones por selección**. Cada transacción importa como máximo
49 canciones y 2 GiB, o elimina hasta 100 canciones. Cada archivo importado sigue
limitado a 256 MiB. El catálogo admitido tiene como máximo 100.000 registros;
no se permite una importación que cruce ese límite. Exportar conserva su límite
independiente de 1.000 archivos por operación.

Cada lote captura el catálogo y comprueba el resultado antes del siguiente.
El límite de espera de 30 minutos se aplica a cada lote, no a toda la selección.
El trabajo queda vinculado al mismo teléfono y a la misma identidad de catálogo.
Se comprueba espacio libre local antes de cada lote: al menos 512 MiB o tres veces
el tamaño de la última copia, lo que sea mayor. Esto no reserva espacio ni puede
impedir que otro proceso llene el disco mientras se está escribiendo.

Un índice local en `bulk-jobs` registra los lotes comprobados; los recibos nativos
siguen siendo la autoridad para resolver una operación pendiente. No se reanuda
un trabajo de miles de canciones a ciegas al abrir la aplicación. Un fallo detiene
la operación; se conserva la selección restante y se puede revisar el diagnóstico.
La copia del catálogo **no contiene todos los audios**: exporta los que necesites
conservar antes de eliminarlos del teléfono.

## Reproducir

Desde la raíz del repositorio, con las dependencias de desarrollo instaladas:

```bash
.venv/bin/python scripts/stress_transfers.py --tracks 10000 --report /tmp/transfers.json
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/stress_preparation.py --tracks 10000 --report /tmp/preparation.json
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
```

En Windows se usa el intérprete equivalente del entorno virtual y puede omitirse
`QT_QPA_PLATFORM=offscreen` para ver la ventana. Ambos programas de estrés crean
datos temporales, no usan el iPhone real y no deben incluirse en el ejecutable.

La validación pendiente es ejecutar lotes grandes con un iPhone físico, música
real, distintos cables y ambas plataformas. Las pruebas realizadas aumentan la
cobertura y descubrieron un fallo concreto; no permiten prometer cero errores.
