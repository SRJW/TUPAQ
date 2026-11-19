"""Comprehensive unit and UI tests for all 9 new TUPAQ features."""
import asyncio
from contextlib import asynccontextmanager, closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QDialog

from test_native_connection import APP
from test_app_files import MemoryAfc
from importios.native import Window
from importios.i18n import set_language


def _png_bytes(width=64, height=64, color=0xFF2288AA):
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(color)
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        path = Path(tmp.name)
    try:
        assert img.save(str(path), 'PNG')
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


class UpdateCheckerTests(unittest.TestCase):
    def test_version_parsing_and_selection_enforces_trusted_urls(self):
        from importios.updates import parse_version, is_newer, select_latest_release

        self.assertGreater(parse_version('v0.3.0'), parse_version('v0.3.0-preview.99'))
        self.assertTrue(is_newer('v0.3.0-preview.36', '0.3.0-preview.35'))
        self.assertFalse(is_newer('v0.3.0-preview.35', '0.3.0-preview.35'))
        self.assertIsNone(parse_version('not-a-version'))

        releases = [
            {'tag_name': 'v0.3.0-preview.99', 'draft': True, 'html_url': 'https://github.com/SRJW/TUPAQ/releases/tag/v0.3.0-preview.99'},
            {'tag_name': 'v9.9.9', 'draft': False, 'html_url': 'https://evil.example/releases/tag/v9.9.9'},
            {'tag_name': 'v0.3.0-preview.37', 'draft': False, 'prerelease': True,
             'html_url': 'https://github.com/SRJW/TUPAQ/releases/tag/v0.3.0-preview.37',
             'assets': [{'name': 'TUPAQ.exe', 'browser_download_url': 'https://github.com/SRJW/TUPAQ/releases/download/v0.3.0-preview.37/TUPAQ.exe'}]},
            {'tag_name': 'v0.3.0-preview.35', 'draft': False,
             'html_url': 'https://github.com/SRJW/TUPAQ/releases/tag/v0.3.0-preview.35'},
        ]
        found = select_latest_release(releases, current='0.3.0-preview.36')
        self.assertTrue(found['available'])
        self.assertEqual(found['tag'], 'v0.3.0-preview.37')
        self.assertEqual(len(found['assets']), 1)

        same = select_latest_release(releases, current='0.3.0-preview.37')
        self.assertFalse(same['available'])


class BatteryTests(unittest.TestCase):
    def test_parse_battery_extracts_bounded_real_metrics_only(self):
        from importios.battery import parse_battery

        raw = {
            'CurrentCapacity': 84,
            'CycleCount': 215,
            'DesignCapacity': 3279,
            'NominalChargeCapacity': 3017,
            'Temperature': 2940,
            'Voltage': 4086,
            'IsCharging': True,
            'ExternalConnected': True,
        }
        parsed = parse_battery(raw)
        self.assertEqual(parsed['charge_percent'], 84)
        self.assertEqual(parsed['cycle_count'], 215)
        self.assertEqual(parsed['design_capacity_mah'], 3279)
        self.assertEqual(parsed['max_capacity_mah'], 3017)
        self.assertEqual(parsed['health_percent'], 92.0)
        self.assertEqual(parsed['temperature_c'], 29.4)
        self.assertEqual(parsed['voltage_v'], 4.09)
        self.assertTrue(parsed['is_charging'])

        # Invalid/out-of-range values are omitted rather than invented.
        bad = {'CurrentCapacity': 150, 'CycleCount': -5, 'DesignCapacity': 0, 'Temperature': 99999, 'Voltage': 50}
        self.assertEqual(parse_battery(bad), {})
        self.assertEqual(parse_battery(None), {})


class DuplicatesTests(unittest.TestCase):
    def test_duplicate_detection_in_library_and_queue(self):
        from importios.duplicates import duplicate_ids_in_library, matches_phone_library

        library = [
            {'id': '1', 'title': 'Canción Uno', 'artist': 'Artista Á', 'duration': 200.0},
            {'id': '2', 'title': 'cancion uno', 'artist': 'artista a', 'duration': 201.5},
            {'id': '3', 'title': 'Canción Uno', 'artist': 'Artista Á', 'duration': 310.0},
            {'id': '4', 'title': 'Única', 'artist': 'Otro', 'duration': 180.0},
        ]
        self.assertEqual(duplicate_ids_in_library(library), {'1', '2'})
        self.assertTrue(matches_phone_library({'title': 'CANCION UNO', 'artist': 'Artista A', 'duration': 200.4}, library))
        self.assertFalse(matches_phone_library({'title': 'Nueva', 'artist': 'Otro', 'duration': 180.0}, library))


