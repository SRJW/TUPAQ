import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from importios.library import copy_catalogue, read_catalogue, LibraryError
from importios.library import _read_phone, connection_failure, format_diagnostics


def database(path):
    with closing(sqlite3.connect(path)) as db:
        db.executescript('''CREATE TABLE item(item_pid INTEGER, media_type INTEGER, item_artist_pid INTEGER, album_pid INTEGER);
            CREATE TABLE item_extra(item_pid INTEGER,title TEXT,total_time_ms REAL);
            CREATE TABLE item_artist(item_artist_pid INTEGER,item_artist TEXT);
            CREATE TABLE album(album_pid INTEGER,album TEXT);
            PRAGMA user_version=2410000;
            INSERT INTO item VALUES(1,8,2,3),(4,2,2,3);
            INSERT INTO item_extra VALUES(1,'Canción de prueba',2300),(4,'Vídeo',9000);
            INSERT INTO item_artist VALUES(2,'Artista'); INSERT INTO album VALUES(3,'Álbum');''')


class FakeAfc:
    def __init__(self, body, change=False, wal=None):
        self.body, self.change = body, change
        self.wal = wal
        self.opens = []
        self.offsets = {}
        self.closed = []

    async def stat(self, path):
        if path.endswith('-wal') and self.wal is None:
            raise FileNotFoundError()
        data = self.wal if path.endswith('-wal') else self.body
        return {'st_size': len(data), 'st_ifmt': 'S_IFREG', 'st_mtime': 1}

    async def fopen(self, path, mode):
        assert mode == 'r'
        self.opens.append((path, mode))
        self.offsets[len(self.opens)] = 0
        return len(self.opens)

    async def fread(self, handle, size):
        data = self.wal if self.opens[handle-1][0].endswith('-wal') else self.body
        if self.change and handle == 2:
            data = data[:-1]+bytes([data[-1] ^ 1])
        offset = self.offsets[handle]
        block = data[offset:offset+min(size, 2000)]
        self.offsets[handle] += len(block)
        return block

    async def fclose(self, handle):
        self.closed.append(handle)


