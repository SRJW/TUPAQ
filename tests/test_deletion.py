"""Native delete sessions never upload, unlink or silently delete another item."""
from contextlib import closing
from pathlib import Path
import json
import plistlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import test_transfers as support
from importios.transfers import run_transfer,TransferError

class Phone(support.Phone):
    _tupaq_device_token="a"*64
    async def start_lockdown_service(self,name):return Peer(self)

class Peer(support.Peer):
    async def send(self,msg):
        p=self.phone
        if msg['Command']=='FileError' and p.fail=='foreign-request':
            p.sent.append(msg);self.queue.append({'Command':'SyncFinished','Session':2});return
        if msg['Command']!='FinishedSyncingMetadata':return await super().send(msg)
        envelope=plistlib.loads(p.files[support.MEDIA+'/Sync_00000000.plist'])
        operations=envelope['operations'][1:]
        if not operations or operations[0]['operation']!='delete_track':return await super().send(msg)
        p.sent.append(msg);p.operations=operations
        assert envelope['revision']==self.anchor+1
        assert all(set(op)=={'operation','pid'} and op['operation']=='delete_track' for op in operations)
        assert len(p.files[support.MEDIA+'/Sync_00000000.plist.cig'])==21
        with closing(sqlite3.connect(':memory:')) as db:
            db.deserialize(p.files[support.PREF+'MediaLibrary.sqlitedb'])
            for op in operations:
                wire=op['pid'] if op['pid']<2**63 else op['pid']-2**64
                pid=db.execute('SELECT item_pid FROM item_store WHERE sync_id=?',(wire,)).fetchone()[0]
                for table in ('item','item_extra','item_store','item_playback'):db.execute(f'DELETE FROM {table} WHERE item_pid=?',(pid,))
            if p.fail=='collateral-delete':db.executescript('DELETE FROM item; DELETE FROM item_extra; DELETE FROM item_store;')
            db.execute('UPDATE _MLDatabaseProperties SET value=?',(str(self.anchor+1),));db.commit()
            p.files[support.PREF+'MediaLibrary.sqlitedb']=db.serialize()
        del p.files[support.MEDIA+'/Sync_00000000.plist'];del p.files[support.MEDIA+'/Sync_00000000.plist.cig']
        if p.fail=='request-deleted':
            self.queue.append({'Command':'AssetManifest','Session':2,'Params':{'AssetManifest':{'Media':[
                {'AssetType':'Music','IsDownload':True,'AssetID':str(operations[0]['pid']),'Variant':{'AssetParts':4}}]}}})
        if p.fail=='foreign-request':
            self.queue.append({'Command':'AssetManifest','Session':2,'Params':{'AssetManifest':{'Media':[
                {'AssetType':'Music','IsDownload':True,'AssetID':'77','Variant':{'AssetParts':4}}]}}});return
        if p.fail!='lost-finished':self.queue.append({'Command':'SyncFinished','Session':2})

class DeletionTests(unittest.TestCase):
    selected=support.TransferTests.selected
    call=support.TransferTests.call
    def tracks(self,phone,root):
        tracks=support.TransferTests.tracks(self,phone,root)
        for track in tracks:track['_device_token']=phone._tupaq_device_token
        return tracks

    def test_native_delete_preserves_survivor_and_leaves_audio_cleanup_to_ios(self):
        with tempfile.TemporaryDirectory() as root:
            p=Phone();self.call(p,'import',[self.selected('aac.m4a')],root)
            chosen=next(t for t in self.tracks(p,root) if t['id']=='1');p.sent.clear();p.writes.clear()
            result=self.call(p,'delete',[chosen],root)
            self.assertEqual(result['deleted'],1)
            self.assertEqual(len(self.tracks(p,root)),1)
            self.assertTrue(all('/Sync/Media/' in path for path in p.writes))
            self.assertTrue(p.files['/iTunes_Control/Music/F00/AAAA.mp3'])
            self.assertFalse(any(m['Command']=='FileComplete' for m in p.sent))
            # Completed deletion receipts must not become import/dedup authorities.
            self.assertEqual(self.call(p,'import',[self.selected('sample.wav')],root)['imported'],1)

    def test_stale_or_other_library_selection_stops_before_metadata(self):
        for field,value in [('library_database',999),('title','Changed'),('_device_token','b'*64),('library_wire',12345)]:
            with self.subTest(field=field),tempfile.TemporaryDirectory() as root:
                p=Phone();chosen=self.tracks(p,root)[0];chosen[field]=value
                with self.assertRaises(TransferError) as caught:self.call(p,'delete',[chosen],root)
                self.assertIn('delete-stale-selection',caught.exception.diagnostic)
                self.assertFalse(p.sent);self.assertFalse(p.writes)

    def test_unsigned_native_pid_is_bound_to_signed_sqlite_wire(self):
        with tempfile.TemporaryDirectory() as root:
            p=Phone()
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(p.files[support.PREF+'MediaLibrary.sqlitedb']);db.execute('UPDATE item_store SET sync_id=-77');db.commit()
                p.files[support.PREF+'MediaLibrary.sqlitedb']=db.serialize()
            self.call(p,'delete',self.tracks(p,root),root)
            self.assertEqual(p.operations[0]['pid'],2**64-77)

    def test_deleted_asset_requests_are_rejected_without_acknowledgement(self):
        with tempfile.TemporaryDirectory() as root:
            p=Phone();p.fail='request-deleted'
            with self.assertRaises(TransferError):self.call(p,'delete',self.tracks(p,root),root)
            self.assertFalse(any(m['Command'] in ('FileComplete','FileError') for m in p.sent))

    def test_collateral_removal_is_never_reported_as_success(self):
        with tempfile.TemporaryDirectory() as root:
            p=Phone();self.call(p,'import',[self.selected('aac.m4a')],root);p.fail='collateral-delete'
            chosen=next(t for t in self.tracks(p,root) if t['id']=='1')
            with self.assertRaises(TransferError) as caught:self.call(p,'delete',[chosen],root)
            self.assertIn('delete-item-set',caught.exception.diagnostic)

    def test_lost_completion_is_checked_read_only_and_does_not_block_next_import(self):
        with tempfile.TemporaryDirectory() as root:
            p=Phone();p.fail='lost-finished'
            with self.assertRaises(TransferError):self.call(p,'delete',self.tracks(p,root),root)
            p.fail=None;sent=len(p.sent);writes=len(p.writes)
            result=self.call(p,'verify',[],root)
            self.assertEqual(result['removed'],1);self.assertEqual(len(p.sent),sent);self.assertEqual(len(p.writes),writes)
            self.assertEqual(self.call(p,'import',[self.selected('sample.wav')],root)['imported'],1)

    def test_only_known_survivor_ancillary_requests_are_refused(self):
        with tempfile.TemporaryDirectory() as root:
            p=Phone();self.call(p,'import',[self.selected('aac.m4a')],root)
            chosen=next(t for t in self.tracks(p,root) if t['id']!='1');p.sent.clear();p.fail='foreign-request'
            self.assertEqual(self.call(p,'delete',[chosen],root)['deleted'],1)
            acks=[m for m in p.sent if m['Command']=='FileError']
            self.assertEqual([m['Params']['AssetID'] for m in acks],['77'])
            self.assertFalse(any(m['Command']=='FileComplete' for m in p.sent))
