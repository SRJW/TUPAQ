"""Pending audio proof permits progress without suppressing actual uncertainty."""
import json
from pathlib import Path
import tempfile
import unittest
from importios.transfers import TransferError
import test_transfers as support
Phone=support.Phone

class ReconciliationTests(unittest.TestCase):
    selected=support.TransferTests.selected
    call=support.TransferTests.call

    def pending(self,phone,root):
        phone.fail='lost-finished'
        with self.assertRaises(TransferError):self.call(phone,'import',[self.selected()],root)
        phone.fail=None
        journal=next(Path(root).glob('*/journal.json'))
        return journal,json.loads(journal.read_text())

    def test_missing_or_corrupt_audio_still_blocks_without_resending(self):
        for corrupt in (False,True):
            with self.subTest(corrupt=corrupt),tempfile.TemporaryDirectory() as root:
                phone=Phone();journal,record=self.pending(phone,root)
                path='/'+record['entries'][0]['destination'].lstrip('/')
                if corrupt:phone.files[path]=b'corruption'
                else:del phone.files[path]
                sent=len(phone.sent);writes=len(phone.writes)
                with self.assertRaises(TransferError) as caught:self.call(phone,'import',[self.selected('aac.m4a')],root)
                self.assertIn('previous-import-unverified',caught.exception.diagnostic)
                self.assertEqual(len(phone.sent),sent);self.assertEqual(len(phone.writes),writes)
                self.assertNotEqual(json.loads(journal.read_text())['phase'],'observed-present')

    def test_same_source_after_reconciliation_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as root:
            phone=Phone();journal,_=self.pending(phone,root);sent=len(phone.sent)
            result=self.call(phone,'import',[self.selected()],root)
            self.assertEqual(result['already_imported'],1);self.assertEqual(result['imported'],0)
            self.assertEqual(result['reconciled'],1);self.assertEqual(len(phone.sent),sent)
            self.assertEqual(json.loads(journal.read_text())['phase'],'observed-present')

    def test_verify_only_reads_remote_files(self):
        with tempfile.TemporaryDirectory() as root:
            phone=Phone();self.pending(phone,root);sent=len(phone.sent);writes=len(phone.writes)
            result=self.call(phone,'verify',[],root)
            self.assertEqual(result['verified'],1);self.assertFalse(result['unresolved'])
            self.assertEqual(len(phone.sent),sent);self.assertEqual(len(phone.writes),writes)

    def test_unannounced_empty_staging_is_retired_only_with_unchanged_catalogue(self):
        from unittest.mock import patch
        from importios.transfers import save_receipt
        with tempfile.TemporaryDirectory() as root:
            phone=Phone()
            def stopped(*args,**kwargs):
                receipt,directory=args[6],args[7]
                receipt['phase']='staging';save_receipt(directory,receipt)
                raise ConnectionResetError('before announcement')
            with patch('importios.transfers.transact',side_effect=stopped):
                with self.assertRaises(TransferError):self.call(phone,'import',[self.selected()],root)
            result=self.call(phone,'import',[self.selected('aac.m4a')],root)
            self.assertEqual(result['imported'],1);self.assertEqual(result['reconciled'],1)

    def test_five_consecutive_imports_do_not_require_deleting_history(self):
        with tempfile.TemporaryDirectory() as root:
            phone=Phone()
            for name in ('sample.mp3','sample.wav','sample.aiff','sample.m4a','covered-aac.m4a'):
                self.assertEqual(self.call(phone,'import',[self.selected(name)],root)['imported'],1)
            self.assertEqual(len(list(Path(root).glob('*/journal.json'))),5)

    def test_changed_catalogue_does_not_retire_uncertain_staging(self):
        from unittest.mock import patch
        from importios.transfers import save_receipt
        import sqlite3
        from contextlib import closing
        import test_transfers as support
        with tempfile.TemporaryDirectory() as root:
            phone=Phone()
            def stopped(*args,**kwargs):
                receipt,directory=args[6],args[7];receipt['phase']='staging';save_receipt(directory,receipt)
                raise ConnectionResetError('before announcement')
            with patch('importios.transfers.transact',side_effect=stopped):
                with self.assertRaises(TransferError):self.call(phone,'import',[self.selected()],root)
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(phone.files[support.PREF+'MediaLibrary.sqlitedb']);db.execute("UPDATE item_extra SET title='Changed original'");db.commit()
                phone.files[support.PREF+'MediaLibrary.sqlitedb']=db.serialize()
            with self.assertRaises(TransferError) as caught:self.call(phone,'import',[self.selected('aac.m4a')],root)
            self.assertIn('previous-import-unverified',caught.exception.diagnostic)
