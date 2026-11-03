# Componentes de terceros

## Firma y protocolo ATC

`importios/sync/signing.py` adapta el algoritmo de
`fbiba/rustunes`, commit `057ee8fc9c9da65795a6f14497fc408c2fe23c76`,
`crates/music-protocol/src/protocol/signing.rs`, con licencia MIT.
`importios/sync/protocol.py` adapta los mecanismos de `protocol/templates.rs`,
`alac.rs`, `mpeg.rs`, `session.rs` y `catalogue/identity.rs`, `anchor.rs` del
mismo commit. La proyección de formatos y las consultas de catálogo se contrastan
con `media/format.rs` y `catalogue/sqlite.rs`. `transfers.py` integra esas piezas
con pymobiledevice3 y verifica copias y resultados; no ejecuta el CLI de rustunes.

Los vectores sintéticos de `tests/fixtures/sync` proceden del mismo proyecto.
Copyright (c) 2026 Feim Biba. Licencia completa: `rustunes-LICENSE.txt`.

No se incorporó código de go-tunes ni se redistribuyen DLL de Apple o 3uTools.

## Dependencias de escritorio

Los paquetes incluyen Python, Mutagen (GPL-2.0-or-later), PySide6/Qt (opción LGPLv3)
y PyCryptodomex (BSD/public domain según componente). PyInstaller usa su licencia
GPL con excepción para los programas empaquetados. Las versiones se fijan en los
archivos requirements y GitHub adjunta un inventario por plataforma.

Fuentes y licencias de los componentes:

- https://github.com/quodlibet/mutagen
- https://code.qt.io/pyside/pyside-setup.git
- https://www.qt.io/licensing/open-source-lgpl-obligations
- https://github.com/Legrandin/pycryptodome
- https://github.com/pyinstaller/pyinstaller
- https://www.python.org/downloads/source/

El código de Importios se publica en este repositorio. Las bibliotecas se
empaquetan sin modificar; no se impone restricción de ingeniería inversa para
depuraciones de modificaciones a las bibliotecas LGPL.

La lectura del catálogo usa pymobiledevice3 11.49.5 (GPL-3.0), incluida como
dependencia del paquete. Se usa la comunicación USB/lockdown/AFC, reutilizando
la confianza existente, y ServiceConnection para el canal ATC propio. Fuente: https://github.com/doronz88/pymobiledevice3 .
