"""Metadata-first phone replay, including recovery of the grey pathless row."""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import plistlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from test_transfers import Phone,Peer,FIXTURES,PREF,MEDIA
from importios.sync.protocol import ProtocolError,validate_manifest
from importios.transfers import run_transfer,TransferError


class PendingPhone(Phone):
    def __init__(self):
        super().__init__()
        self.parts=5
        self.early_terminal=False
        self.modify('''ALTER TABLE item ADD COLUMN remote_location_id INTEGER DEFAULT 0;
            CREATE TABLE item_state(item_pid INTEGER PRIMARY KEY,is_placeholder INTEGER,is_library_added INTEGER,
                has_non_purgeable_asset INTEGER,is_supported_type INTEGER);
            INSERT INTO item_state VALUES(1,0,1,1,1);''')

    def modify(self,sql):
        with closing(sqlite3.connect(':memory:')) as db:
            db.deserialize(self.files[PREF+'MediaLibrary.sqlitedb']);db.executescript(sql)
            self.files[PREF+'MediaLibrary.sqlitedb']=db.serialize()

    async def start_lockdown_service(self,name):
        assert name=='com.apple.atc'
        return PendingPeer(self)


class PendingPeer(Peer):
    async def receive(self):
        message=await super().receive()
        if message['Command']=='SyncFinished' and self.phone.early_terminal:
            self.last_received_at=0
        return message

    async def send(self,msg):
        p=self.phone
        if msg['Command']=='FinishedSyncingMetadata':
            if MEDIA+'/Sync_00000000.plist' in p.files:
                await super().send(msg)
                # Metadata is committed BEFORE the audio demand, as on iOS.
                for op in p.operations:
                    p.apply(op,'iTunes_Control/Music/F00/WAIT.mp3',(FIXTURES/'sample.mp3').read_bytes())
                    with closing(sqlite3.connect(':memory:')) as db:
                        db.deserialize(p.files[PREF+'MediaLibrary.sqlitedb'])
                        item=db.execute('SELECT item_pid FROM item_store WHERE sync_id=?',(op['pid'],)).fetchone()[0]
                        db.execute('UPDATE item SET base_location_id=0 WHERE item_pid=?',(item,))
                        db.execute('UPDATE item_extra SET location=NULL WHERE item_pid=?',(item,))
                        db.execute('INSERT INTO item_state VALUES(?,0,1,0,1)',(item,))
                        db.execute('UPDATE _MLDatabaseProperties SET value=?',(str(self.anchor+1),))
                        db.commit();p.files[PREF+'MediaLibrary.sqlitedb']=db.serialize()
                p.files.pop(MEDIA+'/Sync_00000000.plist',None);p.files.pop(MEDIA+'/Sync_00000000.plist.cig',None)
            else:
                # Matching-anchor empty delta: no signed operations or insert.
                p.sent.append(msg)
                assert msg['Params']['DataclassAnchors']['Media']==str(self.anchor)
                assert msg['Params']['SyncTypes']['Media']==1
                self.remaining={str(op['pid']) for op in p.operations}
                self.queue.append({'Command':'AssetManifest','Session':2,'Params':{'AssetManifest':{'Media':[
                    {'AssetType':'Music','IsDownload':True,'AssetID':identifier,'Variant':{'AssetParts':p.parts}}
                    for identifier in sorted(self.remaining)]}}})
            for record in self.queue[-1]['Params']['AssetManifest']['Media']:
                if record['AssetID'] in self.remaining:
                    covered=next(op for op in p.operations if str(op['pid'])==record['AssetID'])['item'].get('artwork_cache_id')
                    record['Variant']['AssetParts']=7 if covered and p.parts==5 else p.parts
            return
        if msg['Command']=='FileComplete':
            p.sent.append(msg);identifier=msg['Params']['AssetID'];destination=msg['Params']['AssetPath']
            p.files['/'+destination]=p.files.pop('/Airlock/Media/'+identifier)
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(p.files[PREF+'MediaLibrary.sqlitedb'])
                item=db.execute('SELECT item_pid FROM item_store WHERE sync_id=?',(int(identifier),)).fetchone()[0]
                db.execute('UPDATE item SET base_location_id=1 WHERE item_pid=?',(item,))
                db.execute('UPDATE item_extra SET location=? WHERE item_pid=?',(Path(destination).name,item))
                db.execute('UPDATE item_state SET has_non_purgeable_asset=1 WHERE item_pid=?',(item,))
                db.commit();p.files[PREF+'MediaLibrary.sqlitedb']=db.serialize()
            p.register_art(next(op for op in p.operations if str(op['pid'])==identifier),item)
            self.remaining.remove(identifier)
            if not self.remaining:self.queue.append({'Command':'SyncFinished','Session':2})
            return
        await super().send(msg)


