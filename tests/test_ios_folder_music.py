"""End-to-end tests for both iOS folder music flows:
1. iPhone Music Library -> iOS app /Documents folder (export_app)
2. iOS app /Documents folder -> Import queue -> iPhone Music (stage_music)
"""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent

from importios.app_files import TEMP_PREFIX, stage_audio_for_import
from importios.i18n import set_language
from importios.library import read_catalogue
from importios.native import Window
from importios.transfers import PREF, run_transfer
from test_app_files import MemoryAfc
from test_format_export import FIXTURES, build_phone
from test_native_connection import APP


def _run_export_app(phone, app_fs, selected, destination, progress=None):
    @asynccontextmanager
    async def fake_app_docs(_lockdown, _bundle_id):
        yield app_fs.as_afc()

    with (
        patch('importios.transfers.device', phone.device),
        patch('importios.app_files.app_documents_on_lockdown', fake_app_docs),
    ):
        return run_transfer('export_app', selected, destination, progress or (lambda *args: None))


class IosFolderMusicTransferTests(unittest.TestCase):
    def tearDown(self):
        set_language('es')

    def _catalogue_tracks(self, phone):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'MediaLibrary.sqlitedb'
            db_path.write_bytes(phone.files[PREF + 'MediaLibrary.sqlitedb'])
            return read_catalogue(db_path)

    def test_copy_music_to_ios_app_flat_organized_and_conflict_policies(self):
        mp3_bytes = (FIXTURES / 'sample.mp3').read_bytes()
        m4a_bytes = (FIXTURES / 'covered-aac.m4a').read_bytes()
        phone = build_phone([
            {'title': 'Amanecer', 'location': 'A.mp3', 'audio_format': 301, 'bytes': mp3_bytes},
            {'title': 'Horizonte', 'location': 'B.m4a', 'audio_format': 502, 'bytes': m4a_bytes},
        ])
        tracks = self._catalogue_tracks(phone)
        app_fs = MemoryAfc()

        # 1. Organized copy into subfolder /Documents/Mi Música/Artist/Album/...
        dest = {
            'bundle_id': 'org.videolan.vlc-ios',
            'subfolder': 'Mi Música',
            'structure': 'artist_album',
            'conflict_policy': 'skip',
        }
        result = _run_export_app(phone, app_fs, tracks, dest)
        self.assertEqual(result['copied_to_app'], 2)
        self.assertEqual(result.get('skipped_existing', 0), 0)
        self.assertEqual(len(result['files']), 2)
        for remote in result['files']:
            self.assertTrue(remote.startswith('/Documents/Mi Música/'))
            self.assertIn(remote, app_fs.files)
        # Verify exact audio bytes match originals and no leftover temp files.
        copied_payloads = {bytes(app_fs.files[p]) for p in result['files']}
        self.assertEqual(copied_payloads, {mp3_bytes, m4a_bytes})
        self.assertFalse(any(TEMP_PREFIX in path for path in app_fs.files))

        # 2. Repeat with policy='skip': skips both without re-copying.
        repeat_skip = _run_export_app(phone, app_fs, tracks, dest)
        self.assertEqual(repeat_skip['copied_to_app'], 0)
        self.assertEqual(repeat_skip['skipped_existing'], 2)

        # 3. Repeat with policy='rename': creates (2) copies alongside originals.
        dest_rename = dict(dest, conflict_policy='rename')
        repeat_rename = _run_export_app(phone, app_fs, tracks[:1], dest_rename)
        self.assertEqual(repeat_rename['copied_to_app'], 1)
        self.assertIn(' (2).mp3', repeat_rename['files'][0])
        self.assertEqual(bytes(app_fs.files[repeat_rename['files'][0]]), mp3_bytes)

        # 4. Repeat with policy='replace': overwrites in place cleanly.
        dest_replace = dict(dest, conflict_policy='replace')
        repeat_replace = _run_export_app(phone, app_fs, tracks[:1], dest_replace)
        self.assertEqual(repeat_replace['copied_to_app'], 1)
        self.assertEqual(repeat_replace['files'][0], result['files'][0])

    def test_copy_music_to_ios_app_enforces_format_filter(self):
        mp3_bytes = (FIXTURES / 'sample.mp3').read_bytes()
        wav_bytes = (FIXTURES / 'sample.wav').read_bytes()
        phone = build_phone([
            {'title': 'Solo MP3', 'location': 'A.mp3', 'audio_format': 301, 'bytes': mp3_bytes},
            {'title': 'Solo WAV', 'location': 'B.wav', 'audio_format': 701, 'bytes': wav_bytes},
        ])
        tracks = [dict(t, expected_format='MP3') for t in self._catalogue_tracks(phone)]
        app_fs = MemoryAfc()
        dest = {'bundle_id': 'org.videolan.vlc-ios', 'subfolder': '', 'structure': 'flat', 'conflict_policy': 'skip'}
        result = _run_export_app(phone, app_fs, tracks, dest)
        self.assertEqual(result['copied_to_app'], 1)
        self.assertEqual(result['skipped_format'], 1)
        self.assertEqual(len(app_fs.files), 1)
        self.assertEqual(bytes(next(iter(app_fs.files.values()))), mp3_bytes)

    def test_stage_audio_for_import_filters_recursive_audio_and_convertible(self):
        mp3_bytes = (FIXTURES / 'sample.mp3').read_bytes()
        wav_bytes = (FIXTURES / 'sample.wav').read_bytes()
        app_fs = MemoryAfc()
        app_fs.add_dir('/Documents/Album')
        app_fs.add_dir('/Documents/Album/Disc2')
        app_fs.add_file('/Documents/Album/track.mp3', mp3_bytes)
        app_fs.add_file('/Documents/Album/Disc2/track.mp3', wav_bytes)
        app_fs.add_file('/Documents/Album/notes.pdf', b'%PDF-1.4')
        app_fs.add_file('/Documents/Album/lossless.flac', b'fLaC0000')

        with tempfile.TemporaryDirectory() as tmp:
            res_native = asyncio.run(stage_audio_for_import(app_fs.as_afc(), ['Album'], tmp, allow_convert=False))
            self.assertEqual(len(res_native['staged']), 2)
            self.assertEqual(res_native['skipped_non_audio'], 1)
            self.assertEqual(res_native['skipped_convertible'], 1)
            names = sorted(Path(p).name for p in res_native['staged'])
            self.assertEqual(names, ['track (2).mp3', 'track.mp3'])

        with tempfile.TemporaryDirectory() as tmp:
            res_conv = asyncio.run(stage_audio_for_import(app_fs.as_afc(), ['Album'], tmp, allow_convert=True))
            self.assertEqual(len(res_conv['staged']), 3)
            self.assertEqual(res_conv['skipped_non_audio'], 1)
            self.assertEqual(res_conv['skipped_convertible'], 0)
            self.assertTrue(any(Path(p).name == 'lossless.flac' for p in res_conv['staged']))


