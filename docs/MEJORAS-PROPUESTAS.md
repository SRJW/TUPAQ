# Propuestas para las siguientes versiones

Estas funciones están propuestas; no se presentan como implementadas.

1. **Cola guardada e historial local por canción.** Recuperar la cola tras cerrar
   la app y mostrar qué se importó o exportó, cuándo y con qué resultado. Guardar
   solo rutas, metadatos y comprobaciones locales, sin duplicar los audios ni
   reanudar escrituras automáticamente. Es la prioridad para mejorar continuidad
   y hacer más comprensible una interrupción.
2. **Vistas Álbumes y Recientes.** Cambiar entre la tabla actual y una cuadrícula
   de portadas; consultar metadatos ya leídos y cargar únicamente las portadas
   visibles. Mantener las casillas y acciones en ambas vistas. Recientes debe
   distinguir fechas conocidas de datos ausentes o ambiguos.
3. **Avisos de posibles duplicados antes de importar.** Comparar título, artista,
   álbum y duración para señalar coincidencias, sin fusionar ni omitir versiones
   diferentes automáticamente. El usuario decide; no se descargaría toda la
   biblioteca para calcular hashes masivos.

La base de estas mejoras es conservar siempre la última vista válida, mostrar
resultados por canción y mantener las comprobaciones de identidad y contenido
antes de cualquier escritura. La interfaz no debe presentar una lectura fallida
como biblioteca vacía ni una transferencia no confirmada como completada.