class LibraryTests(unittest.TestCase):
    def test_ios27_type8_reference_fixture_returns_one_music_track(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'library.db'
            with closing(sqlite3.connect(path)) as db:
                db.executescript((Path(__file__).parent/'fixtures/library-ios27.sql').read_text())
            diagnostics = {}
            tracks = read_catalogue(path, diagnostics)
            self.assertEqual(diagnostics['schema_version'], 2410000)
            self.assertEqual(diagnostics['media_types'], [{'type':8,'count':1}])
            self.assertEqual(diagnostics['items_total'], 1)
            self.assertEqual(diagnostics['music_items'], 1)
            self.assertEqual(diagnostics['tracks_returned'], 1)
            self.assertEqual(tracks[0]['title'], 'Canción de catálogo iOS 27')

    def test_public_bitmask_and_other_internal_codes_are_not_catalogue_music(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'library.db'
            database(path)
            for kind in [0,1,2,4,9,16,32]:
                with self.subTest(kind=kind):
                    with closing(sqlite3.connect(path)) as db:
                        db.execute('UPDATE item SET media_type=?', (kind,))
                        db.commit()
                    diagnostics = {}
                    self.assertEqual(read_catalogue(path, diagnostics), [])
                    self.assertEqual(diagnostics['music_items'], 0)

    def test_type8_song_only_in_wal_survives_two_read_only_afc_copies(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'source.db'
            database(path)
            with closing(sqlite3.connect(path)) as db:
                db.execute('DELETE FROM item')
                db.execute('DELETE FROM item_extra')
                db.commit()
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('PRAGMA wal_autocheckpoint=0')
                db.execute('INSERT INTO item VALUES(101,8,2,3)')
                db.execute("INSERT INTO item_extra VALUES(101,'Música de prueba en WAL',123000)")
                db.commit()
                afc = FakeAfc(path.read_bytes(), wal=Path(str(path)+'-wal').read_bytes())
            destination = Path(temporary)/'snapshot'
            destination.mkdir()
            diagnostics = {}
            tracks = asyncio.run(copy_catalogue(afc, destination, diagnostics=diagnostics))
            self.assertEqual(len(tracks), 1)
            self.assertEqual(tracks[0]['title'], 'Música de prueba en WAL')
            self.assertEqual(diagnostics['schema_version'], 2410000)
            self.assertEqual(diagnostics['media_types'], [{'type':8,'count':1}])
            self.assertEqual(diagnostics['items_total'], diagnostics['music_items'])
            self.assertEqual(diagnostics['music_items'], diagnostics['tracks_returned'])
            self.assertEqual(diagnostics['music_type_code'], 8)
            self.assertEqual(diagnostics['music_type_comparison'], 'equal')
            self.assertTrue(diagnostics['wal_present'])
            self.assertEqual([mode for _, mode in afc.opens], ['r']*4)
            self.assertEqual(afc.closed, [1,2,3,4])

    def test_music_without_extra_metadata_is_not_silently_discarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'library.db'
            database(path)
            with closing(sqlite3.connect(path)) as db:
                db.execute('DELETE FROM item_extra WHERE item_pid=1')
                db.commit()
            diagnostics = {}
            tracks = read_catalogue(path, diagnostics)
            self.assertEqual(len(tracks), 1)
            self.assertEqual(tracks[0]['title'], 'Sin título')
            self.assertEqual(tracks[0]['duration'], 0)
            self.assertEqual(diagnostics['music_without_extra'], 1)

    def test_readout_counts_distinguish_filter_from_empty_catalogue_without_titles(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'library.db'
            database(path)
            with closing(sqlite3.connect(path)) as db:
                db.execute('UPDATE item SET media_type=2')
                db.commit()
            diagnostics = {}
            self.assertEqual(read_catalogue(path, diagnostics), [])
            self.assertEqual(diagnostics['items_total'], 2)
            self.assertEqual(diagnostics['music_items'], 0)
            self.assertEqual(diagnostics['media_types'], [{'type':2,'count':2}])
            report = format_diagnostics(diagnostics)
            self.assertNotIn('Canción de prueba', report)
            self.assertNotIn(temporary, report)
            with closing(sqlite3.connect(path)) as db:
                db.execute('DELETE FROM item')
                db.commit()
            self.assertEqual(read_catalogue(path, diagnostics), [])
            self.assertEqual(diagnostics['items_total'], 0)
            self.assertEqual(diagnostics['tracks_returned'], 0)

    def test_diagnostic_media_types_do_not_expose_unexpected_text_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'library.db'
            database(path)
            with closing(sqlite3.connect(path)) as db:
                db.execute("UPDATE item SET media_type='private-device-data'")
                db.commit()
            diagnostics = {}
            self.assertEqual(read_catalogue(path, diagnostics), [])
            self.assertNotIn('private-device-data', format_diagnostics(diagnostics))
            self.assertEqual(diagnostics['media_types'], [{'type':None,'count':2}])

    def test_readout_includes_committed_music_present_only_in_copied_wal(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)/'source.db'
            snapshot = Path(temporary)/'MediaLibrary.sqlitedb'
            database(source)
            with closing(sqlite3.connect(source)) as writer:
                writer.execute('PRAGMA journal_mode=WAL')
                writer.execute('PRAGMA wal_autocheckpoint=0')
                writer.execute('INSERT INTO item VALUES(8,8,2,3)')
                writer.execute("INSERT INTO item_extra VALUES(8,'Solo en WAL',5000)")
                writer.commit()
                snapshot.write_bytes(source.read_bytes())
                Path(str(snapshot)+'-wal').write_bytes(Path(str(source)+'-wal').read_bytes())
                diagnostics = {}
                tracks = read_catalogue(snapshot, diagnostics)
                self.assertEqual({t['title'] for t in tracks}, {'Canción de prueba','Solo en WAL'})
                self.assertTrue(diagnostics['wal_present'])
                self.assertGreater(diagnostics['wal_bytes'], 0)
                self.assertEqual(diagnostics['music_items'], 2)

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
        lockdown.paired = False
        lockdown.session_id = None
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
        lockdown.paired = True
        lockdown.session_id = 'synthetic-session'
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
            lockdown.validate_pairing.assert_not_awaited()
            copy.assert_awaited_once()

    def test_sdk_opens_one_session_and_reader_does_not_start_it_again(self):
        from pymobiledevice3.lockdown import LockdownClient
        from pymobiledevice3.exceptions import SessionActiveError

        lockdown = AsyncMock()
        lockdown.__aenter__.return_value = lockdown
        lockdown.paired = False
        lockdown.session_id = None

        async def validate():
            if lockdown.session_id:
                raise SessionActiveError()
            lockdown.paired = True
            lockdown.session_id = 'synthetic-session'
            return True

        lockdown.validate_pairing.side_effect = validate

        async def create(**options):
            # Use the pinned SDK's real initialization helper, which validates
            # existing trust even when automatic pairing is disabled.
            await LockdownClient._handle_autopair(lockdown, options['autopair'], None)
            return lockdown

        afc = AsyncMock()
        afc.__aenter__.return_value = afc
        with patch('pymobiledevice3.usbmux.list_devices', new_callable=AsyncMock) as devices, \
             patch('pymobiledevice3.lockdown.create_using_usbmux', side_effect=create) as factory, \
             patch('pymobiledevice3.services.afc.AfcService', return_value=afc), \
             patch('importios.library.copy_catalogue', new_callable=AsyncMock, return_value=[]) as copy:
            devices.return_value = [SimpleNamespace(is_usb=True, serial='synthetic-test-id')]
            self.assertEqual(asyncio.run(_read_phone()), [])
            self.assertFalse(factory.call_args.kwargs['autopair'])
            lockdown.validate_pairing.assert_awaited_once()
            lockdown.pair.assert_not_awaited()
            copy.assert_awaited_once()
            lockdown.__aexit__.assert_awaited_once()

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