class IosFolderMusicUITests(unittest.TestCase):
    def setUp(self):
        self.window = Window(auto_connect=False)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.tracks.clear()
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        set_language('es')

    def test_app_files_send_to_music_button_stages_and_loads_import_queue(self):
        w = self.window
        w.navigate(4)
        w.app_current_bundle = 'org.videolan.vlc-ios'
        w.app_list = [{'bundle_id': 'org.videolan.vlc-ios', 'name': 'VLC', 'version': '3.5'}]
        w.app_entries = [
            {'name': 'sample.mp3', 'relative': 'sample.mp3', 'kind': 'file', 'size': 12345, 'modified': None},
            {'name': 'notes.pdf', 'relative': 'notes.pdf', 'kind': 'file', 'size': 400, 'modified': None},
        ]
        w.populate_app_table()
        w.update_buttons()
        self.assertFalse(w.app_send_music.isEnabled())

        sample_row = next(r for r in range(w.app_table.rowCount()) if w.app_table.item(r, 0).text() == 'sample.mp3')
        w.app_table.selectRow(sample_row)
        APP.processEvents()
        self.assertTrue(w.app_send_music.isEnabled())

        with patch.object(w, 'start_app_action') as start:
            w.send_app_entries_to_music()
            start.assert_called_once()
            action, bundle, rel, payload = start.call_args.args
            self.assertEqual(action, 'stage_music')
            self.assertEqual(bundle, 'org.videolan.vlc-ios')
            self.assertEqual(rel, '')
            self.assertEqual(payload['items'], ['sample.mp3'])
            self.assertTrue(Path(payload['destination']).is_dir())
            staged_dir = w.app_import_temp_dir

        # Simulate staged completion handing off to Import queue.
        staged_file = staged_dir / 'sample.mp3'
        staged_file.write_bytes((FIXTURES / 'sample.mp3').read_bytes())
        w.app_action_result({'action': 'stage_music', 'staged': [str(staged_file)], 'skipped_non_audio': 0, 'skipped_convertible': 0, 'cancelled': False})
        w.app_action_finished()
        deadline = time.monotonic() + 5
        while w.worker is not None and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(0.005)
        self.assertEqual(w.pages.currentIndex(), 2)
        self.assertEqual(len(w.tracks), 1)
        # Clearing and closing removes the temporary staging directory cleanly.
        w.tracks.clear()
        w.close()
        self.assertFalse(staged_dir.exists())

    def test_copy_to_ios_folder_fetches_apps_and_translates_result_es_en(self):
        w = self.window
        w.connection_token = 'tok-1'
        w.show_library([{
            'id': 'a', 'title': 'Alpha', 'artist': 'Artist', 'album': 'Album',
            'duration': 42, 'size': 10 * 1024**2, 'is_local': True, 'usb_exists': True,
            'afc_path': 'iTunes_Control/Music/F00/AAAA.mp3', 'format_label': 'MP3',
        }])
        w.library_model.checked.add('a')
        w.checks_changed()

        # When app_list is not loaded yet, copy_songs_to_ios_folder triggers list_apps with pending_ios_copy.
        with patch.object(w, 'start_app_action') as start:
            w.copy_songs_to_ios_folder()
            self.assertTrue(w.pending_ios_copy)
            start.assert_called_once_with('list_apps')
        w.pending_ios_copy = False

        # Verify transfer_result messages for copied_to_app in ES and EN.
        w.transfer_result({'copied_to_app': 2, 'bundle_id': 'org.videolan.vlc-ios', 'skipped_existing': 1})
        self.assertIn('2 canciones copiadas y verificadas en la carpeta del iPhone.', w.status.text())
        self.assertIn('1 omitidos (ya existían).', w.status.text())

        w.language_choice.setCurrentIndex(1)
        APP.processEvents()
        w.transfer_result({'copied_to_app': 2, 'bundle_id': 'org.videolan.vlc-ios'})
        self.assertEqual(w.status.text(), '2 songs copied and verified in the iPhone folder.')
        self.assertEqual(w.app_send_music.text(), 'Send to Music')
