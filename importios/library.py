"""Read a stable local copy of the phone catalogue. No remote write API is used."""
import asyncio
from contextlib import closing
import hashlib
import math
from pathlib import Path
import sqlite3
import tempfile

REMOTE_DB = '/iTunes_Control/iTunes/MediaLibrary.sqlitedb'
MAX_FILE = 128*1024*1024
MAX_TRACKS = 100_000


class LibraryError(Exception):
    pass


def read_catalogue(path):
    """Query the local snapshot only, accepting the documented item/extra schema."""
    try:
        with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise LibraryError('La copia de la biblioteca no pasó la comprobación de integridad.')
            required = {'item': {'item_pid', 'media_type', 'item_artist_pid', 'album_pid'},
                        'item_extra': {'item_pid', 'title', 'total_time_ms'},
                        'item_artist': {'item_artist_pid', 'item_artist'},
                        'album': {'album_pid', 'album'}}
            for table, columns in required.items():
                found = {row[1] for row in db.execute(f'PRAGMA table_info("{table}")')}
                if not columns <= found:
                    raise LibraryError('La estructura de esta biblioteca todavía no es compatible con el lector.')
            rows = db.execute('''SELECT i.item_pid, e.title, a.item_artist, b.album, e.total_time_ms
                FROM item i JOIN item_extra e ON e.item_pid=i.item_pid
                LEFT JOIN item_artist a ON a.item_artist_pid=i.item_artist_pid
                LEFT JOIN album b ON b.album_pid=i.album_pid
                WHERE (i.media_type & 1) != 0 ORDER BY e.title, i.item_pid LIMIT ?''', (MAX_TRACKS+1,)).fetchall()
            if len(rows) > MAX_TRACKS:
                raise LibraryError('La biblioteca supera el límite de 100.000 canciones de esta versión.')
            tracks = []
            for pid, title, artist, album, ms in rows:
                if any(value is not None and not isinstance(value, str) for value in [title, artist, album]):
                    raise LibraryError('El catálogo contiene metadatos de un tipo no admitido.')
                duration = float(ms or 0)/1000
                if not math.isfinite(duration):
                    raise LibraryError('El catálogo contiene una duración no válida.')
                tracks.append({'id': str(pid), 'title': title or 'Sin título', 'artist': artist or 'Sin artista',
                               'album': album or 'Sin álbum', 'duration': max(0, duration)})
            return tracks
    except (sqlite3.Error, OSError, ValueError, TypeError) as error:
        raise LibraryError('No se pudo leer una copia válida de la biblioteca de Música.') from error


async def copy_catalogue(afc, directory, missing_errors=(FileNotFoundError,)):
    """Two consecutive identical db+WAL reads, always opening AFC in mode 'r'."""
    directory = Path(directory)
    fingerprints = []
    for pass_number in range(2):
        folder = directory/str(pass_number)
        folder.mkdir()
        current = {}
        for suffix in ['', '-wal']:
            remote = REMOTE_DB+suffix
            try:
                before = await afc.stat(remote)
            except missing_errors:
                if suffix:
                    current[suffix] = None
                    continue
                raise LibraryError('No se encontró la biblioteca de Música en el iPhone.')
            size = before.get('st_size', -1)
            if before.get('st_ifmt') != 'S_IFREG' or not isinstance(size, int) or not 0 <= size <= MAX_FILE:
                raise LibraryError('La biblioteca contiene un archivo de tamaño o tipo no admitido.')
            handle = await afc.fopen(remote, 'r')
            target = folder/('MediaLibrary.sqlitedb'+suffix)
            try:
                with target.open('xb') as output:
                    remaining = size
                    while remaining:
                        block = await afc.fread(handle, min(1024*1024, remaining))
                        if not block or len(block) > remaining:
                            raise LibraryError('La copia de la biblioteca quedó incompleta.')
                        output.write(block)
                        remaining -= len(block)
            finally:
                await afc.fclose(handle)
            after = await afc.stat(remote)
            if any(before.get(key) != after.get(key) for key in ['st_size', 'st_mtime', 'st_ifmt']):
                raise LibraryError('La biblioteca está cambiando. Espera a que termine la actividad de Música e inténtalo de nuevo.')
            with target.open('rb') as stream:
                current[suffix] = hashlib.file_digest(stream, 'sha256').hexdigest()
        fingerprints.append(current)
    if fingerprints[0] != fingerprints[1]:
        raise LibraryError('La biblioteca cambió durante la lectura. Vuelve a intentarlo cuando esté estable.')
    return read_catalogue(directory/'1'/'MediaLibrary.sqlitedb')


async def _read_phone():
    # Imported explicitly so the desktop packager discovers all runtime modules.
    from pymobiledevice3 import usbmux
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService, AfcFileNotFoundError

    devices = [device for device in await usbmux.list_devices() if device.is_usb]
    if len(devices) != 1:
        raise LibraryError('Conecta un solo iPhone por USB y desbloquéalo para leer su biblioteca.')
    lockdown = await create_using_usbmux(serial=devices[0].serial, connection_type='USB', autopair=False,
                                       label='Importios')
    async with lockdown:
        if not await lockdown.validate_pairing():
            raise LibraryError('El ordenador necesita una autorización de confianza existente. Desbloquea el iPhone y comprueba su conexión con Windows o Finder; Importios no crea emparejamientos automáticamente.')
        async with AfcService(lockdown) as afc:
            with tempfile.TemporaryDirectory(prefix='importios-library-') as directory:
                return await copy_catalogue(afc, directory, (FileNotFoundError, AfcFileNotFoundError))


def read_phone_library():
    try:
        return asyncio.run(asyncio.wait_for(_read_phone(), timeout=120))
    except LibraryError:
        raise
    except Exception as error:
        # Do not expose pairing records or device identifiers in UI diagnostics.
        raise LibraryError('No se pudo consultar Música. Comprueba el cable, el desbloqueo y la confianza del ordenador. La biblioteca del teléfono no se ha modificado.') from error
