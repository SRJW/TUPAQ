# Evidencia reproducible de sincronización

Este directorio contiene herramientas de análisis estático y resultados, no un
cliente de sincronización. No carga DLL, no abre conexiones y no escribe al iPhone.

`inspect_media.py` lee la DLL aportada, verifica su SHA-256 y usa `objdump` para
registrar referencias y llamadas dentro de funciones ya identificadas. Rechaza
otras versiones: los límites de funciones no pueden trasladarse entre binarios.
El resultado separa referencias a cadenas, llamadas a importaciones, llamadas
directas y llamadas a punteros cuyo destino aún debe resolverse.

En Linux, con GNU objdump instalado:

```sh
python3 -m venv /tmp/importios-research
/tmp/importios-research/bin/python -m pip install -r research/requirements.txt
/tmp/importios-research/bin/python research/inspect_media.py /ruta/idm_media.dll /tmp/evidence.json
```

La DLL no se distribuye en el repositorio. `media-evidence.json` conserva las
direcciones y referencias obtenidas de la versión aportada. No incluye el binario
ni un volcado completo de su código. La herramienta es específica de esta muestra;
no pretende ser un descompilador general ni una demostración de soporte para iOS.

Consulta [el informe de segunda fase](SINCRONIZACION.md).
