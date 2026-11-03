import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from importios.library import copy_catalogue, read_catalogue, LibraryError
from importios.library import _read_phone, connection_failure


def database(path):
    with closing(sqlite3.connect(path)) as db:
        db.executescript('''CREATE TABLE item(item_pid INTEGER, media_type INTEGER, item_artist_pid INTEGER, album_pid INTEGER);
            CREATE TABLE item_extra(item_pid INTEGER,title TEXT,total_time_ms REAL);
            CREATE TABLE item_artist(item_artist_pid INTEGER,item_artist TEXT);
            CREATE TABLE album(album_pid INTEGER,album TEXT);
            INSERT INTO item VALUES(1,1,2,3),(4,2,2,3);
            INSERT INTO item_extra VALUES(1,'Canción de prueba',2300),(4,'Vídeo',9000);
            INSERT INTO item_artist VALUES(2,'Artista'); INSERT INTO album VALUES(3,'Álbum');''')


class FakeAfc:
    def __init__(self, body, change=False):
        self.body, self.change = body, change
        self.opens = []
        self.offsets = {}
        self.closed = []

    async def stat(self, path):
        if path.endswith('-wal'):
            raise FileNotFoundError()
        return {'st_size': len(self.body), 'st_ifmt': 'S_IFREG', 'st_mtime': 1}

    async def fopen(self, path, mode):
        assert mode == 'r'
        self.opens.append((path, mode))
        self.offsets[len(self.opens)] = 0
        return len(self.opens)

    async def fread(self, handle, size):
        data = self.body
        if self.change and handle == 2:
            data = data[:-1]+bytes([data[-1] ^ 1])
        offset = self.offsets[handle]
        block = data[offset:offset+min(size, 2000)]
        self.offsets[handle] += len(block)
        return block

    async def fclose(self, handle):
        self.closed.append(handle)


class LibraryTests(unittest.TestCase):
    def test_diagnostic_omits_exception_payload_and_device_identifiers(self):
        error = connection_failure(OSError('SECRET-PAIR-RECORD device-id path'), 'lockdown')
        self.assertEqual(error.diagnostic, 'lockdown:OSError')
        self.assertNotIn('SECRET', str(error))
        self.assertNotIn('device-id', str(error))
        missing = ModuleNotFoundError('private payload', name='pymobiledevice3.lockdown')
        self.assertEqual(connection_failure(missing, 'modules').diagnostic,
                         'modules:ModuleNotFoundError:pymobiledevice3.lockdown')
        missing.name = '/private/path'
        self.assertEqual(connection_failure(missing, 'modules').diagnostic,
                         'modules:ModuleNotFoundError')

    def test_usb_failure_identifies_stage_without_attempting_pairing(self):
        with patch('pymobiledevice3.usbmux.list_devices', new_callable=AsyncMock) as devices, \
             patch('pymobiledevice3.lockdown.create_using_usbmux', new_callable=AsyncMock) as create:
            devices.side_effect = ConnectionRefusedError('private payload')
            with self.assertRaises(LibraryError) as caught:
                asyncio.run(_read_phone())
            self.assertEqual(caught.exception.diagnostic, 'usb:ConnectionRefusedError')
            self.assertNotIn('private payload', str(caught.exception))
            create.assert_not_awaited()

    def test_missing_trust_never_opens_the_file_service(self):
        lockdown = AsyncMock()
        lockdown.__aenter__.return_value = lockdown
        lockdown.validate_pairing.return_value = False
        with patch('pymobiledevice3.usbmux.list_devices', new_callable=AsyncMock) as devices, \
             patch('pymobiledevice3.lockdown.create_using_usbmux', new_callable=AsyncMock) as create, \
             patch('pymobiledevice3.services.afc.AfcService') as afc:
            devices.return_value = [SimpleNamespace(is_usb=True, serial='synthetic-test-id')]
            create.return_value = lockdown
            with self.assertRaisesRegex(LibraryError, 'confianza'):
                asyncio.run(_read_phone())
            afc.assert_not_called()

    def test_phone_reader_reuses_trust_without_automatic_pairing(self):
        lockdown = AsyncMock()
        lockdown.__aenter__.return_value = lockdown
        lockdown.validate_pairing.return_value = True
        afc = AsyncMock()
        afc.__aenter__.return_value = afc
        with patch('pymobiledevice3.usbmux.list_devices', new_callable=AsyncMock) as devices, \
             patch('pymobiledevice3.lockdown.create_using_usbmux', new_callable=AsyncMock) as create, \
             patch('pymobiledevice3.services.afc.AfcService', return_value=afc), \
             patch('importios.library.copy_catalogue', new_callable=AsyncMock) as copy:
            devices.return_value = [SimpleNamespace(is_usb=True, serial='synthetic-test-id')]
            create.return_value = lockdown
            copy.return_value = []
            self.assertEqual(asyncio.run(_read_phone()), [])
            self.assertFalse(create.call_args.kwargs['autopair'])
            lockdown.validate_pairing.assert_awaited_once()
            copy.assert_awaited_once()

    def test_catalogue_is_read_only_filters_music_and_joins_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'library.db'
            database(path)
            before = path.read_bytes()
            tracks = read_catalogue(path)
            self.assertEqual(len(tracks), 1)
            self.assertEqual(tracks[0], {'id':'1','title':'Canción de prueba','artist':'Artista','album':'Álbum','duration':2.3})
            self.assertEqual(before, path.read_bytes())

    def test_consistent_double_copy_uses_read_mode_and_closes_handles(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'library.db'
            database(path)
            afc = FakeAfc(path.read_bytes())
            target = Path(temporary)/'snapshot';target.mkdir()
            tracks = asyncio.run(copy_catalogue(afc, target))
            self.assertEqual(len(tracks), 1)
            self.assertEqual([mode for _, mode in afc.opens], ['r','r'])
            self.assertEqual(afc.closed, [1,2])

    def test_changing_remote_copy_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'library.db'
            database(path)
            target = Path(temporary)/'snapshot';target.mkdir()
            with self.assertRaisesRegex(LibraryError, 'cambió'):
                asyncio.run(copy_catalogue(FakeAfc(path.read_bytes(), change=True), target))

    def test_unknown_schema_and_invalid_database_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'unknown.db'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE unrelated(value TEXT)')
                db.commit()
            with self.assertRaisesRegex(LibraryError, 'estructura'):
                read_catalogue(path)
            path.write_bytes(b'not a database')
            with self.assertRaises(LibraryError):
                read_catalogue(path)
