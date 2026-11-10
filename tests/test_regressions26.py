"""Regressions from preview.25: actual SDK interface, artwork and popup UI."""
import asyncio
from contextlib import asynccontextmanager,closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import create_autospec,patch
from pymobiledevice3.services.afc import AfcService
from mutagen.id3 import ID3,APIC
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListView
from PySide6.QtTest import QTest
from importios.remote_artwork import cover_for_track,original_path,catalogue_artwork
from importios.transfers import run_transfer,TransferError
from test_recovery import PendingPhone
from test_transfers import FIXTURES,PREF
from test_remote_artwork import AFC,AUDIO,RELATIVE
from test_selected_assets import cover
from test_native_connection import APP
from importios.native import Window


class Regressions26(unittest.TestCase):
    def call(self,phone,selected,root,fail=False):
        # Only APIs exposed by the installed, pinned SDK exist on this proxy.
        proxy=create_autospec(AfcService,instance=True,spec_set=True)
        for name in ('stat','listdir','fopen','fclose','lock','makedirs','fread','fwrite','rename','rm'):
            if hasattr(phone,name) and hasattr(proxy,name):getattr(proxy,name).side_effect=getattr(phone,name)
        if fail:proxy.makedirs.side_effect=AttributeError('simulated legacy SDK call')
        @asynccontextmanager
        async def device():
            yield phone,proxy
        with patch('importios.transfers.device',device),patch('importios.transfers.Atc',lambda peer:peer):
            return run_transfer('import',selected,root,lambda *a:None)

    def selected(self,name='covered-aac.m4a'):
        p=FIXTURES/name
        return {'path':str(p),'id':hashlib.sha256(p.read_bytes()).hexdigest()}

    def test_missing_artwork_folder_uses_real_sdk_api(self):
        phone=PendingPhone()
        self.assertFalse(hasattr(AfcService,'mkdir'))
        with tempfile.TemporaryDirectory() as root:
            result=self.call(phone,[self.selected()],root)
            self.assertEqual(result['imported'],1)
            self.assertIn('/Airlock/Media/Artwork',phone.dirs)
            self.assertFalse(phone.handles)

    def test_matching_retry_completes_legacy_pending_without_erasing_backup(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(TransferError):self.call(phone,[self.selected()],root,fail=True)
            journal=next(Path(root).glob('*/journal.json'))
            before=json.loads(journal.read_text())
            self.assertEqual((before['phase'],before['last_error_code']),('metadata-announced','AttributeError'))
            result=self.call(phone,[self.selected()],root)
            self.assertEqual(result['already_imported'],1)
            self.assertEqual(json.loads(journal.read_text())['phase'],'completed')
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(phone.files[PREF+'MediaLibrary.sqlitedb'])
                self.assertEqual(db.execute('SELECT count(*) FROM item').fetchone()[0],2)
            self.assertTrue((journal.parent/'before').is_dir())
            self.assertFalse(phone.handles)

    def test_retry_refuses_a_changed_catalogue_anchor(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(TransferError):self.call(phone,[self.selected()],root,fail=True)
            journal=next(Path(root).glob('*/journal.json'))
            phone.modify("UPDATE _MLDatabaseProperties SET value='99'")
            phone.sent.clear();phone.writes.clear()
            with self.assertRaises(TransferError) as caught:self.call(phone,[self.selected()],root)
            self.assertIn('recovery-anchor',caught.exception.diagnostic)
            self.assertEqual(json.loads(journal.read_text())['phase'],'metadata-announced')
            self.assertFalse(phone.sent);self.assertFalse(phone.writes)

    def test_repeated_covered_imports_recreate_ios_artwork_folder(self):
        from mutagen.mp4 import MP4
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root,tempfile.TemporaryDirectory() as local:
            for n in range(3):
                p=Path(local)/f'song-{n}.m4a';p.write_bytes((FIXTURES/'covered-aac.m4a').read_bytes())
                audio=MP4(p);audio['\xa9nam']=[f'Prueba {n}'];audio.save()
                phone.dirs.discard('/Airlock/Media/Artwork')
                result=self.call(phone,[{'path':str(p),'id':hashlib.sha256(p.read_bytes()).hexdigest()}],root)
                self.assertEqual(result['imported'],1)
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(phone.files[PREF+'MediaLibrary.sqlitedb'])
                self.assertEqual(db.execute('SELECT count(*) FROM item').fetchone()[0],4)
                self.assertEqual(db.execute('SELECT title FROM item_extra WHERE item_pid=1').fetchone()[0],'Original')
            self.assertEqual(len(list(Path(root).glob('*/journal.json'))),3)

    def test_unrelated_retry_never_completes_or_discards_pending(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(TransferError):self.call(phone,[self.selected()],root,fail=True)
            journal=next(Path(root).glob('*/journal.json'));phone.sent.clear();phone.writes.clear()
            with self.assertRaises(TransferError) as caught:self.call(phone,[self.selected('sample.mp3')],root)
            self.assertIn('previous-import-unverified',caught.exception.diagnostic)
            self.assertEqual(json.loads(journal.read_text())['phase'],'metadata-announced')
            self.assertFalse(phone.sent);self.assertFalse(phone.writes)

    def test_smaller_embedded_picture_beats_larger_cached_picture_for_both_views(self):
        embedded=cover(64,48);cached=cover(1200,1200)
        tags=ID3();tags.add(APIC(encoding=3,mime='image/png',type=3,data=embedded))
        stream=io.BytesIO();tags.save(stream)
        track={'afc_path':AUDIO,'artwork_paths':[original_path(RELATIVE)]}
        for assets in (False,True):
            afc=AFC({AUDIO:stream.getvalue(),original_path(RELATIVE):cached})
            result=asyncio.run(cover_for_track(afc,track,assets=assets))
            if assets:self.assertEqual(result['cover'],embedded)
            else:
                from PySide6.QtGui import QImage
                self.assertEqual((QImage.fromData(result).width(),QImage.fromData(result).height()),(96,72))
            self.assertEqual(afc.opens,[(AUDIO,'r')])

    def test_readable_file_without_picture_does_not_inherit_catalogue_cover(self):
        track={'afc_path':AUDIO,'artwork_paths':[original_path(RELATIVE)]}
        for assets in (False,True):
            afc=AFC({AUDIO:(FIXTURES/'sample.mp3').read_bytes(),original_path(RELATIVE):cover()})
            result=asyncio.run(cover_for_track(afc,track,assets=assets))
            self.assertFalse(result.get('cover') if assets else result)
            self.assertEqual(afc.opens,[(AUDIO,'r')])

    def test_ambiguous_or_cross_namespace_tokens_never_choose_another_picture(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.executescript('''CREATE TABLE artwork_token(entity_pid,entity_type,artwork_token,artwork_source_type,artwork_type,artwork_variant_type);
                CREATE TABLE artwork(artwork_token,artwork_source_type,artwork_type,artwork_variant_type,relative_path);
                INSERT INTO artwork_token VALUES(1,0,'same',1,1,1);''')
            db.executemany('INSERT INTO artwork VALUES(?,?,?,?,?)',[
                ('same',500,6,1,'aa/'+'a'*38),('same',1,6,1,RELATIVE)])
            self.assertEqual(catalogue_artwork(db)[('1',0)],original_path(RELATIVE))
            db.execute('INSERT INTO artwork VALUES(?,?,?,?,?)',('same',1,6,1,'cc/'+'b'*38))
            self.assertNotIn(('1',0),catalogue_artwork(db))

    def test_modern_popup_preserves_keyboard_selection_in_both_themes(self):
        window=Window(auto_connect=False);window.show()
        try:
            self.assertEqual(APP.style().objectName().lower(),'fusion')
            for theme in (1,2):
                window.theme_choice.setCurrentIndex(theme);APP.processEvents()
                combo=window.format_filter
                self.assertNotIn('M4P',[combo.itemText(i) for i in range(combo.count())])
                self.assertIsInstance(combo.view(),QListView)
                combo.setCurrentIndex(0);combo.setFocus();combo.showPopup();APP.processEvents()
                self.assertTrue(combo.view().isVisible())
                QTest.keyClick(combo.view(),Qt.Key.Key_Down)
                QTest.keyClick(combo.view(),Qt.Key.Key_Return);APP.processEvents()
                self.assertEqual(combo.currentIndex(),1)
        finally:window.close();APP.processEvents()