class RecoveryTests(unittest.TestCase):
    def selected(self,name='sample.mp3'):
        path=FIXTURES/name
        return {'path':str(path),'id':hashlib.sha256(path.read_bytes()).hexdigest()}

    def call(self,phone,mode,selected,root):
        with patch('importios.transfers.device',phone.device),patch('importios.transfers.Atc',lambda peer:peer):
            return run_transfer(mode,selected,root,lambda *args:None)

    def pending(self,phone,root,selected=None):
        # Reproduce preview.3's strict guard AFTER the phone committed metadata.
        with patch('importios.transfers.validate_manifest',side_effect=ProtocolError('manifest-own-parts')):
            with self.assertRaises(TransferError):self.call(phone,'import',selected or [self.selected()],root)
        journal=next(Path(root).glob('*/journal.json'))
        record=json.loads(journal.read_text(encoding='utf-8'))
        self.assertEqual(record['phase'],'metadata-announced')
        phone.sent.clear();phone.writes.clear()
        return journal,record

    def test_audio_with_genius_completes_normal_metadata_first_import(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            result=self.call(phone,'import',[self.selected()],root)
            self.assertEqual(result['imported'],1)
            self.assertEqual(len([m for m in phone.sent if m['Command']=='FileComplete']),1)
            self.assertFalse(any(m['Command']=='FileError' and m['Params']['AssetID']!='77' for m in phone.sent))

    def test_pending_resume_uploads_same_ids_without_reinsert_or_anchor_increment(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            journal,record=self.pending(phone,root)
            result=self.call(phone,'resume',[],root)
            self.assertEqual(result['verified'],1)
            self.assertEqual(json.loads(journal.read_text(encoding='utf-8'))['phase'],'completed')
            self.assertFalse(any(path.startswith(MEDIA) for path in phone.writes))
            finish=next(m for m in phone.sent if m['Command']=='FinishedSyncingMetadata')
            self.assertEqual(finish['Params']['DataclassAnchors']['Media'],'8')
            complete=next(m for m in phone.sent if m['Command']=='FileComplete')
            self.assertEqual(complete['Params']['AssetID'],str(record['entries'][0]['track_id']))
            self.assertEqual(phone.files['/'+record['entries'][0]['destination']],(FIXTURES/'sample.mp3').read_bytes())
            self.assertEqual(len(list(Path(root).glob('*/journal.json'))),1)
            self.assertFalse(phone.handles)

    def test_removed_pending_item_gets_fresh_checked_import_without_duplicates(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            journal,record=self.pending(phone,root)
            phone.modify('''DELETE FROM item WHERE item_pid!=1;DELETE FROM item_extra WHERE item_pid!=1;
                DELETE FROM item_store WHERE item_pid!=1;DELETE FROM item_state WHERE item_pid!=1;
                DELETE FROM item_playback WHERE item_pid!=1;''')
            result=self.call(phone,'resume',[],root)
            self.assertEqual(result['imported'],1)
            self.assertEqual(json.loads(journal.read_text(encoding='utf-8'))['phase'],'resolved-items-removed')
            complete=next(m for m in phone.sent if m['Command']=='FileComplete')
            self.assertNotEqual(complete['Params']['AssetID'],str(record['entries'][0]['track_id']))
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(phone.files[PREF+'MediaLibrary.sqlitedb'])
                self.assertEqual(db.execute('SELECT COUNT(*) FROM item').fetchone()[0],2)

    def test_already_completed_operation_is_only_verified_without_another_send(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            result=self.call(phone,'import',[self.selected()],root)
            journal=Path(result['backup'])/'journal.json'
            record=json.loads(journal.read_text(encoding='utf-8'));record['phase']='metadata-announced'
            journal.write_text(json.dumps(record),encoding='utf-8');phone.sent.clear();phone.writes.clear()
            self.assertEqual(self.call(phone,'resume',[],root)['verified'],1)
            self.assertFalse(phone.sent);self.assertFalse(phone.writes)

    def test_changed_source_stops_recovery_before_any_atc_session(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root,tempfile.TemporaryDirectory() as local:
            path=Path(local)/'song.mp3';path.write_bytes((FIXTURES/'sample.mp3').read_bytes())
            self.pending(phone,root,[{'path':str(path),'id':hashlib.sha256(path.read_bytes()).hexdigest()}])
            path.write_bytes(path.read_bytes()+b'changed')
            with self.assertRaises(TransferError) as caught:self.call(phone,'resume',[],root)
            self.assertIn('source-changed',caught.exception.diagnostic)
            self.assertFalse(phone.sent);self.assertFalse(phone.writes)

    def test_relocated_original_can_be_selected_by_content_hash(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root,tempfile.TemporaryDirectory() as local:
            path=Path(local)/'song.mp3';path.write_bytes((FIXTURES/'sample.mp3').read_bytes())
            selected={'path':str(path),'id':hashlib.sha256(path.read_bytes()).hexdigest()}
            self.pending(phone,root,[selected]);path.unlink()
            self.assertEqual(self.call(phone,'resume',[self.selected()],root)['verified'],1)

    def test_cloud_placeholder_wrong_groups_and_changed_library_are_never_recovered(self):
        cases=[("UPDATE item_state SET is_placeholder=1 WHERE item_pid!=1",'recovery-pending-state'),
            ("UPDATE item SET remote_location_id=9 WHERE item_pid!=1",'recovery-pending-state'),
            ("UPDATE album SET sync_id=999 WHERE album_pid!=3",'recovery-owned-groups'),
            ("UPDATE db_info SET db_pid=99",'verify-library-identity'),
            ("UPDATE item_extra SET title='changed' WHERE item_pid=1",'verify-original-music-changed')]
        for sql,code in cases:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as root:
                phone=PendingPhone();self.pending(phone,root);phone.modify(sql)
                with self.assertRaises(TransferError) as caught:self.call(phone,'resume',[],root)
                self.assertIn(code,caught.exception.diagnostic)
                self.assertFalse(phone.sent);self.assertFalse(phone.writes)

    def test_change_after_ready_and_airlock_collision_stop_without_completion(self):
        for kind in ('catalogue-after-ready','airlock'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root:
                phone=PendingPhone();_,receipt=self.pending(phone,root)
                if kind=='airlock':phone.files[f"/Airlock/Media/{receipt['entries'][0]['track_id']}"]=b'unknown'
                else:phone.fail=kind
                with self.assertRaises(TransferError):self.call(phone,'resume',[],root)
                self.assertFalse(phone.writes)
                self.assertFalse(any(m['Command'] in ('FinishedSyncingMetadata','FileComplete','FileError') for m in phone.sent))

    def test_unknown_own_parts_stop_before_audio_ack_and_include_numeric_diagnostic(self):
        for parts in (0,2,3,4,7,8,9,255):
            with self.subTest(parts=parts),tempfile.TemporaryDirectory() as root:
                phone=PendingPhone();self.pending(phone,root);phone.parts=parts
                with self.assertRaises(TransferError) as caught:self.call(phone,'resume',[],root)
                self.assertIn('manifest-own-parts',caught.exception.diagnostic)
                self.assertIn('asset_parts',caught.exception.diagnostic)
                self.assertFalse(phone.writes)
                self.assertFalse(any(m['Command'] in ('FileComplete','FileError') for m in phone.sent))

    def test_early_terminal_is_not_claimed_as_a_success(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            journal,_=self.pending(phone,root);phone.early_terminal=True
            with self.assertRaises(TransferError) as caught:self.call(phone,'resume',[],root)
            self.assertIn('terminal-before-settlement',caught.exception.diagnostic)
            self.assertNotEqual(json.loads(journal.read_text(encoding='utf-8'))['phase'],'completed')
            # A separate readback can subsequently establish the actual effect.
            self.assertEqual(self.call(phone,'verify',[],root)['verified'],1)

    def test_pending_batch_completes_without_extra_items(self):
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            self.pending(phone,root,[self.selected(),self.selected('sample.m4a')])
            self.assertEqual(self.call(phone,'resume',[],root)['verified'],2)
            self.assertEqual(len([m for m in phone.sent if m['Command']=='FileComplete']),2)


class SerializedPeer:
    """Exercise production framing/pump instead of replacing Atc with Peer."""
    def __init__(self,peer,early=False):
        import asyncio
        self.peer,self.buffer,self.early=peer,bytearray(),early
        self.condition=asyncio.Condition()

    async def sendall(self,raw):
        import struct
        assert struct.unpack('<I',raw[:4])[0]==len(raw)-4
        message=plistlib.loads(raw[4:])
        await self.peer.send(message)
        if self.early and message['Command']=='FinishedSyncingMetadata':
            self.peer.queue.append({'Command':'SyncFinished','Session':2})
        async with self.condition:self.condition.notify_all()

    async def recvall(self,size):
        import struct
        async with self.condition:
            while len(self.buffer)<size:
                if self.peer.queue:
                    raw=plistlib.dumps(await self.peer.receive(),fmt=plistlib.FMT_BINARY)
                    self.buffer.extend(struct.pack('<I',len(raw))+raw)
                else:
                    await self.condition.wait()
            data=bytes(self.buffer[:size]);del self.buffer[:size]
            return data

    async def close(self):
        self.peer.phone.closed=True


class FramedRecoveryTests(unittest.TestCase):
    selected = RecoveryTests.selected
    call = RecoveryTests.call
    pending = RecoveryTests.pending
    def test_production_frame_pump_completes_existing_pending_audio(self):
        from importios.sync.protocol import Atc
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            self.pending(phone,root)
            with patch('importios.transfers.device',phone.device),patch('importios.transfers.Atc',lambda peer:Atc(SerializedPeer(peer))):
                result=run_transfer('resume',[],root,lambda *args:None)
            self.assertEqual(result['verified'],1)
            self.assertFalse(any(path.startswith(MEDIA) for path in phone.writes))

    def test_production_pump_remembers_terminal_received_before_audio_settlement(self):
        from importios.sync.protocol import Atc
        phone=PendingPhone()
        with tempfile.TemporaryDirectory() as root:
            journal,_=self.pending(phone,root)
            with patch('importios.transfers.device',phone.device),patch('importios.transfers.Atc',lambda peer:Atc(SerializedPeer(peer,early=True))):
                with self.assertRaises(TransferError) as caught:run_transfer('resume',[],root,lambda *args:None)
            self.assertIn('terminal-before-settlement',caught.exception.diagnostic)
            self.assertNotEqual(json.loads(journal.read_text(encoding='utf-8'))['phase'],'completed')
