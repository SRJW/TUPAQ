# Análisis estático del instalador aportado

**Actualización:** [Segunda fase: flujo de importación y dependencias](research/SINCRONIZACION.md),
con [evidencia reproducible](research/README.md).

Fecha: 3 de noviembre de 2026. Este documento registra observaciones del archivo
aportado por el usuario; no constituye una implementación de sincronización.

## Integridad y método

- Se reconstruyeron las 19 partes numeradas, en orden.
- El ZIP resultante contiene `3utools-9-09-009.exe`, de 198.037.352 bytes.
- La comprobación CRC del ZIP terminó sin errores. Esto verifica la integridad
  del archivo reconstruido, no la autenticidad de su editor ni su seguridad.
- SHA-256 del ejecutable:
  `42047346546a811642df24159d97624aced6953ac856b68d89d54a01bb4b6b2d`.
- Se encontró y extrajo un archivo 7z incrustado en el desplazamiento
  `0x2fd1c0` (3.133.888 decimal), con 535 entradas entre archivos y directorios.
- Se usaron `zipfile`, `py7zr`, `pefile`, `strings` y `objdump` para leer archivos,
  tablas de importaciones/exportaciones y desensamblar código x64.
- No se ejecutó el instalador, EXE, DLL ni ningún componente extraído. No hubo
  conexión con un iPhone ni modificaciones en una biblioteca musical.
- Los binarios de terceros permanecen fuera del repositorio y no se redistribuyen.

## Hallazgo principal: módulo de importación identificado

`3uTools.exe` importa de `idm_media.dll` las funciones `ios_add_media`,
`ios_del_media`, `ios_add_playlist`, `ios_del_playlist` e `ios_update_playlist`,
entre otras. Por tanto, la relación entre la aplicación y ese módulo se observa
en la tabla de importaciones; no se deduce solamente de su nombre.

El módulo `idm_media.dll` mide 172.904 bytes y tiene SHA-256:
`6fdaeb62646cba0e3fa72228fe320d63ce740440e36a5c31180e5494296496d2`.

Su función exportada `ios_add_media` comienza en RVA `0xc6d0`. Las direcciones
virtuales de la tabla siguiente usan la base preferida `0x180000000`; no son
direcciones observadas en un proceso en ejecución.

| Evidencia en idm_media.dll | Ubicación o referencia de código |
| --- | --- |
| `ios_add_media` | VA `0x18000c6d0` |
| `insert_track` | Cadena en offset de archivo `0x1c028`; referencias en VA `0x18000a9b1` y `0x180015b5d` |
| `/iTunes_Control/Sync/Media/Sync_00000000.plist` | Cadena en offset `0x1c3a0`; referencia en VA `0x18000cfe9`, dentro de `ios_add_media` |
| `/iTunes_Control/Sync/Media/Sync_00000000.plist.cig` | Cadena en offset `0x1c3d0`; referencia en VA `0x18000d003`, dentro de `ios_add_media` |
| `ReadyForSync` | Referencia en VA `0x18000968b` |
| `FinishedSyncingMetadata` | Referencia en VA `0x18000b113`, entre otras |

Otras cadenas presentes en ese módulo:

- Servicios: `com.apple.afc`, `com.apple.iTunes`, `com.apple.atc`.
- Rutas: `/iTunes_Control/Music/F`, `/Airlock/Media/`,
  `/iTunes_Control/Artwork/ArtworkDB`, `/Airlock/Media/Artwork/`.
- Operaciones: `delete_track`, `insert_playlist`, `delete_playlist`, `update_playlist`.
- Mensajes/campos: `RequestingSync`, `SyncAllowed`, `SyncFailed`, `SyncFinished`,
  `LibraryID`, `SyncTypes`, `SyncHostName`, `SyncedDataclasses`.
- Importa funciones de `libplist2.dll`, incluyendo serialización binaria y XML.

**Interpretación:** hay evidencia de una ruta de importación que combina gestión
de archivos con preparación de metadatos/órdenes de sincronización. La presencia
de referencias a los dos archivos de sincronización dentro de `ios_add_media`
es una pista más fuerte que encontrar esas cadenas en un recurso aislado.
No se ha reconstruido el grafo completo de llamadas ni el flujo de datos.

## Componentes adicionales

- `idm_sync.dll` exporta `sync` e incluye mensajes de negociación de sincronización.
- `3uTools.exe` contiene referencias a
  `/iTunes_Control/iTunes/MediaLibrary.sqlitedb`. No demuestra por sí solo que
  la importación escriba directamente en esa base de datos; también podría
  consultarla para listar o exportar música.
- El paquete contiene `itunesFlashDll/MobileDevice.dll`, componentes de Apple,
  Qt 5 y bibliotecas FFmpeg. Su presencia no prueba qué componente participa
  en cada operación concreta.
- Otro módulo, `idm_813.dll`, también contiene rutas similares, pero exporta
  `jb83`. No debe confundirse una ruta antigua o de jailbreak con la ruta de
  importación normal ni tomarse como prueba de compatibilidad actual.

## Lo que todavía no está demostrado

1. El esquema completo de las órdenes y metadatos de importación.
2. El contenido, generación y validación del archivo `.cig`. Su extensión por
   sí sola no prueba un algoritmo de firma, hash o cifrado determinado.
3. La secuencia exacta de mensajes, sus respuestas y diferencias por versión de iOS.
4. Qué ramas y mecanismos usa realmente este programa con iOS 27.
5. La preservación de canciones, listas y portadas existentes durante una importación.
6. Una implementación independiente y funcional para Importios.

## Siguiente investigación

Seguir las llamadas desde `ios_add_media` hacia la construcción de metadatos,
las referencias a `.plist`/`.cig` y la negociación de `com.apple.atc`.
Determinar primero el formato de datos y los requisitos por versión; no llamar
las DLL con argumentos adivinados ni escribir archivos en un dispositivo real.
Una futura validación funcional requiere una biblioteca o dispositivo de prueba,
sin utilizar la biblioteca personal del usuario para experimentar.

El hallazgo permite enfocar la investigación. **No convierte todavía a Importios
en un importador compatible con Música ni valida soporte para iOS 27.**
