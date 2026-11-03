# Importios: primera prueba de compatibilidad

## Objetivo

Aplicación de escritorio para Windows y macOS que importe música local MP3,
WAV, ALAC y AIFF a la biblioteca de la app Música del iPhone mediante USB.
Copiar archivos a la app Archivos no satisface este objetivo.

## Investigación inicial

Documentación consultada el 3 de noviembre de 2026:

- [libimobiledevice](https://github.com/libimobiledevice/libimobiledevice):
  comunicación con servicios de iOS, identificación, emparejamiento y acceso
  a archivos. Su README no documenta una operación para importar canciones
  a la biblioteca de Música. Conectividad no demuestra sincronización musical.
- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3): herramientas
  y API Python para Windows, macOS y Linux. Documenta detección y acceso AFC,
  pero su README no establece soporte para importar a Música.
- [libgpod](https://github.com/fadingred/libgpod): manipulación de bibliotecas
  de iPod. Las afirmaciones de compatibilidad con iPhone de su README están
  fechadas en 2010. No permiten concluir compatibilidad con iOS actual.

Estas observaciones delimitan lo documentado; no prueban que la transferencia
sea imposible ni que alguna biblioteca la implemente para el dispositivo objetivo.

## Primera prueba necesaria

Equipo indicado por el usuario: Windows 11, iPhone 13 Pro, iOS 27.
La compilación de iOS aún no se ha comprobado.
La compatibilidad de las herramientas con iOS 27 sigue pendiente de validación.

1. Registrar sistema operativo del ordenador, modelo de iPhone y versión de iOS.
2. Preparar detección USB y comprobar la autorización de confianza del iPhone.
3. Identificar un mecanismo de importación compatible con esa combinación.
4. Importar un MP3 de prueba y comprobar en el iPhone que aparece en Música,
   conserva título y artista y se reproduce después de desconectar el cable.
5. Comprobar el comportamiento de la biblioteca existente antes de ofrecer
   transferencias en lote. Documentar cualquier condición de sincronización.

La prueba no se considera superada por detectar el teléfono, abrir una conexión
AFC ni copiar un archivo. Requiere verificar la canción dentro de Música.
No modificar manualmente la base de datos de la biblioteca sin un mecanismo
compatible y una estrategia de recuperación comprobados.

## Ampliación después de la prueba

- Lectura de metadatos y portadas.
- Validación del códec real: ALAC suele venir en un contenedor .m4a.
- Pruebas separadas con MP3, WAV, ALAC y AIFF.
- Conversión solo cuando sea necesaria, conservando los originales.
- Interfaz en español, selección de canciones, progreso y errores comprensibles.
- Empaquetado y pruebas independientes para Windows y macOS.

## Estado

El repositorio incluye una aplicación local para seleccionar y analizar audio,
sin motor de transferencia. Se ha probado con archivos generados en los cuatro
formatos y con Chromium en Linux. El usuario confirmó que Dispositivos Apple
en Windows reconoce su iPhone. No se ha probado la importación a Música.
El entorno de desarrollo remoto ejecuta Linux
y no tiene acceso al USB del ordenador del usuario. La validación física deberá
realizarse en ese ordenador; no requiere que el usuario aprenda programación,
pero sí que ejecute la herramienta de prueba y comunique el resultado.

Actualización: se implementaron una ventana nativa Qt y un firmador candidato independiente con cuatro vectores conocidos. Véase [la cuarta fase](research/IMPLEMENTACION-INDEPENDIENTE.md). La sesión completa de importación sigue pendiente.
