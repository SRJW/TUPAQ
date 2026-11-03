#!/bin/sh
set -eu
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
    echo 'Necesitas Python 3.10 o posterior de python.org para esta versión de desarrollo.'
    exit 1
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import mutagen; assert mutagen.version_string == "1.47.0"' 2>/dev/null; then
    .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python -m importios