class PlaylistsTests(unittest.TestCase):
    def test_read_playlists_and_write_m3u8(self):
        from importios.library import read_catalogue
        from importios.playlists import write_m3u8

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'MediaLibrary.sqlitedb'
            with closing(sqlite3.connect(db_path)) as db:
                db.executescript('''
                    PRAGMA user_version=2410000;
                    CREATE TABLE item(item_pid INTEGER PRIMARY KEY, media_type INTEGER, item_artist_pid INTEGER, album_pid INTEGER, track_number INTEGER);
                    CREATE TABLE item_extra(item_pid INTEGER PRIMARY KEY, title TEXT, total_time_ms REAL, file_size INTEGER, location TEXT);
                    CREATE TABLE item_artist(item_artist_pid INTEGER PRIMARY KEY, item_artist TEXT);
                    CREATE TABLE album(album_pid INTEGER PRIMARY KEY, album TEXT);
                    CREATE TABLE container(container_pid INTEGER PRIMARY KEY, name TEXT, is_hidden INTEGER, smart_is_folder INTEGER, distinguished_kind INTEGER);
                    CREATE TABLE container_item(container_pid INTEGER, item_pid INTEGER, position INTEGER);
                    INSERT INTO item_artist VALUES (1, 'Banda');
                    INSERT INTO album VALUES (1, 'Disco');
                    INSERT INTO item VALUES (10, 8, 1, 1, 1), (20, 8, 1, 1, 2);
                    INSERT INTO item_extra VALUES (10, 'Primera', 180000, 1000, 'F00/AAAA.mp3'), (20, 'Segunda', 210000, 2000, 'F00/BBBB.mp3');
                    INSERT INTO container VALUES (1, 'Biblioteca', 0, 0, 1);
                    INSERT INTO container VALUES (2, 'Oculta', 1, 0, 0);
                    INSERT INTO container VALUES (3, 'Carpeta', 0, 1, 0);
                    INSERT INTO container VALUES (4, 'Favoritas', 0, 0, 0);
                    INSERT INTO container_item VALUES (1, 10, 0), (2, 10, 0), (4, 20, 1), (4, 10, 2);
                ''')
                db.commit()
            playlists = []
            tracks = read_catalogue(db_path, playlists_out=playlists)
            self.assertEqual(len(tracks), 2)
            self.assertEqual({t['id']: t.get('track_number') for t in tracks}, {'10': 1, '20': 2})
            self.assertEqual(len(playlists), 1)
            self.assertEqual(playlists[0]['name'], 'Favoritas')
            self.assertEqual(playlists[0]['track_ids'], ['20', '10'])

            m3u = write_m3u8(Path(tmp) / 'Favoritas.m3u8', [
                {'title': 'Segunda', 'artist': 'Banda', 'duration': 210, 'relative_path': Path('Banda/Disco/02 - Segunda.mp3')},
            ])
            content = m3u.read_text(encoding='utf-8')
            self.assertIn('#EXTM3U', content)
            self.assertIn('#EXTINF:210,Banda - Segunda', content)
            self.assertIn('Banda/Disco/02 - Segunda.mp3', content)


