"""Large selections keep small native sessions and stop on uncertain work."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from importios.bulk import plan,execute,BINDING,validate_binding
from importios.cancellation import CURRENT,TransferControl,begin_commit
from importios.sync.protocol import ProtocolError
from importios.transfers import run_transfer


class BulkTests(unittest.TestCase):
    def work(self,mode,selected,root,leaf,control=None,progress=lambda *a:None):
        def report(*args):progress(*args)
        report.control=control or TransferControl()
        with patch('importios.transfers.import_selected',side_effect=leaf),patch('importios.deletion.delete_selected',side_effect=leaf):
            return run_transfer(mode,selected,root,report)

    def test_ten_thousand_imports_partition_without_loss_or_protocol_oversize(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'audio.mp3';path.write_bytes(b'fixture');tracks=[{'id':str(n),'path':str(path)} for n in range(10000)];seen=[];values=[]
            async def leaf(chunk,*args):
                self.assertLessEqual(len(chunk),49);begin_commit();seen.extend(t['id'] for t in chunk)
                return {'imported':len(chunk),'already_imported':0,'source_ids':[t['id'] for t in chunk]}
            result=self.work('import',tracks,root,leaf,progress=lambda v,t,*a:values.append((v,t)))
            self.assertEqual(result['imported'],10000);self.assertNotIn('deleted',result);self.assertEqual(seen,[t['id'] for t in tracks])
            self.assertEqual(result['batches_completed'],205);self.assertEqual(values[-1],(1000000,1000000))
            self.assertEqual([v for v,_ in values],sorted(v for v,_ in values))
            record=json.loads(Path(result['bulk_journal']).read_text(encoding='utf-8'));self.assertEqual(record['phase'],'completed')

    def test_cancel_during_committed_delete_finishes_current_batch_only(self):
        with tempfile.TemporaryDirectory() as root:
            tracks=[{'id':str(n)} for n in range(10000)];seen=[];control=TransferControl()
            async def leaf(chunk,*args):
                begin_commit();seen.extend(t['id'] for t in chunk)
                if len(seen)==700:self.assertFalse(control.request())
                return {'deleted':len(chunk),'item_ids':[t['id'] for t in chunk]}
            result=self.work('delete',tracks,root,leaf,control)
            self.assertTrue(result['cancelled']);self.assertEqual(result['deleted'],700);self.assertEqual(len(seen),700)
            self.assertFalse(control.committed);self.assertEqual(result['batches_completed'],7)

    def test_failure_keeps_only_verified_counts_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as root:
            calls=[]
            async def leaf(chunk,*args):
                calls.append(chunk)
                if len(calls)==3:raise ConnectionResetError('test')
                return {'deleted':len(chunk),'item_ids':[t['id'] for t in chunk]}
            result=self.work('delete',[{'id':str(n)} for n in range(5000)],root,leaf)
            self.assertTrue(result['bulk_stopped']);self.assertEqual(result['processed'],200);self.assertEqual(result['deleted'],200);self.assertEqual(len(calls),3)
            self.assertEqual(json.loads(Path(result['bulk_journal']).read_text())['phase'],'stopped')

    def test_preflight_rejects_duplicates_and_byte_budgets_are_respected(self):
        with self.assertRaises(ProtocolError):plan('delete',[{'id':'a'}]*101)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'sparse.wav'
            with path.open('wb') as stream:stream.truncate(256*1024**2)
            chunks=plan('import',[{'id':str(n),'path':str(path)} for n in range(20)])
            self.assertEqual([len(c) for c in chunks],[8,8,4])

    def test_low_space_stops_before_native_changes(self):
        with tempfile.TemporaryDirectory() as root,patch('importios.bulk.shutil.disk_usage',return_value=SimpleNamespace(free=0)):
            async def leaf(*args):self.fail('No native session may start')
            result=self.work('delete',[{'id':str(n)} for n in range(101)],root,leaf)
            self.assertTrue(result['bulk_stopped']);self.assertEqual(result['processed'],0)

    def test_phone_or_catalogue_change_is_rejected_before_next_commit(self):
        token=BINDING.set({})
        try:
            first=SimpleNamespace(_tupaq_device_token='a'*64);other=SimpleNamespace(_tupaq_device_token='b'*64)
            validate_binding(first,{'database':1,'primary':2})
            with self.assertRaises(ProtocolError):validate_binding(other,{'database':1,'primary':2})
            with self.assertRaises(ProtocolError):validate_binding(first,{'database':9,'primary':2})
        finally:BINDING.reset(token)

    def test_planned_destinations_are_reserved_before_the_first_upload(self):
        import test_transfers as support
        from importios.transfers import available_path
        phone=support.Phone();occupied=set();source={'extension':'.mp3'}
        async def work():
            before={'tracks':{}}
            with patch('importios.transfers.secrets.choice',side_effect=list('BBBBBBBBCCCC')):
                first=await available_path(phone,before,source,occupied)
                second=await available_path(phone,before,source,occupied)
            self.assertTrue(first.endswith('/BBBB.mp3'));self.assertTrue(second.endswith('/CCCC.mp3'))
            self.assertEqual(len(occupied),2);self.assertFalse(phone.writes)
        asyncio.run(work())

    def test_native_multisession_replay_preserves_unselected_original(self):
        import hashlib
        from mutagen.id3 import ID3,TIT2
        import test_transfers as support
        from test_deletion import Phone
        from importios.library import read_catalogue
        from importios.transfers import PREF
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);tracks=[];phone=Phone();original=phone.files['/iTunes_Control/Music/F00/AAAA.mp3']
            for i in range(101):
                path=root/f'{i}.mp3';path.write_bytes((support.FIXTURES/'sample.mp3').read_bytes())
                tags=ID3(path);tags.add(TIT2(encoding=3,text=f'Bulk {i}'));tags.save(path,padding=lambda _:0)
                tracks.append({'id':hashlib.sha256(path.read_bytes()).hexdigest(),'path':str(path)})
            with patch('importios.transfers.device',phone.device),patch('importios.transfers.Atc',lambda peer:peer):
                added=run_transfer('import',tracks,root/'backups',lambda *a:None)
                self.assertEqual(added['imported'],101);self.assertEqual(added['batches_completed'],3)
                database=root/'read.sqlite';database.write_bytes(phone.files[PREF+'MediaLibrary.sqlitedb'])
                chosen=[dict(t,_device_token=phone._tupaq_device_token) for t in read_catalogue(database) if t['id']!='1']
                removed=run_transfer('delete',chosen,root/'backups',lambda *a:None)
                self.assertEqual(removed['deleted'],101);self.assertEqual(removed['batches_completed'],2)
                database.write_bytes(phone.files[PREF+'MediaLibrary.sqlitedb'])
                self.assertEqual([t['id'] for t in read_catalogue(database)],['1'])
                self.assertEqual(phone.files['/iTunes_Control/Music/F00/AAAA.mp3'],original);self.assertFalse(phone.handles)

    def test_lost_final_ack_does_not_duplicate_audio_on_full_selection_retry(self):
        import hashlib
        from mutagen.id3 import ID3,TIT2
        import test_transfers as support
        from test_deletion import Phone
        from importios.library import read_catalogue
        from importios.transfers import PREF
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);tracks=[];phone=Phone();phone.fail='lost-finished'
            for i in range(101):
                path=root/f'{i}.mp3';path.write_bytes((support.FIXTURES/'sample.mp3').read_bytes())
                tags=ID3(path);tags.add(TIT2(encoding=3,text=f'Recovery {i}'));tags.save(path,padding=lambda _:0)
                tracks.append({'id':hashlib.sha256(path.read_bytes()).hexdigest(),'path':str(path)})
            with patch('importios.transfers.device',phone.device),patch('importios.transfers.Atc',lambda peer:peer):
                stopped=run_transfer('import',tracks,root/'backups',lambda *a:None)
                self.assertTrue(stopped['bulk_stopped']);self.assertEqual(stopped['processed'],0)
                phone.fail=None
                recovered=run_transfer('import',tracks,root/'backups',lambda *a:None)
                self.assertFalse(recovered.get('bulk_stopped'));self.assertEqual(recovered['imported'],52);self.assertEqual(recovered['already_imported'],49)
                database=root/'read.sqlite';database.write_bytes(phone.files[PREF+'MediaLibrary.sqlitedb'])
                self.assertEqual(len(read_catalogue(database)),102);self.assertFalse(phone.handles)

    def test_native_cancel_after_commit_retries_without_duplicate_entries(self):
        import hashlib
        from mutagen.id3 import ID3,TIT2
        import test_transfers as support
        from test_deletion import Phone
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);tracks=[];phone=Phone();control=TransferControl()
            for i in range(101):
                path=root/f'{i}.mp3';path.write_bytes((support.FIXTURES/'sample.mp3').read_bytes())
                tags=ID3(path);tags.add(TIT2(encoding=3,text=f'Cancel {i}'));tags.save(path,padding=lambda _:0)
                tracks.append({'id':hashlib.sha256(path.read_bytes()).hexdigest(),'path':str(path)})
            def report(*args):
                if 'Importando:' in args[2]:control.request()
            report.control=control
            with patch('importios.transfers.device',phone.device),patch('importios.transfers.Atc',lambda peer:peer):
                stopped=run_transfer('import',tracks,root/'backups',report)
                self.assertTrue(stopped['cancelled']);self.assertEqual(stopped['processed'],49)
                recovered=run_transfer('import',tracks,root/'backups',lambda *a:None)
                self.assertEqual(recovered['imported'],52);self.assertEqual(recovered['already_imported'],49)

    def test_catalogue_capacity_is_checked_before_native_commit(self):
        import test_transfers as support
        from test_deletion import Phone
        from importios.transfers import TransferError,PREF
        with tempfile.TemporaryDirectory() as root:
            phone=Phone();original=phone.files[PREF+'MediaLibrary.sqlitedb']
            import hashlib
            path=support.FIXTURES/'sample.mp3'
            selected=[{'id':hashlib.sha256(path.read_bytes()).hexdigest(),'path':str(path)}]
            with patch('importios.transfers.device',phone.device),patch('importios.transfers.Atc',lambda peer:peer),patch('importios.library.MAX_TRACKS',1):
                with self.assertRaises(TransferError) as caught:run_transfer('import',selected,Path(root),lambda *a:None)
            self.assertIn('import-catalogue-limit',caught.exception.diagnostic)
            self.assertEqual(phone.files[PREF+'MediaLibrary.sqlitedb'],original)
            self.assertFalse(phone.writes);self.assertFalse(phone.handles)
