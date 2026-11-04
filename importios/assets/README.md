# Encuentro · TUPAQ

Identidad elegida por el usuario: dos formas escalonadas que representan la unión.
Paleta de referencia: naranja `#D65313`, marfil `#FFF2DA`, ciruela `#571747`.

- `tupaq.png`: arte aprobado preparado para la aplicación, con transparencia
  fuera de las esquinas del contenedor. Es la fuente para los formatos nativos.
- `tupaq.ico`: siete tamaños, de 16 a 256 px, incrustados en el EXE de Windows.
- `tupaq.icns`: tamaños estándar de macOS, hasta 1024 px, para Finder y Dock.

Los formatos ICO e ICNS se convirtieron desde el PNG mediante Pillow; no se
necesita Pillow para ejecutar ni compilar TUPAQ. Los recursos nativos se conservan
en Git para que cada plataforma publique el mismo diseño. La aplicación Qt carga
una única instancia compartida del icono PNG; los archivos de música sin portada
mantienen su indicador musical genérico.

La interfaz usa un naranja más oscuro (`#B8430A`) para mantener legible el texto
blanco de los botones. La marca no sustituye las carátulas de las canciones.