class TranscodeTests(unittest.TestCase):
    def test_flac_converts_to_alac_and_aac_preserving_tags_cover_lyrics_and_original(self):
        import subprocess
        from mutagen.flac import FLAC, Picture
        from importios.transcode import find_ffmpeg, convert_to_m4a
        from importios.audio import inspect_audio, read_artwork
        from importios.lyrics import embedded_lyrics
        from importios.preparation import expand
        import mutagen

        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            self.skipTest('ffmpeg not installed in test environment')

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            flac_path = folder / 'demo.flac'
            subprocess.run(
                [ffmpeg, '-y', '-v', 'error', '-i', 'tests/fixtures/sample.wav', '-c:a', 'flac', str(flac_path)],
                check=True,
            )
            audio = FLAC(flac_path)
            audio['title'] = ['Canción Sin Pérdida']
            audio['artist'] = ['Banda FLAC']
            audio['album'] = ['Disco Master']
            audio['date'] = ['2025']
            audio['tracknumber'] = ['3/10']
            audio['lyrics'] = ['Primera línea\nSegunda línea']
            pic = Picture()
            pic.type = 3
            pic.mime = 'image/png'
            pic.data = _png_bytes()
            audio.add_picture(pic)
            audio.save()

            orig_hash = hashlib.sha256(flac_path.read_bytes()).hexdigest()

            # Folder expansion respects include_convertible flag.
            self.assertEqual(expand([folder], include_convertible=False), [])
            self.assertEqual(expand([folder], include_convertible=True), [flac_path])

            out_dir = folder / 'converted'
            alac_file = convert_to_m4a(flac_path, target_codec='alac', output_dir=out_dir)
            aac_file = convert_to_m4a(flac_path, target_codec='aac', output_dir=out_dir)

            self.assertEqual(hashlib.sha256(flac_path.read_bytes()).hexdigest(), orig_hash)

            alac_info = inspect_audio(alac_file, alac_file.name)
            self.assertEqual(alac_info['container'], 'M4A')
            self.assertEqual(alac_info['format'], 'ALAC')
            self.assertEqual(alac_info['title'], 'Canción Sin Pérdida')
            self.assertEqual(alac_info['artist'], 'Banda FLAC')
            self.assertEqual(alac_info['album'], 'Disco Master')
            self.assertEqual(alac_info['year'], 2025)
            self.assertIsNotNone(read_artwork(alac_file))
            mp4 = mutagen.File(alac_file)
            self.assertIn('Primera línea', embedded_lyrics(mp4.tags).get('lyrics_text', ''))

            aac_info = inspect_audio(aac_file, aac_file.name)
            self.assertEqual(aac_info['container'], 'M4A')
            self.assertEqual(aac_info['format'], 'AAC')
            self.assertEqual(aac_info['title'], 'Canción Sin Pérdida')


class AppFilesAdvancedTests(unittest.TestCase):
    def test_rename_and_conflict_policies_on_upload_and_export(self):
        from importios.app_files import rename_entry, upload_paths, export_entries, AppFilesError

        mem = MemoryAfc()
        mem.dirs.add('/Documents/sub')
        mem.files['/Documents/existing.txt'] = b'old-data'
        mem.files['/Documents/sub/a.txt'] = b'hello'
        afc = mem.as_afc()

        # Rename file cleanly & reject root or duplicate target.
        renamed = asyncio.run(rename_entry(afc, 'sub/a.txt', 'b.txt'))
        self.assertEqual(renamed, 'sub/b.txt')
        self.assertIn('/Documents/sub/b.txt', mem.files)
        self.assertNotIn('/Documents/sub/a.txt', mem.files)
        with self.assertRaises(AppFilesError):
            asyncio.run(rename_entry(afc, '', 'root2'))
        with self.assertRaises(AppFilesError):
            asyncio.run(rename_entry(afc, 'existing.txt', 'sub'))

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'existing.txt'
            src.write_bytes(b'new-data')

            # Upload conflict: skip
            res_skip = asyncio.run(upload_paths(afc, '', [src], conflict_policy='skip'))
            self.assertEqual(res_skip['skipped'], 1)
            self.assertEqual(mem.files['/Documents/existing.txt'], b'old-data')

            # Upload conflict: rename
            res_ren = asyncio.run(upload_paths(afc, '', [src], conflict_policy='rename'))
            self.assertEqual(res_ren['uploaded'], 1)
            self.assertEqual(mem.files['/Documents/existing (2).txt'], b'new-data')

            # Upload conflict: replace
            res_rep = asyncio.run(upload_paths(afc, '', [src], conflict_policy='replace'))
            self.assertEqual(res_rep['uploaded'], 1)
            self.assertEqual(mem.files['/Documents/existing.txt'], b'new-data')

            # Export conflicts: skip, rename, replace
            dest = Path(tmp) / 'out'
            dest.mkdir()
            (dest / 'existing.txt').write_bytes(b'local-old')

            exp_skip = asyncio.run(export_entries(afc, ['existing.txt'], dest, conflict_policy='skip'))
            self.assertEqual(exp_skip['skipped'], 1)
            self.assertEqual((dest / 'existing.txt').read_bytes(), b'local-old')

            exp_ren = asyncio.run(export_entries(afc, ['existing.txt'], dest, conflict_policy='rename'))
            self.assertEqual(exp_ren['exported'], 1)
            self.assertEqual((dest / 'existing (2).txt').read_bytes(), b'new-data')

            exp_rep = asyncio.run(export_entries(afc, ['existing.txt'], dest, conflict_policy='replace'))
            self.assertEqual(exp_rep['exported'], 1)
            self.assertEqual((dest / 'existing.txt').read_bytes(), b'new-data')


