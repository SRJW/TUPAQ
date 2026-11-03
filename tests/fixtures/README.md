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
