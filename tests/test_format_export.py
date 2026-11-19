"""Strict format filtering and byte-verified export across all supported audio formats."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QFileDialog

from importios.i18n import set_language
from importios.library import read_catalogue
from importios.library_fields import format_label
from importios.native import Window
from importios.remote_details import detect_file_format_label
from importios.search import matches_format, suffix_matches_format
from importios.transfers import PREF, run_transfer
from test_native_connection import APP
from test_transfers import Phone as BasePhone

FIXTURES = Path(__file__).parent / 'fixtures'


class SeekablePhone(BasePhone):
    async def fseek(self, handle, offset):
        self.handles[handle][1] = offset


def build_phone(entries, seekable=True):
    phone = SeekablePhone() if seekable else BasePhone()
    with closing(sqlite3.connect(':memory:')) as db:
        db.deserialize(phone.files[PREF + 'MediaLibrary.sqlitedb'])
        db.executescript('DELETE FROM item; DELETE FROM item_extra; DELETE FROM item_playback; DELETE FROM item_store;')
        for idx, entry in enumerate(entries, start=1):
            db.execute('INSERT INTO item(item_pid,media_type,item_artist_pid,album_pid,base_location_id) VALUES(?,8,2,3,1)', (idx,))
            db.execute('INSERT INTO item_extra(item_pid,title,total_time_ms,location) VALUES(?,?,1044,?)',
                       (idx, entry['title'], entry['location']))
            if entry.get('audio_format') is not None:
                db.execute('INSERT INTO item_playback(item_pid,audio_format) VALUES(?,?)', (idx, entry['audio_format']))
            db.execute('INSERT INTO item_store(item_pid,sync_id) VALUES(?,?)', (idx, 100 + idx))
            phone.files['/iTunes_Control/Music/F00/' + entry['location']] = entry['bytes']
        db.commit()
        phone.files[PREF + 'MediaLibrary.sqlitedb'] = db.serialize()
    return phone


def run_export(phone, selected, out_dir):
    with patch('importios.transfers.device', phone.device), patch('importios.transfers.Atc', lambda peer: peer):
        return run_transfer('export', selected, out_dir, lambda *args: None)


class FormatFilteringAndExportTests(unittest.TestCase):
    def tearDown(self):
        set_language('es')

    def test_catalogue_format_label_rejects_contradictory_extensions_for_all_formats(self):
        valid = [
            (301, 'F00/A.mp3', 'MP3'),
            (302, 'F00/A.mp3', 'MP3'),
            (303, 'F00/A.mp3', 'MP3'),
            (601, 'F00/A.m4a', 'M4A · ALAC'),
            (601, 'F00/A.alac', 'M4A · ALAC'),
            (502, 'F00/A.m4a', 'M4A · AAC'),
            (508, 'F00/A.m4a', 'M4A · AAC'),
            (509, 'F00/A.m4a', 'M4A · AAC'),
            (1001, 'F00/A.m4a', 'M4A · AAC'),
            (502, 'F00/A.m4p', 'M4P · protegido'),
            (701, 'F00/A.wav', 'WAV'),
            (701, 'F00/A.aif', 'AIFF'),
            (701, 'F00/A.aiff', 'AIFF'),
        ]
        for code, path, expected in valid:
            with self.subTest(valid=(code, path)):
                self.assertEqual(format_label(code, path), expected)

        contradictions = [
            (301, 'F00/A.m4a'),
            (302, 'F00/A.m4a'),
            (303, 'F00/A.wav'),
            (301, 'F00/A.aif'),
            (301, 'F00/A.m4p'),
            (601, 'F00/A.mp3'),
            (601, 'F00/A.wav'),
            (601, 'F00/A.aiff'),
            (502, 'F00/A.mp3'),
            (508, 'F00/A.wav'),
            (1001, 'F00/A.aif'),
            (701, 'F00/A.mp3'),
            (701, 'F00/A.m4a'),
        ]
        for code, path in contradictions:
            with self.subTest(contradiction=(code, path)):
                self.assertIsNone(format_label(code, path))

    def test_search_rejects_contradictory_unverified_labels_across_all_formats(self):
        cases = [
            ({'format_label': 'MP3', 'format_source': 'catalogue', 'afc_path': 'F00/A.m4a'}, 'M4A', ('MP3', 'WAV', 'AIFF', 'AAC', 'ALAC')),
            ({'format_label': 'M4A · AAC', 'format_source': 'catalogue', 'afc_path': 'F00/A.mp3'}, 'MP3', ('M4A', 'AAC', 'ALAC', 'WAV', 'AIFF')),
            ({'format_label': 'M4A · ALAC', 'format_source': 'catalogue', 'afc_path': 'F00/A.wav'}, 'WAV', ('M4A', 'ALAC', 'AAC', 'MP3', 'AIFF')),
            ({'format_label': 'WAV', 'format_source': 'catalogue', 'afc_path': 'F00/A.aif'}, 'AIFF', ('WAV', 'MP3', 'M4A', 'AAC', 'ALAC')),
            ({'format_label': 'AIFF', 'format_source': 'catalogue', 'afc_path': 'F00/A.wav'}, 'WAV', ('AIFF', 'MP3', 'M4A', 'AAC', 'ALAC')),
        ]
        for track, expected, rejected in cases:
            with self.subTest(path=track['afc_path'], claimed=track['format_label']):
                self.assertTrue(matches_format(track, expected))
                for fmt in rejected:
                    self.assertFalse(matches_format(track, fmt), fmt)

    def test_detect_file_format_label_identifies_all_formats_without_extension(self):
        expected = {
            'sample.mp3': 'MP3',
            'aac.m4a': 'M4A · AAC',
            'covered-aac.m4a': 'M4A · AAC',
            'sample.m4a': 'M4A · ALAC',
            'sample.wav': 'WAV',
            'sample.aiff': 'AIFF',
        }
        with tempfile.TemporaryDirectory() as root:
            for name, label in expected.items():
                part = Path(root) / 'audio.part'
                part.write_bytes((FIXTURES / name).read_bytes())
                self.assertEqual(detect_file_format_label(part), label, name)
            garbage = Path(root) / 'garbage.part'
            garbage.write_bytes(b'not an audio file at all')
            self.assertIsNone(detect_file_format_label(garbage))

    def test_export_selected_blocks_wrong_extension_and_disguised_bytes_for_every_format(self):
        mp3_bytes = (FIXTURES / 'sample.mp3').read_bytes()
        aac_bytes = (FIXTURES / 'aac.m4a').read_bytes()
        alac_bytes = (FIXTURES / 'sample.m4a').read_bytes()
        wav_bytes = (FIXTURES / 'sample.wav').read_bytes()
        aiff_bytes = (FIXTURES / 'sample.aiff').read_bytes()

        scenarios = [
            ('MP3', [
                {'title': 'Real MP3', 'location': 'REAL.mp3', 'audio_format': 301, 'bytes': mp3_bytes},
                {'title': 'Wrong Ext M4A', 'location': 'WRONG.m4a', 'audio_format': 301, 'bytes': aac_bytes},
                {'title': 'Disguised AAC in MP3', 'location': 'FAKE.mp3', 'audio_format': 301, 'bytes': aac_bytes},
            ], {'Artista original - Real MP3.mp3'}, 2),
            ('M4A', [
                {'title': 'Real AAC', 'location': 'AAC.m4a', 'audio_format': 502, 'bytes': aac_bytes},
                {'title': 'Real ALAC', 'location': 'ALAC.m4a', 'audio_format': 601, 'bytes': alac_bytes},
                {'title': 'Wrong Ext MP3', 'location': 'WRONG.mp3', 'audio_format': 502, 'bytes': mp3_bytes},
                {'title': 'Disguised MP3 in M4A', 'location': 'FAKE.m4a', 'audio_format': 502, 'bytes': mp3_bytes},
            ], {'Artista original - Real AAC.m4a', 'Artista original - Real ALAC.m4a'}, 2),
            ('AAC', [
                {'title': 'Real AAC', 'location': 'AAC.m4a', 'audio_format': 502, 'bytes': aac_bytes},
                {'title': 'ALAC Inside M4A', 'location': 'ALAC.m4a', 'audio_format': 502, 'bytes': alac_bytes},
                {'title': 'Wrong MP3', 'location': 'MP3.mp3', 'audio_format': 301, 'bytes': mp3_bytes},
            ], {'Artista original - Real AAC.m4a'}, 2),
            ('ALAC', [
                {'title': 'Real ALAC', 'location': 'ALAC.m4a', 'audio_format': 601, 'bytes': alac_bytes},
                {'title': 'AAC Inside M4A', 'location': 'AAC.m4a', 'audio_format': 601, 'bytes': aac_bytes},
                {'title': 'Wrong MP3', 'location': 'MP3.mp3', 'audio_format': 301, 'bytes': mp3_bytes},
            ], {'Artista original - Real ALAC.m4a'}, 2),
            ('WAV', [
                {'title': 'Real WAV', 'location': 'REAL.wav', 'audio_format': 701, 'bytes': wav_bytes},
                {'title': 'Disguised AIFF in WAV', 'location': 'FAKE.wav', 'audio_format': 701, 'bytes': aiff_bytes},
                {'title': 'Wrong M4A', 'location': 'WRONG.m4a', 'audio_format': 502, 'bytes': aac_bytes},
            ], {'Artista original - Real WAV.wav'}, 2),
            ('AIFF', [
                {'title': 'Real AIFF', 'location': 'REAL.aif', 'audio_format': 701, 'bytes': aiff_bytes},
                {'title': 'Disguised WAV in AIF', 'location': 'FAKE.aif', 'audio_format': 701, 'bytes': wav_bytes},
                {'title': 'Wrong M4A', 'location': 'WRONG.m4a', 'audio_format': 502, 'bytes': aac_bytes},
            ], {'Artista original - Real AIFF.aif'}, 2),
        ]

        for seekable in (True, False):
            for fmt, entries, expected_names, expected_skipped in scenarios:
                with self.subTest(format=fmt, seekable=seekable), tempfile.TemporaryDirectory() as root:
                    phone = build_phone(entries, seekable=seekable)
                    db_path = Path(root) / 'catalogue.db'
                    db_path.write_bytes(phone.files[PREF + 'MediaLibrary.sqlitedb'])
                    tracks = [dict(t, expected_format=fmt) for t in read_catalogue(db_path)]
                    out = Path(root) / 'out'
                    out.mkdir()
                    result = run_export(phone, tracks, out)
                    self.assertEqual(result['exported'], len(expected_names))
                    self.assertEqual(result.get('skipped_format', 0), expected_skipped)
                    written = {p.name for p in out.iterdir()}
                    self.assertEqual(written, expected_names)
                    for exported_file in out.iterdir():
                        self.assertTrue(suffix_matches_format(exported_file.name, fmt))
                        detected = detect_file_format_label(exported_file)
                        self.assertTrue(matches_format({'format_label': detected, 'format_source': 'header'}, fmt))
                    self.assertFalse(phone.writes)
                    self.assertFalse(phone.sent)


class FormatExportUITests(unittest.TestCase):
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

    def test_filtered_export_never_includes_hidden_checked_tracks_from_other_formats(self):
        w = self.window
        rows = [
            {'id': 'mp3', 'title': 'Song MP3', 'artist': 'A', 'album': 'B', 'duration': 60, 'is_local': True, 'usb_exists': True, 'afc_path': 'iTunes_Control/Music/F00/1.mp3', 'format_label': 'MP3'},
            {'id': 'aac', 'title': 'Song AAC', 'artist': 'A', 'album': 'B', 'duration': 60, 'is_local': True, 'usb_exists': True, 'afc_path': 'iTunes_Control/Music/F00/2.m4a', 'format_label': 'M4A · AAC'},
            {'id': 'alac', 'title': 'Song ALAC', 'artist': 'A', 'album': 'B', 'duration': 60, 'is_local': True, 'usb_exists': True, 'afc_path': 'iTunes_Control/Music/F00/3.m4a', 'format_label': 'M4A · ALAC'},
            {'id': 'wav', 'title': 'Song WAV', 'artist': 'A', 'album': 'B', 'duration': 60, 'is_local': True, 'usb_exists': True, 'afc_path': 'iTunes_Control/Music/F00/4.wav', 'format_label': 'WAV'},
            {'id': 'aiff', 'title': 'Song AIFF', 'artist': 'A', 'album': 'B', 'duration': 60, 'is_local': True, 'usb_exists': True, 'afc_path': 'iTunes_Control/Music/F00/5.aif', 'format_label': 'AIFF'},
            {'id': 'mislabeled', 'title': 'Mislabeled M4A', 'artist': 'A', 'album': 'B', 'duration': 60, 'is_local': True, 'usb_exists': True, 'afc_path': 'iTunes_Control/Music/F00/6.m4a', 'format_label': 'MP3', 'format_source': 'catalogue'},
        ]
        w.show_library(rows)
        # Check every single track while unfiltered (simulating leftover checks before changing format filter).
        w.library_model.check_visible(True)
        self.assertEqual(len(w.library_model.checked), 6)

        expected_by_filter = {
            'MP3': {'mp3'},
            'M4A': {'aac', 'alac', 'mislabeled'},
            'AAC': {'aac'},
            'ALAC': {'alac'},
            'WAV': {'wav'},
            'AIFF': {'aiff'},
        }
        with tempfile.TemporaryDirectory() as folder:
            for fmt, expected_ids in expected_by_filter.items():
                with self.subTest(format=fmt):
                    w.format_filter.setCurrentIndex(w.format_filter.findText(fmt))
                    APP.processEvents()
                    self.assertTrue(w.export_phone.isEnabled())
                    with patch.object(QFileDialog, 'getExistingDirectory', return_value=folder), patch.object(w, 'start_transfer') as start:
                        w.export_songs()
                        start.assert_called_once()
                        mode, items, _ = start.call_args.args
                        self.assertEqual(mode, 'export')
                        self.assertEqual({t['id'] for t in items}, expected_ids)
                        self.assertTrue(all(t.get('expected_format') == fmt for t in items))

        # If only an M4A is checked and user switches to MP3, Export must stay disabled.
        w.library_model.checked = {'aac'}
        w.format_filter.setCurrentIndex(w.format_filter.findText('MP3'))
        w.checks_changed()
        self.assertFalse(w.export_phone.isEnabled())
        self.assertEqual(w.selection_count.text(), '0 seleccionadas (MP3)')

    def test_select_all_checkbox_label_is_clear_in_spanish_and_english(self):
        w = self.window
        w.resize(1080, 720)
        rows = [
            {'id': '1', 'title': 'Alpha', 'artist': 'Artist', 'album': 'Album', 'duration': 40, 'is_local': True, 'usb_exists': True, 'afc_path': 'iTunes_Control/Music/F00/1.mp3', 'format_label': 'MP3', 'has_artwork': True},
            {'id': '2', 'title': 'Beta', 'artist': 'Artist', 'album': 'Album', 'duration': 50, 'is_local': True, 'usb_exists': True, 'afc_path': 'iTunes_Control/Music/F00/2.m4a', 'format_label': 'M4A · AAC'},
        ]
        w.show_library(rows)
        self.assertEqual(w.select_visible.text(), 'Seleccionar todo')
        self.assertNotIn('visibles', w.select_visible.text().casefold())

        w.format_filter.setCurrentIndex(w.format_filter.findText('MP3'))
        self.assertEqual(w.select_visible.text(), 'Seleccionar todos los MP3')

        w.search.setText('Alpha')
        self.assertEqual(w.select_visible.text(), 'Seleccionar resultados')

        w.clear_filters()
        w.content_filter.setCurrentIndex(1)
        self.assertEqual(w.select_visible.text(), 'Seleccionar resultados')

        w.language_choice.setCurrentIndex(1)
        APP.processEvents()
        self.assertEqual(w.select_visible.text(), 'Select all results')
        w.clear_filters()
        self.assertEqual(w.select_visible.text(), 'Select all')
        w.format_filter.setCurrentIndex(w.format_filter.findText('MP3'))
        self.assertEqual(w.select_visible.text(), 'Select all MP3')
        self.assertGreaterEqual(w.select_visible.sizeHint().width(), QFontMetrics(w.select_visible.font()).horizontalAdvance(w.select_visible.text()) + 20)

    def test_transfer_result_and_finish_report_skips_and_refilter_corrected_tracks(self):
        w = self.window
        rows = [
            {'id': 'real', 'title': 'Real', 'artist': 'A', 'album': 'B', 'duration': 60, 'is_local': True, 'usb_exists': True, 'afc_path': 'iTunes_Control/Music/F00/1.mp3', 'format_label': 'MP3', 'format_source': 'catalogue'},
            {'id': 'fake', 'title': 'Fake', 'artist': 'A', 'album': 'B', 'duration': 60, 'is_local': True, 'usb_exists': True, 'afc_path': 'iTunes_Control/Music/F00/2.mp3', 'format_label': 'MP3', 'format_source': 'catalogue'},
        ]
        w.show_library(rows)
        w.format_filter.setCurrentIndex(w.format_filter.findText('MP3'))
        self.assertEqual({t['id'] for t in w.library_model.tracks}, {'real', 'fake'})
        outcome = {'exported': 1, 'skipped_format': 1, 'format_updates': {'fake': {'format_label': 'M4A · AAC', 'format_source': 'header'}}}
        w.transfer_result(outcome)
        self.assertEqual(w.status.text(), '1 archivos exportados y comprobados. 1 omitidos por formato distinto.')
        w.language_choice.setCurrentIndex(1)
        self.assertEqual(w.status.text(), '1 file exported and verified. 1 skipped due to different format.')
        from unittest.mock import Mock
        w.transfer_worker = Mock(mode='export', selected=rows)
        w.transfer_finished()
        self.assertEqual([t['id'] for t in w.library_model.tracks], ['real'])
        w.format_filter.setCurrentIndex(w.format_filter.findText('AAC'))
        self.assertEqual([t['id'] for t in w.library_model.tracks], ['fake'])