class OrganizedExportAndMetadataOverrideTests(unittest.TestCase):
    def test_artist_album_incremental_and_m3u8_export(self):
        from importios.transfers import export_relative_path, export_selected

        track = {
            'id': '1', 'title': 'Sol', 'artist': 'Luna', 'album': 'Noche',
            'track_number': 2, 'duration': 185, 'afc_path': '/iTunes_Control/Music/F00/AAAA.mp3',
        }
        self.assertEqual(export_relative_path(track, 'artist_album'), Path('Luna/Noche/02 - Sol.mp3'))
        self.assertEqual(export_relative_path(track, 'flat'), Path('Luna - Sol.mp3'))

        mp3_bytes = Path('tests/fixtures/sample.mp3').read_bytes()
        mem = MemoryAfc()
        mem.dirs.update({'/iTunes_Control', '/iTunes_Control/Music', '/iTunes_Control/Music/F00'})
        mem.files['/iTunes_Control/Music/F00/AAAA.mp3'] = mp3_bytes
        afc = mem.as_afc()

        @asynccontextmanager
        async def fake_device():
            yield MagicMock(), afc

        async def fake_copy(afc_arg, catalogue_dir, exc_types):
            return [dict(track)]

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            item = dict(track, folder_structure='artist_album', incremental=True, playlist_name='Viaje')
            with patch('importios.transfers.device', fake_device), patch('importios.transfers.copy_catalogue', fake_copy):
                first = asyncio.run(export_selected([item], dest, lambda *a: None))
                self.assertEqual(first['exported'], 1)
                exported_file = dest / 'Luna' / 'Noche' / '02 - Sol.mp3'
                self.assertTrue(exported_file.is_file())
                self.assertTrue((dest / 'Viaje.m3u8').is_file())
                self.assertIn('Luna/Noche/02 - Sol.mp3', (dest / 'Viaje.m3u8').read_text(encoding='utf-8'))

                # Second export in incremental mode skips without creating (2).
                second = asyncio.run(export_selected([item], dest, lambda *a: None))
                self.assertEqual(second['exported'], 0)
                self.assertEqual(second['skipped_existing'], 1)
                self.assertFalse((dest / 'Luna' / 'Noche' / '02 - Sol (2).mp3').exists())

    def test_metadata_overrides_and_custom_artwork_preserve_original_file(self):
        from importios.transfers import plan_entries
        from importios.sync.source import inspect_source

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            src = tmp_dir / 'song.mp3'
            src.write_bytes(Path('tests/fixtures/sample.mp3').read_bytes())
            orig_hash = hashlib.sha256(src.read_bytes()).hexdigest()

            cover = tmp_dir / 'cover.png'
            cover.write_bytes(_png_bytes(120, 120, 0xFFCC4411))

            source = inspect_source(src)
            source.update({
                'title': 'Título Editado',
                'artist': 'Artista Nuevo',
                'album': 'Álbum Nuevo',
                'year': 2024,
                'custom_artwork_path': str(cover),
                'has_artwork': True,
                'send_artwork': True,
            })

            mem = MemoryAfc()
            mem.dirs.update({'iTunes_Control/Music/F00', '/iTunes_Control/Music/F00'})
            afc = mem.as_afc()
            before = {'ids': set(), 'artists': {}, 'albums': {}, 'tracks': {}, 'artwork_ids': set(), 'artwork_known': True, 'lyrics_records': {}}
            work = tmp_dir / 'stage'
            work.mkdir()
            entries = asyncio.run(plan_entries(afc, before, [source], work))

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]['source']['title'], 'Título Editado')
            self.assertEqual(entries[0]['source']['artist'], 'Artista Nuevo')
            self.assertEqual(entries[0]['source']['album'], 'Álbum Nuevo')
            self.assertEqual(entries[0]['source']['year'], 2024)
            self.assertIsNotNone(entries[0].get('artwork'))
            self.assertTrue(Path(entries[0]['artwork']['path']).read_bytes().startswith(b'\xff\xd8'))
            # Original MP3 file is completely untouched!
            self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(), orig_hash)


