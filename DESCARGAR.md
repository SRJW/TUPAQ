# Descargar Importios sin usar Python

GitHub compila la aplicación para Windows y macOS. Las descargas incluyen
el intérprete y las dependencias: no necesitas instalar Python.

## Descarga recomendada

Entra en [Releases](https://github.com/SRJW/importios/releases) y abre la versión
preliminar de escritorio. Sus archivos aparecen en **Assets**, una vez que la
compilación termine. Elige `.exe` para Windows y el `.dmg` correspondiente a tu
Mac. No necesitas Python, terminal, navegador para usar la aplicación ni iTunes.
La detección USB en Windows sí necesita el controlador/servicio local de Apple.

## Windows 11 (descarga desde Actions)

1. Entra en [las compilaciones de GitHub](https://github.com/SRJW/importios/actions/workflows/desktop.yml).
2. Abre la ejecución más reciente de la rama `desarrollo/preparacion-musica`
   que tenga un indicador verde. Si está en curso, espera a que termine.
3. Al final de la página, en **Artifacts**, descarga **Importios-Windows-x64**.
   Para descargar artefactos debes iniciar sesión en GitHub.
4. Extrae el ZIP y abre **Importios.exe**. Se abrirá una ventana propia de Importios.
5. Para salir, cierra la ventana de Importios.

## macOS

En la misma ejecución, descarga **Importios-macOS-AppleSilicon** para un Mac con
chip Apple (M1, M2, etc.) o **Importios-macOS-Intel** para un Mac Intel. Extrae el
ZIP, abre el `.dmg` y arrastra **Importios** a **Applications**. Después abre
Importios desde Aplicaciones. No basta con cambiar la extensión de un EXE:
GitHub compila cada aplicación en su sistema correspondiente.

## Versiones publicadas

Cuando se publique una etiqueta `v…`, GitHub generará una versión preliminar en
[Releases](https://github.com/SRJW/importios/releases) con el EXE y los dos DMG
como descargas directas. Las compilaciones normales se guardan durante 30 días;
los archivos de una release se conservan hasta que se retire esa versión.

## Estado y avisos del sistema

Los archivos solo estarán disponibles si la compilación de GitHub termina bien.
Estos paquetes no tienen certificado de firma de Windows ni firma y notarización
de desarrollador de Apple. Windows o macOS pueden mostrar avisos o impedir abrirlos.
No desactives las protecciones del equipo; comunica el mensaje exacto si ocurre.
Un DMG no sustituye la firma ni la notarización.

Esta versión selecciona y analiza audio; **todavía no transfiere canciones al
iPhone**. No hace falta conectar el teléfono y no se modifica su biblioteca.
