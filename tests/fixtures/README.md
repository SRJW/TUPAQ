# Audio de prueba

Archivos sintéticos de un segundo generados con FFmpeg, sin música de terceros.
Se incluyen para que Windows y macOS puedan ejecutar las pruebas sin instalar
FFmpeg. `aac.m4a` permite comprobar que un contenedor M4A no implica códec ALAC.

Generación (sustituir códec y nombre según la tabla):

```sh
ffmpeg -f lavfi -i sine=frequency=440:duration=1 -c:a CODEC \
  -metadata 'title=Prueba áé' -metadata artist=Importios \
  -metadata 'album=Álbum' ARCHIVO
```

| Archivo | Códec |
| --- | --- |
| sample.mp3 | libmp3lame |
| sample.wav | pcm_s16le |
| sample.aiff | pcm_s16be |
| sample.m4a | alac |
| aac.m4a | aac |

`covered-aac.m4a` es una copia del tono AAC con una imagen PNG verde sintética
y título «M4A con portada», para probar la extracción y presentación de miniaturas.

## Catálogo SQLite de referencia

`library-ios27.sql` es un catálogo sintético mínimo, con `user_version=2410000`
y `item.media_type=8` para una canción. Su procedencia y la diferencia respecto
a `MPMediaTypeMusic` se documentan en `research/LECTURA-MEDIA-TYPE.md`.
