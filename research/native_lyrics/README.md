# Sonda del parser nativo: investigación, no función de karaoke

Los ensayos del usuario confirmaron que `©lyr`/ATC puede registrar texto, incluso
XML, sin activar avance ni búsqueda por líneas en Música. El usuario utiliza
archivos propios y no tiene suscripción activa a Apple Music; no existe en su
biblioteca un caso confirmado de ambas acciones con el que comparar el registro.

Este experimento intenta separar un problema de documento de un problema de
entrega/registro. En un runner macOS 15 sin cuenta de Apple Music, carga únicamente
el framework MediaServices del sistema e intenta usar `MSVLyricsTTMLParser` sobre
cinco muestras **sintéticas**. No se abren Música, bibliotecas ni archivos de audio;
no se escriben datos en un iPhone ni se implementan solicitudes de red. Los únicos
archivos generados por la sonda son sus propios informes.

Se comprueba presencia y firma de los métodos antes de invocarlos. Las firmas se
contrastaron con las declaraciones de iOS 18 del repositorio de investigación
`qingralf/iOS18-Runtime-Headers`, commit `cfdd406d3a0bbac8473571dda5482e155b1cc402`,
en `PrivateFrameworks/MediaServices.framework/MSVLyricsTTMLParser.h`.
No se copian ni redistribuyen frameworks de Apple.

Los casos comparan TTML genérico, la salida real del generador Line v3, unidades
en segundos y modo Word con palabras sintéticas individuales. El control XML
malformado debe distinguirse de un parser no disponible. Cada muestra se ejecuta
en un proceso separado y con límite de tiempo. Se informa tanto del resultado del
parseo como de los intervalos que devuelve realmente Apple, sin publicar letras.

El resultado `synthetic_times_match` solo significa que **ese parser de ese Mac**
devolvió los dos intervalos sintéticos esperados. No demuestra reproducción en
Música, acceso al campo TTML del reproductor, sincronización USB, compatibilidad
con la versión del iPhone del usuario ni una solución sin suscripción. Un job
verde solo indica que la investigación produjo informes; los resultados negativos
o `parser_unavailable` se conservan y no se convierten en pruebas aprobadas.

La siguiente decisión depende de esos resultados: si el parser acepta Line v3
con sus tiempos, no se justifica seguir cambiando ese formato para corregir la
entrega por USB. Si no reconoce tiempos o falta el parser, el informe delimita
exactamente lo que sigue sin comprobarse. No se modifican flags de disponibilidad
para simular un resultado.

## Resultados observados el 10 de noviembre de 2026

La sonda se ejecutó en dos runners sin cuenta de Apple Music:

- [ARM, macOS 15.8.2 (24H232)](https://github.com/SRJW/TUPAQ/actions/runs/42910344371), commit `55695cd`.
- [Intel, macOS 15.7.9 (24G830)](https://github.com/SRJW/TUPAQ/actions/runs/42910804979), commit `5db2a75`.

En ambos, el framework cargó, el parser estuvo disponible y devolvió:

| Muestra sintética | Parseo | Tipo opaco observado | Intervalos devueltos |
| --- | --- | --- | --- |
| Salida del generador Line v3 | Aceptada | 1 | 1–3 y 3–5 segundos |
| TTML genérico v1 | Aceptada | 0 | 1–3 y 3–5 segundos |
| Line con unidades en segundos | Aceptada | 1 | 1–3 y 3–5 segundos |
| Word, una palabra por línea | Aceptada | 2 | 1–3 y 3–5 segundos |
| XML malformado | Rechazada | 0 | Ninguno |

Estos valores son observaciones, no nombres oficiales del enum. La prueba usa
texto sintético, **no el audio ni la letra real del usuario**. Contrasta el
generador usado para la copia v3, sin afirmar que se ejecutó esa copia privada
completa en los runners públicos.

Decisión: no generar una v4 por cambiar etiquetas, separadores o unidades. El
generador Line produce tiempos que reconoce el parser de Apple en estos Macs;
el ensayo físico de v3 continúa siendo negativo. La investigación siguiente debe
identificar el recurso y la ruta receptora que alimentan `MPModelLyrics.TTML`,
distintos de comprobar el registro de `lyrics` de biblioteca. Hace falta observar
esa ruta antes de implementar otro envío. Ni una suscripción ni un indicador
`hasTimeSyncedLyrics` sustituyen esa evidencia.

No se publicó una nueva versión de la aplicación por estos resultados: no hay
todavía un cambio de importación que permita anunciar karaoke funcional.
