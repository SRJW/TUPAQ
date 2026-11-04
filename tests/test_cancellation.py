"""Cancellation preserves completed exports and never interrupts native metadata."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_transfers as support
from importios.cancellation import TransferControl
from importios.transfers import run_transfer

class CancellationTests(unittest.TestCase):
    selected=support.TransferTests.selected
    tracks=support.TransferTests.tracks
    def run_work(self,p,mode,selected,path,control,callback=lambda *a:None):
        def progress(*args):callback(*args)
        progress.control=control
        with patch('importios.transfers.device',p.device),patch('importios.transfers.Atc',lambda peer:peer):
            return run_transfer(mode,selected,path,progress)

    def test_cancel_during_preparation_writes_no_library_changes_and_next_import_works(self):
        with tempfile.TemporaryDirectory() as root:
            p=support.Phone();original=p.files[support.PREF+'MediaLibrary.sqlitedb'];c=TransferControl()
            result=self.run_work(p,'import',[self.selected()],root,c,lambda *args:c.request())
            self.assertTrue(result['cancelled']);self.assertFalse(p.sent);self.assertFalse(p.writes)
            self.assertEqual(p.files[support.PREF+'MediaLibrary.sqlitedb'],original)
            receipt=json.loads(next(Path(root).glob('*/journal.json')).read_text());self.assertEqual(receipt['phase'],'before-write-failed')
            self.assertEqual(self.run_work(p,'import',[self.selected()],root,TransferControl())['imported'],1)

    def test_cancel_after_commit_finishes_and_verifies_the_entire_native_batch(self):
        with tempfile.TemporaryDirectory() as root:
            p=support.Phone();c=TransferControl()
            def report(*args):
                if args[2].startswith('Importando:'):c.request()
            result=self.run_work(p,'import',[self.selected(),self.selected('aac.m4a')],root,c,report)
            self.assertEqual(result['imported'],2);self.assertTrue(result['cancel_deferred']);self.assertNotIn('cancelled',result)
            self.assertEqual(json.loads(next(Path(root).glob('*/journal.json')).read_text())['phase'],'completed')

    def test_cancel_export_preserves_finished_files_and_removes_current_temporary_file(self):
        with tempfile.TemporaryDirectory() as root:
            p=support.Phone()
            support.TransferTests.call(self,p,'import',[self.selected('aac.m4a')],root)
            tracks=self.tracks(p,root);c=TransferControl()
            def report(*args):
                if args[2].startswith('Exportada:'):c.request()
            out=Path(root)/'out';out.mkdir();p.writes.clear();p.sent.clear()
            result=self.run_work(p,'export',tracks,out,c,report)
            self.assertTrue(result['cancelled']);self.assertEqual(result['exported'],1)
            self.assertTrue(Path(result['files'][0]).is_file());self.assertEqual(len(list(out.iterdir())),1)
            self.assertFalse(p.writes);self.assertFalse(p.sent)

    def test_waiting_for_native_reply_is_cancellable_without_stopping_a_socket_read(self):
        import asyncio
        from importios.sync.protocol import Atc
        from importios.cancellation import CURRENT,TransferCancelled
        async def test():
            control=TransferControl();token=CURRENT.set(control);channel=Atc(None)
            try:
                task=asyncio.create_task(channel.receive());await asyncio.sleep(.02);control.request()
                with self.assertRaises(TransferCancelled):await asyncio.wait_for(task,1)
            finally:CURRENT.reset(token)
        asyncio.run(test())