class AudioPlayerTests(unittest.TestCase):
    def test_player_validates_missing_file_and_stops_cleanly(self):
        from importios.player import AudioPreviewPlayer

        player = AudioPreviewPlayer()
        self.assertFalse(player.is_playing)
        with self.assertRaises(ValueError):
            player.play('/nonexistent/audio.mp3')

        fake_proc = MagicMock()
        fake_proc.poll.return_value = None
        with patch.object(AudioPreviewPlayer, '_build_command', return_value=['true', 'sample.mp3']), \
             patch('importios.player.subprocess.Popen', return_value=fake_proc):
            player.play('tests/fixtures/sample.mp3')
            self.assertTrue(player.is_playing)
            player.stop()
            fake_proc.terminate.assert_called_once()
            self.assertFalse(player.is_playing)


class NewFeaturesUITests(unittest.TestCase):
    def setUp(self):
        self.w = Window(auto_connect=False)
        self.w.show()
        APP.processEvents()

    def tearDown(self):
        self.w.tracks.clear()
        self.w.close()
        self.w.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        set_language('es')

    def test_update_banner_battery_card_and_app_files_controls(self):
        w = self.w
        # Update banner
        w.update_check_result({'available': True, 'version': '0.3.0-preview.99', 'url': 'https://github.com/SRJW/TUPAQ/releases/tag/v0.3.0-preview.99'})
        self.assertTrue(w.update_banner.isVisible())
        self.assertIn('0.3.0-preview.99', w.update_banner_label.text())
        with patch('importios.native.QDesktopServices.openUrl') as open_url:
            w.open_update_release()
            open_url.assert_called_once()

        # Battery card in Diagnostics
        w.device_details = {
            'model': 'iPhone 15 Pro', 'version': '18.2',
            'battery': {'health_percent': 94.0, 'cycle_count': 180, 'charge_percent': 72,
                        'max_capacity_mah': 3070, 'design_capacity_mah': 3274, 'temperature_c': 28.5, 'voltage_v': 3.98, 'is_charging': True},
        }
        w.update_diagnostics()
        self.assertIn('94%', w.diagnostic_fields['battery_health'].text())
        self.assertIn('180', w.diagnostic_fields['battery_health'].text())
        self.assertIn('28.5 °C', w.diagnostic_fields['battery_detail'].text())
        self.assertIn('3.98 V', w.diagnostic_fields['battery_detail'].text())
        self.assertFalse(w.battery_bar.isHidden())

        # App Files search, rename button state, and conflict policy
        w.app_current_bundle = 'org.videolan.vlc-ios'
        w.app_entries = [
            {'name': 'Pelicula.mkv', 'relative': 'Pelicula.mkv', 'kind': 'file', 'size': 1024, 'modified': None},
            {'name': 'Subtitulos.srt', 'relative': 'Subtitulos.srt', 'kind': 'file', 'size': 256, 'modified': None},
        ]
        w.populate_app_table()
        self.assertEqual(w.app_table.rowCount(), 2)
        w.app_search.setText('sub')
        self.assertEqual(w.app_table.rowCount(), 1)
        w.app_table.selectRow(0)
        w.update_buttons()
        self.assertTrue(w.app_rename.isEnabled())
        w.app_conflict.setCurrentIndex(2)  # replace
        with patch.object(w, 'start_app_action') as start_action:
            w.upload_app_paths(['tests/fixtures/sample.mp3'])
            start_action.assert_called_once()
            self.assertEqual(start_action.call_args[0][3]['conflict_policy'], 'replace')

    def test_playlists_duplicates_grid_view_metadata_editor_and_audio_preview(self):
        w = self.w
        tracks = [
            {'id': '1', 'is_local': True, 'title': 'Muestra', 'artist': 'TUPAQ', 'album': 'Disco A', 'duration': 1.0, 'afc_path': '/iTunes_Control/Music/F00/A.mp3', 'format_label': 'MP3'},
            {'id': '2', 'is_local': True, 'title': 'Muestra', 'artist': 'TUPAQ', 'album': 'Disco A', 'duration': 1.0, 'afc_path': '/iTunes_Control/Music/F00/B.mp3', 'format_label': 'MP3'},
            {'id': '3', 'is_local': True, 'title': 'Otra', 'artist': 'Otro', 'album': 'Disco B', 'duration': 200.0, 'afc_path': '/iTunes_Control/Music/F00/C.mp3', 'format_label': 'MP3'},
        ]
        w.playlists = [{'id': 'pl-1', 'name': 'Favoritas', 'track_ids': ['3', '1']}]
        w.refresh_playlist_filter()
        w.show_library(tracks)
        self.assertFalse(w.playlist_filter.isHidden())

        # Playlist filter narrows visible tracks & export preserves exact playlist order
        w.playlist_filter.setCurrentIndex(1)
        self.assertEqual({t['id'] for t in w.library_model.tracks}, {'3', '1'})
        w.library_model.checked.update({'1', '3'})
        with patch('importios.native.QFileDialog.getExistingDirectory', return_value=str(Path.cwd())), \
             patch.object(w, 'start_transfer') as start_transfer:
            w.export_songs()
            start_transfer.assert_called_once()
            exported_items = start_transfer.call_args[0][1]
            self.assertEqual([t['id'] for t in exported_items], ['3', '1'])
            self.assertEqual(exported_items[0]['playlist_name'], 'Favoritas')
        w.library_model.checked.clear()
        w.playlist_filter.setCurrentIndex(0)

        # Duplicates filter on iPhone library
        w.content_filter.setCurrentIndex(3)
        self.assertEqual({t['id'] for t in w.library_model.tracks}, {'1', '2'})
        w.content_filter.setCurrentIndex(0)

        # Album/Artist grid view selection marks whole album
        w.change_library_view_mode(1)
        self.assertEqual(w.library_views.currentIndex(), 1)
        self.assertEqual(w.collection_grid.count(), 2)
        w.collection_grid.item(0).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(w.library_model.checked, {'1', '2'})

        # Double click album filters and returns to Canciones
        w.collection_grid.itemDoubleClicked.emit(w.collection_grid.item(1))
        self.assertEqual(w.library_views.currentIndex(), 0)
        self.assertEqual(w.search.text(), 'Disco B')
        w.clear_filters()

        # Queue duplicate marking + removal + metadata editor + audio preview
        w.accept_track({
            'id': 'local-dup', 'filename': 'sample.mp3', 'path': str(Path('tests/fixtures/sample.mp3').resolve()),
            'title': 'Muestra', 'artist': 'TUPAQ', 'album': 'Disco A', 'format': 'MP3', 'duration': 1.0, 'size': 1234,
        })
        self.assertTrue(w.tracks['local-dup']['in_phone'])
        self.assertEqual(w.queue_status['local-dup'].text(), 'Ya en el iPhone')
        self.assertFalse(w.remove_duplicates.isHidden())

        # Edit metadata via real MetadataEditorDialog widgets (clean Python subclass overriding exec)
        from importios.metadata_editor import MetadataEditorDialog
        class AutoAcceptEditor(MetadataEditorDialog):
            def exec(self):
                self.title_edit.setText('Renombrada')
                self.artist_edit.setText('Nuevo Artista')
                self.album_edit.setText('Nuevo Álbum')
                self.genre_edit.setText('Rock')
                self.year_edit.setText('2026')
                return QDialog.DialogCode.Accepted

        w.table.selectRow(0)
        with patch('importios.metadata_editor.MetadataEditorDialog', AutoAcceptEditor):
            w.edit_selected_metadata()
        self.assertEqual(w.tracks['local-dup']['title'], 'Renombrada')
        self.assertEqual(w.tracks['local-dup']['artist'], 'Nuevo Artista')
        self.assertEqual(w.tracks['local-dup']['year'], 2026)
        self.assertFalse(w.tracks['local-dup']['in_phone'])
        self.assertEqual(w.table.item(0, 0).text(), 'Renombrada')

        # Audio preview toggle starts & stops cleanly
        with patch.object(w.audio_player, 'play') as play_mock, patch.object(w.audio_player, 'stop') as stop_mock:
            w.toggle_audio_preview()
            play_mock.assert_called_once()
            w.inspector_closed()
            stop_mock.assert_called()


if __name__ == '__main__':
    unittest.main()
