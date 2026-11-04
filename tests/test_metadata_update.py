"""Replay separate Artwork delivery and owned-track date/cover updates."""
from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import plistlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from test_transfers import Phone,Peer,FIXTURES,PREF,MEDIA
from importios.transfers import run_transfer,TransferError


class MetadataPhone(Phone):
    async def start_lockdown_service(self,name):return MetadataPeer(self)

    def legacy(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.deserialize(self.files[PREF+'MediaLibrary.sqlitedb'])
            db.executescript('DELETE FROM artwork;DELETE FROM artwork_token;UPDATE item SET date_added=0;')
            self.files[PREF+'MediaLibrary.sqlitedb']=db.serialize()


class MetadataPeer(Peer):
    async def send(self,msg):
        p=self.phone
        if msg['Command']=='FinishedSyncingMetadata':
            envelope=plistlib.loads(p.files[MEDIA+'/Sync_00000000.plist'])
            self.updates=[op for op in envelope['operations'] if op['operation']=='update_track']
            if not self.updates:
                await super().send(msg);return
            p.sent.append(msg);self.remaining=set()
            assert envelope['revision']==self.anchor+1
            for op in self.updates:
                assert set(op)=={'operation','pid','item'}
                assert set(op['item'])<= {'date_created','date_modified','artwork_cache_id','artwork_checksum'}
                if op['item'].get('artwork_cache_id'):self.remaining.add(str(op['pid']))
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(p.files[PREF+'MediaLibrary.sqlitedb'])
                for op in self.updates:
                    if p.fail!='ignore-date':
                        db.execute('UPDATE item SET date_added=? WHERE item_pid=(SELECT item_pid FROM item_store WHERE sync_id=?)',
                            (int((op['item']['date_created']-datetime(2001,1,1)).total_seconds()),op['pid']))
                db.execute('UPDATE _MLDatabaseProperties SET value=?',(str(self.anchor+1),))
                db.commit();p.files[PREF+'MediaLibrary.sqlitedb']=db.serialize()
            del p.files[MEDIA+'/Sync_00000000.plist'];del p.files[MEDIA+'/Sync_00000000.plist.cig']
            if self.remaining:
                self.queue.append({'Command':'AssetManifest','Session':2,'Params':{'AssetManifest':{'Media':[
                    {'AssetType':'Music','IsDownload':True,'AssetID':wire,'Variant':{'AssetParts':6}}
                    for wire in sorted(self.remaining)]}}})
            else:self.queue.append({'Command':'SyncFinished','Session':2})
            return
        if msg['Command']=='FileComplete' and getattr(self,'updates',[]):
            p.sent.append(msg);wire=msg['Params']['AssetID'];assert msg['Params']['AssetPath']==''
            op=next(op for op in self.updates if str(op['pid'])==wire)
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(p.files[PREF+'MediaLibrary.sqlitedb'])
                pid=db.execute('SELECT item_pid FROM item_store WHERE sync_id=?',(int(wire),)).fetchone()[0]
            p.register_art(op,pid)
            if p.fail=='tamper-art':
                key=next(k for k in p.files if '/Artwork/Originals/' in k);p.files[key]=b'corrupt'
            self.remaining.remove(wire)
            if not self.remaining:self.queue.append({'Command':'SyncFinished','Session':2})
            return
        await super().send(msg)


class MetadataUpdateTests(unittest.TestCase):
    def selected(self,name='covered-aac.m4a'):
        path=FIXTURES/name;return {'path':str(path),'id':hashlib.sha256(path.read_bytes()).hexdigest()}

    def call(self,p,mode,selected,root):
        with patch('importios.transfers.device',p.device),patch('importios.transfers.Atc',lambda peer:peer):
            return run_transfer(mode,selected,root,lambda *args:None)

    def owned(self,p,root,name='covered-aac.m4a'):
        result=self.call(p,'import',[self.selected(name)],root)
        journal=Path(result['backup'])/'journal.json';record=json.loads(journal.read_text(encoding='utf-8'))
        for entry in record['entries']:entry.pop('artwork',None);entry.pop('added_at',None)
        journal.write_text(json.dumps(record),encoding='utf-8');p.legacy();p.sent.clear();p.writes.clear()
        return record['entries'][0]

    def test_new_import_sends_cover_before_audio_and_records_date_and_real_size(self):
        p=MetadataPhone()
        with tempfile.TemporaryDirectory() as root:
            result=self.call(p,'import',[self.selected()],root)
            record=json.loads((Path(result['backup'])/'journal.json').read_text(encoding='utf-8'));entry=record['entries'][0]
            art=f"/Airlock/Media/Artwork/{entry['track_id']}";audio=f"/Airlock/Media/{entry['track_id']}.m4a"
            self.assertLess(p.writes.index(art),p.writes.index(audio))
            operation=p.operations[0]
            self.assertEqual(operation['item']['artwork_checksum'],entry['artwork']['size']+17)
            self.assertEqual(operation['location']['file_size'],entry['source']['size'])
            self.assertNotIn('location',operation['location'])
            self.assertIsInstance(operation['item']['date_created'],datetime)
            self.assertTrue(any('/Artwork/Originals/' in path for path in p.files))

    def test_existing_legacy_song_gets_cover_and_recent_date_without_audio_reupload(self):
        p=MetadataPhone()
        with tempfile.TemporaryDirectory() as root:
            entry=self.owned(p,root);audio=p.files['/'+entry['destination']]
            result=self.call(p,'repair',[],root)
            self.assertEqual((result['updated'],result['covers']),(1,1))
            self.assertEqual(p.files['/'+entry['destination']],audio)
            self.assertFalse(any(path.startswith('/Airlock/Media/') and '/Artwork/' not in path for path in p.writes))
            self.assertEqual(len([m for m in p.sent if m['Command']=='FileComplete']),1)
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(p.files[PREF+'MediaLibrary.sqlitedb'])
                self.assertEqual(db.execute('SELECT COUNT(*) FROM item').fetchone()[0],2)
                self.assertEqual(db.execute('SELECT date_added FROM item WHERE item_pid=1').fetchone()[0],0)
                self.assertGreater(db.execute('SELECT MAX(date_added) FROM item').fetchone()[0],0)

    def test_song_without_embedded_cover_gets_date_only(self):
        p=MetadataPhone()
        with tempfile.TemporaryDirectory() as root:
            self.owned(p,root,'sample.mp3')
            result=self.call(p,'repair',[],root)
            self.assertEqual((result['updated'],result['covers']),(1,0))
            self.assertFalse(any(m['Command']=='FileComplete' for m in p.sent))
            self.assertFalse(any('/Airlock/' in path for path in p.writes))

    def test_corrupt_originals_cache_and_ignored_date_are_not_reported_as_success(self):
        for failure,code in [('tamper-art','verify-artwork-original'),('ignore-date','verify-added-date')]:
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as root:
                p=MetadataPhone();self.owned(p,root);p.fail=failure
                with self.assertRaises(TransferError) as caught:self.call(p,'repair',[],root)
                self.assertIn(code,caught.exception.diagnostic)
                p.fail=None
                result=self.call(p,'import',[self.selected('sample.wav')],root)
                self.assertEqual(result['imported'],1)
                self.assertEqual(result['metadata_unverified'],1)

    def test_no_registered_import_is_never_an_update_authority(self):
        p=MetadataPhone()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(TransferError) as caught:self.call(p,'repair',[],root)
            self.assertIn('metadata-no-owned-tracks',caught.exception.diagnostic)
            self.assertFalse(p.sent);self.assertFalse(p.writes)
