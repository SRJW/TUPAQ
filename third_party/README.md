# Componentes de terceros

## Firma fija de metadatos

`importios/sync/signing.py` adapta el algoritmo de
`fbiba/rustunes`, commit `057ee8fc9c9da65795a6f14497fc408c2fe23c76`,
`crates/music-protocol/src/protocol/signing.rs`, con licencia MIT.
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
