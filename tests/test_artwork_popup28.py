"""Real iOS artwork typing, stale display covers and native popup clipping."""
import hashlib,json,tempfile,unittest
from contextlib import closing
from pathlib import Path
import sqlite3
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QFrame,QLabel
from PySide6.QtTest import QTest
from importios.native import Window
from importios.sync.catalogue import snapshot
from importios.sync.protocol import ProtocolError
from importios.transfers import run_transfer,TransferError
from test_native_connection import APP
from test_recovery import PendingPhone
from test_transfers import FIXTURES,PREF


class StaleCoverPhone(PendingPhone):
    old_relative='ab/'+'f'*38
    def __init__(self):
        super().__init__()
        self.modify('''CREATE TABLE best_artwork_token(entity_pid,entity_type,available_artwork_token,artwork_source_type,artwork_variant_type);
            INSERT INTO artwork VALUES('999',300,6,0,'ab/ffffffffffffffffffffffffffffffffffffff');''')
        self.files[PREF+'Artwork/Originals/'+self.old_relative]=b'old different cover'

    def register_art(self,op,pid):
        super().register_art(op,pid)
        # Music may retain its previous display preference after an upload.
        self.modify(f"INSERT INTO best_artwork_token VALUES({int(pid)},0,'999',300,0)")


class ArtworkPopupTests(unittest.TestCase):
    def selected(self):
        path=FIXTURES/'covered-aac.m4a'
        return {'path':str(path),'id':hashlib.sha256(path.read_bytes()).hexdigest()}

    def call(self,p,mode,selected,root):
        with patch('importios.transfers.device',p.device),patch('importios.transfers.Atc',lambda peer:peer):
            return run_transfer(mode,selected,root,lambda *a:None)

    def test_real_track_type_one_original_type_six_is_verified(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            result=self.call(phone,'import',[self.selected()],root)
            self.assertEqual(result['imported'],1)
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(phone.files[PREF+'MediaLibrary.sqlitedb'])
                self.assertEqual(db.execute('SELECT artwork_type FROM artwork_token WHERE entity_type=0').fetchone()[0],1)
                # This was the invalid join in preview.27: it returns no row.
                self.assertEqual(db.execute('SELECT COUNT(*) FROM artwork a JOIN artwork_token t ON a.artwork_token=t.artwork_token AND a.artwork_source_type=t.artwork_source_type AND a.artwork_variant_type=t.artwork_variant_type AND a.artwork_type=t.artwork_type WHERE t.entity_type=0').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT artwork_type FROM artwork').fetchone()[0],6)

    def test_display_cover_preference_cannot_override_upload_verification(self):
        phone=StaleCoverPhone()
        with tempfile.TemporaryDirectory() as root:
            result=self.call(phone,'import',[self.selected()],root)
            receipt=json.loads((Path(result['backup'])/'journal.json').read_text())
            entry=receipt['entries'][0]
            path=Path(root)/'current.db';path.write_bytes(phone.files[PREF+'MediaLibrary.sqlitedb'])
            current=snapshot(path);track=current['tracks'][current['wire_to_item'][str(entry['track_id'])]]
            self.assertTrue(track['artwork_paths'][0].endswith(phone.old_relative))
            self.assertFalse(any(p.endswith(phone.old_relative) for p in current['artwork_originals'][entry['artwork']['cache_id']]))
            self.assertFalse(any(p.endswith(phone.old_relative) for p,mode in phone.opens))
            self.assertEqual(result['imported'],1)

    def test_previous_artwork_verification_failure_is_reconciled_without_resending(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            with patch('importios.sync.artwork.verify',side_effect=ProtocolError('verify-artwork-original')):
                with self.assertRaises(TransferError):self.call(phone,'import',[self.selected()],root)
            journal=next(Path(root).glob('*/journal.json'))
            self.assertEqual(json.loads(journal.read_text())['phase'],'verifying')
            phone.writes.clear();phone.sent.clear()
            result=self.call(phone,'import',[self.selected()],root)
            self.assertEqual((result['imported'],result['already_imported'],result['metadata_unverified']),(0,1,0))
            self.assertEqual(json.loads(journal.read_text())['phase'],'observed-present')
            self.assertFalse(phone.writes);self.assertFalse(phone.sent)

    def test_corrupt_artwork_still_stops_and_reports_only_counts(self):
        phone=PendingPhone();register=phone.register_art
        def corrupt(op,pid):
            register(op,pid)
            for path in list(phone.files):
                if '/Artwork/Originals/' in path:phone.files[path]=b'wrong bytes'
        phone.register_art=corrupt
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(TransferError) as caught:self.call(phone,'import',[self.selected()],root)
            diagnostic=caught.exception.diagnostic
            self.assertIn('verify-artwork-original',diagnostic)
            self.assertIn('\"audio_verified\": true',diagnostic)
            self.assertIn('audio y los metadatos están verificados',str(caught.exception))
            self.assertIn('"different_candidates": 1',diagnostic)
            self.assertNotIn('covered-aac',diagnostic);self.assertNotIn('/Artwork/',diagnostic)
            self.assertNotEqual(json.loads(next(Path(root).glob('*/journal.json')).read_text())['phase'],'completed')

    def test_ambiguous_cache_id_cannot_pass_by_finding_one_matching_picture(self):
        phone=PendingPhone();register=phone.register_art
        def duplicate(op,pid):
            register(op,pid)
            if any('/Artwork/Originals/' in path for path in phone.files):
                cache=op['item']['artwork_cache_id']
                phone.modify(f"INSERT INTO artwork VALUES('{int(cache)}',300,6,0,'00/00000000000000000000000000000000000000')")
        phone.register_art=duplicate
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(TransferError) as caught:self.call(phone,'import',[self.selected()],root)
            self.assertIn('verify-artwork-original',caught.exception.diagnostic)
            self.assertIn('"path_candidates": 2',caught.exception.diagnostic)
            self.assertIn('"readable_candidates": 0',caught.exception.diagnostic)

    def test_diagnostics_are_read_only_optional_and_not_called_by_import(self):
        phone=PendingPhone();before=dict(phone.files)
        with tempfile.TemporaryDirectory() as root:
            result=self.call(phone,'diagnose',[],root)
            self.assertEqual(result['diagnosed'],1);self.assertEqual(phone.files,before)
            self.assertFalse(phone.writes);self.assertFalse(phone.sent)
            self.assertFalse(list(Path(root).glob('*/journal.json')))
            with patch('importios.diagnostics.check',side_effect=AssertionError('not part of import')):
                self.assertEqual(self.call(phone,'import',[self.selected()],root)['imported'],1)

    def test_popup_has_no_native_frame_and_clips_all_corners_in_both_themes(self):
        w=Window(auto_connect=False);w.show();APP.processEvents()
        try:
            self.assertFalse(hasattr(w,'font_status'))
            self.assertFalse(any('fuente del sistema' in v.text() for v in w.findChildren(QLabel)))
            for theme in (1,2):
                w.theme_choice.setCurrentIndex(theme);APP.processEvents()
                box=w.format_filter;box.showPopup();APP.processEvents();popup=box.view().window()
                self.assertTrue(popup.windowFlags() & Qt.WindowType.FramelessWindowHint)
                self.assertTrue(popup.windowFlags() & Qt.WindowType.NoDropShadowWindowHint)
                self.assertEqual(popup.frameShape(),QFrame.Shape.NoFrame)
                mask=popup.mask();self.assertFalse(mask.isEmpty())
                for p in (popup.rect().topLeft(),popup.rect().topRight(),popup.rect().bottomLeft(),popup.rect().bottomRight()):self.assertFalse(mask.contains(p))
                self.assertTrue(mask.contains(popup.rect().center()))
                original=box.currentIndex();QTest.keyClick(box.view(),Qt.Key.Key_Escape);APP.processEvents()
                self.assertFalse(popup.isVisible());self.assertEqual(box.currentIndex(),original)
        finally:w.close();APP.processEvents()
