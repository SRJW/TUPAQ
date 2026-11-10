"""Replay a synthetic phone; no real iPhone or private library is used."""
import asyncio
from contextlib import asynccontextmanager, closing
import hashlib
import io
import json
from pathlib import Path
import plistlib
import sqlite3
import struct
import tempfile
import unittest
import zlib
from datetime import datetime
from unittest.mock import patch

import mutagen

from importios.library import read_catalogue
from importios.phone_paths import media_path
from importios.sync.protocol import (Atc, ProtocolError, library_identity, saved_anchors,
                                    encode_operations, validate_manifest)
from importios.sync.source import inspect_source
from importios.transfers import run_transfer, TransferError, export_name, PREF, MEDIA

FIXTURES = Path(__file__).parent/'fixtures'


def preferences():
    data = bytearray(1232)
    data[:4] = b'frpd'
    struct.pack_into('<HH',data,4,1,25)
    data[8] = 1
    struct.pack_into('<QQ',data,12,0x1234,0xab)
    return bytes(data)


def host_database():
    root = bytearray(244)
    root[:4] = b'mhbd'
    struct.pack_into('<IIIII',root,4,244,244+144,1,117,1)
    struct.pack_into('<Q',root,72,11)
    section = bytearray(144)
    struct.pack_into('<IIII',section,0,0x6473686d,96,144,11)
    struct.pack_into('<IIII',section,96,7,1,1,0)
    return bytes(root+section)


def initial_catalogue():
    with closing(sqlite3.connect(':memory:')) as db:
        db.executescript('''PRAGMA user_version=2410000;
          CREATE TABLE item(item_pid INTEGER PRIMARY KEY,media_type INTEGER,item_artist_pid INTEGER,album_pid INTEGER,base_location_id INTEGER,date_added INTEGER DEFAULT 0);
          CREATE TABLE item_extra(item_pid INTEGER PRIMARY KEY,title TEXT,total_time_ms REAL,location TEXT,file_size INTEGER DEFAULT 0);
          CREATE TABLE item_playback(item_pid INTEGER PRIMARY KEY,audio_format INTEGER);
          CREATE TABLE artwork(artwork_token TEXT,artwork_source_type INTEGER,artwork_type INTEGER,artwork_variant_type INTEGER,relative_path TEXT);
          CREATE TABLE artwork_token(entity_pid INTEGER,entity_type INTEGER,artwork_token TEXT,artwork_source_type INTEGER,artwork_type INTEGER,artwork_variant_type INTEGER);
          CREATE TABLE item_artist(item_artist_pid INTEGER PRIMARY KEY,item_artist TEXT);
          CREATE TABLE album(album_pid INTEGER PRIMARY KEY,album TEXT,album_artist_pid INTEGER,sync_id INTEGER);
          CREATE TABLE album_artist(album_artist_pid INTEGER PRIMARY KEY,album_artist TEXT,sync_id INTEGER);
          CREATE TABLE item_store(item_pid INTEGER PRIMARY KEY,sync_id INTEGER);
          CREATE TABLE base_location(base_location_id INTEGER PRIMARY KEY,path TEXT);
          CREATE TABLE db_info(db_pid INTEGER,primary_container_pid INTEGER);
          CREATE TABLE _MLDatabaseProperties(key TEXT,value TEXT);
          INSERT INTO db_info VALUES(11,12);
          INSERT INTO _MLDatabaseProperties VALUES('MLSyncClientSyncAnchor','7');
          INSERT INTO item(item_pid,media_type,item_artist_pid,album_pid,base_location_id) VALUES(1,8,2,3,1);
          INSERT INTO item_extra(item_pid,title,total_time_ms,location) VALUES(1,'Original',1044,'AAAA.mp3');
          INSERT INTO item_artist VALUES(2,'Artista original');
          INSERT INTO album_artist VALUES(4,'Artista original',21);
          INSERT INTO album VALUES(3,'Álbum original',4,31);
          INSERT INTO item_store VALUES(1,77);
          INSERT INTO base_location VALUES(1,'iTunes_Control/Music/F00');''')
        return db.serialize()


class Phone:
    def __init__(self):
        self.files = {PREF+'MediaLibrary.sqlitedb':initial_catalogue(),PREF+'iTunesPrefs':preferences(),
                      PREF+'iTunesCDB':host_database(),'/iTunes_Control/Music/F00/AAAA.mp3':(FIXTURES/'sample.mp3').read_bytes()}
        self.dirs = {MEDIA,'/Airlock/Media','/iTunes_Control/Music/F00'}
        self.handles, self.opens, self.writes, self.sent = {}, [], [], []
        self.fail, self.closed, self.operations = None, False, []

    def path(self,p):return '/'+str(p).strip('/')

    async def stat(self,p):
        p=self.path(p)
        if p in self.dirs:return {'st_ifmt':'S_IFDIR','st_size':0,'st_mtime':1}
        if p not in self.files:raise FileNotFoundError()
        return {'st_ifmt':'S_IFREG','st_size':len(self.files[p]),'st_mtime':1}

    async def listdir(self,p):
        p=self.path(p)+'/'
        return ['.','..']+[s[len(p):] for s in self.files if s.startswith(p) and '/' not in s[len(p):]]

    async def fopen(self,p,mode):
        p=self.path(p)
        assert 'MediaLibrary.sqlitedb' not in p or mode=='r', 'Never write SQLite on phone'
        if mode=='r' and p not in self.files:raise FileNotFoundError()
        if mode in ('w','a+'):
            self.files.setdefault(p,b'')
            if mode=='w':self.files[p]=b''
        self.opens.append((p,mode))
        h=len(self.opens);self.handles[h]=[p,0,mode]
        return h

    async def fclose(self,h):del self.handles[h]
    async def lock(self,h,op):pass
    async def makedirs(self,path):self.dirs.add(self.path(path))

    async def fread(self,h,size):
        p,off,mode=self.handles[h]
        assert mode=='r'
        block=self.files[p][off:off+min(size,1234)]
        self.handles[h][1]+=len(block)
        return block

    async def fwrite(self,h,data):
        p,off,mode=self.handles[h]
        assert mode=='w'
        self.writes.append(p)
        self.files[p]=self.files[p][:off]+data+self.files[p][off+len(data):]
        self.handles[h][1]+=len(data)

    async def rename(self,source,target):
        source,target=self.path(source),self.path(target)
        assert target not in self.files
        self.files[target]=self.files.pop(source)

    @asynccontextmanager
    async def device(self):yield self,self
    async def start_lockdown_service(self,name):
        assert name=='com.apple.atc'
        return Peer(self)

    def apply(self,operation,destination,audio):
        with closing(sqlite3.connect(':memory:')) as db:
            db.deserialize(self.files[PREF+'MediaLibrary.sqlitedb'])
            item=operation['item'];wire=operation['pid']
            # Deliberately make SQLite's item_pid different from the wire PID.
            pid=db.execute('SELECT COALESCE(MAX(item_pid),0)+1 FROM item').fetchone()[0]
            artist=db.execute('SELECT COALESCE(MAX(item_artist_pid),0)+1 FROM item_artist').fetchone()[0]
            album_artist=item['artist_pid'];album=item['album_pid']
            db.execute('INSERT INTO item_artist VALUES(?,?)',(artist,item['artist']))
            db.execute('INSERT OR IGNORE INTO album_artist VALUES(?,?,?)',(album_artist,item['album_artist'],album_artist))
            db.execute('INSERT OR IGNORE INTO album VALUES(?,?,?,?)',(album,item['album'],album_artist,album))
            db.execute('INSERT INTO item(item_pid,media_type,item_artist_pid,album_pid,base_location_id) VALUES(?,8,?,?,1)',(pid,artist,album))
            ms=item.get('total_time_ms')
            if ms is None:ms=mutagen.File(io.BytesIO(audio)).info.length*1000
            db.execute('INSERT INTO item_extra(item_pid,title,total_time_ms,location,file_size) VALUES(?,?,?,?,?)',(pid,item['title'],ms,Path(destination).name,len(audio)))
            db.execute('INSERT INTO item_playback VALUES(?,?)',(pid,operation['avformat_info']['audio_format']))
            db.execute('UPDATE item SET date_added=? WHERE item_pid=?',(int((item['date_created']-datetime(2001,1,1)).total_seconds()),pid))
            db.execute('INSERT INTO item_store VALUES(?,?)',(pid,wire))
            db.commit();self.files[PREF+'MediaLibrary.sqlitedb']=db.serialize()
        self.register_art(operation,pid)

    def register_art(self,operation,pid):
        cache=operation['item'].get('artwork_cache_id');path=f"/Airlock/Media/Artwork/{operation['pid']}"
        if not cache or path not in self.files:return
        data=self.files.pop(path);sha=hashlib.sha1(data).hexdigest();relative=sha[:2]+'/'+sha[2:]
        self.files[PREF+'Artwork/Originals/'+relative]=data
        with closing(sqlite3.connect(':memory:')) as db:
            db.deserialize(self.files[PREF+'MediaLibrary.sqlitedb'])
            album=db.execute('SELECT album_pid FROM item WHERE item_pid=?',(pid,)).fetchone()[0]
            db.execute('INSERT INTO artwork VALUES(?,300,6,0,?)',(str(cache),relative))
            for entity,kind in [(pid,0),(album,4)]:
                db.execute('DELETE FROM artwork_token WHERE entity_pid=? AND entity_type=? AND artwork_source_type=300',(entity,kind))
                db.execute('INSERT INTO artwork_token VALUES(?,?,?,300,6,0)',(entity,kind,str(cache)))
            db.commit();self.files[PREF+'MediaLibrary.sqlitedb']=db.serialize()


class Peer:
    def __init__(self,phone):self.phone=phone;self.queue=[];self.remaining=set()
    async def __aenter__(self):return self
    async def __aexit__(self,*ignored):self.phone.closed=True
    async def receive(self):
        if not self.queue:raise ConnectionResetError('synthetic disconnect')
        message=self.queue.pop(0)
        if message['Command']=='ReadyForSync' and self.phone.fail=='catalogue-after-ready':
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(self.phone.files[PREF+'MediaLibrary.sqlitedb'])
                db.execute("UPDATE _MLDatabaseProperties SET value=? WHERE key='MLSyncClientSyncAnchor'",(str(self.anchor+1),))
                db.commit();self.phone.files[PREF+'MediaLibrary.sqlitedb']=db.serialize()
        return message
    async def send(self,msg):
        p=self.phone;p.sent.append(msg)
        command=msg['Command']
        if command=='Ping':
            self.queue += [{'Command':'Pong','Session':2},
                {'Command':'Capabilities','Session':2,'Params':{'GrappaSupportInfo':{'version':1,'deviceType':0,'protocolVersion':1}}},
                {'Command':'SyncAllowed','Session':2,'Params':{'DataProtected':False,'ManualSync':True,'DisabledAssetTypes':[]}}]
        elif command=='RequestingSync':
            assert msg['Params']['HostInfo']['LibraryID']=='000000000000129F'
            reply=plistlib.loads((FIXTURES/'sync/grappa-fixed-vectors.plist').read_bytes())[0]['reply']
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(p.files[PREF+'MediaLibrary.sqlitedb'])
                self.anchor=int(db.execute("SELECT value FROM _MLDatabaseProperties WHERE key='MLSyncClientSyncAnchor'").fetchone()[0])
            anchor=str(self.anchor+1 if p.fail=='anchor' else self.anchor)
            self.queue.append({'Command':'ReadyForSync','Session':2,'Params':{'DataclassAnchors':{'Media':anchor,'Book':'0'},'DeviceInfo':{'Grappa':reply}}})
        elif command=='FinishedSyncingMetadata':
            assert msg['Params']['SyncTypes']['Media']==1
            assert msg['Params']['DataclassAnchors']['Media']==str(self.anchor+1)
            envelope=plistlib.loads(p.files[MEDIA+'/Sync_00000000.plist'])
            assert envelope['revision']==self.anchor+1
            assert len(p.files[MEDIA+'/Sync_00000000.plist.cig'])==21
            assert envelope['operations'][0]['operation']=='update_db_info'
            p.operations=envelope['operations'][1:]
            assert all(op['operation']=='insert_track' for op in p.operations)
            self.remaining={str(op['pid']) for op in p.operations}
            assets=[{'AssetType':'Music','IsDownload':True,'AssetID':i,'Variant':{'AssetParts':3 if next(op for op in p.operations if str(op['pid'])==i)['item'].get('artwork_cache_id') else 1}} for i in sorted(self.remaining)]
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(p.files[PREF+'MediaLibrary.sqlitedb'])
                if db.execute('SELECT 1 FROM item_store WHERE sync_id=77').fetchone():
                    assets.append({'AssetType':'Music','IsDownload':True,'AssetID':'77','Variant':{'AssetParts':4}})
            if p.fail=='manifest':assets[-1]['AssetID']='999999'
            self.queue.append({'Command':'AssetManifest','Session':2,'Params':{'AssetManifest':{'Media':assets}}})
            del p.files[MEDIA+'/Sync_00000000.plist'];del p.files[MEDIA+'/Sync_00000000.plist.cig']
        elif command=='FileComplete':
            identifier=msg['Params']['AssetID'];destination=msg['Params']['AssetPath']
            data=p.files.pop('/Airlock/Media/'+identifier)
            p.files['/'+destination]=data
            if p.fail=='tamper':
                p.files['/'+destination]=data[:-1]+bytes([data[-1]^1])
            operation=next(op for op in p.operations if str(op['pid'])==identifier)
            p.apply(operation,destination,data)
            self.remaining.remove(identifier)
            if not self.remaining:
                with closing(sqlite3.connect(':memory:')) as db:
                    db.deserialize(p.files[PREF+'MediaLibrary.sqlitedb'])
                    db.execute("UPDATE _MLDatabaseProperties SET value=?",(str(self.anchor+1),))
                    db.commit();p.files[PREF+'MediaLibrary.sqlitedb']=db.serialize()
                if p.fail!='lost-finished':self.queue.append({'Command':'SyncFinished','Session':2})


class TransferTests(unittest.TestCase):
    def selected(self,name='sample.mp3'):
        path=FIXTURES/name
        return {'path':str(path),'id':hashlib.sha256(path.read_bytes()).hexdigest()}

    def call(self,phone,mode,selected,destination):
        with patch('importios.transfers.device',phone.device),patch('importios.transfers.Atc',lambda peer:peer):
            return run_transfer(mode,selected,destination,lambda *args:None)

    def tracks(self,phone,folder):
        path=Path(folder)/'read.db';path.write_bytes(phone.files[PREF+'MediaLibrary.sqlitedb'])
        return read_catalogue(path)

    def test_all_requested_containers_project_to_native_format_codes_without_conversion(self):
        for name,code in [('sample.mp3',301),('sample.m4a',601),('covered-aac.m4a',502),('sample.wav',701),('sample.aiff',701)]:
            with self.subTest(name=name):
                source=inspect_source(FIXTURES/name)
                self.assertEqual(source['audio_format'],code)
                self.assertGreater(source['samples'],0)
                if 'year' in source:self.assertIs(type(source['year']),int)

    def test_delta_import_preserves_original_and_checks_each_audio_byte(self):
        phone=Phone();original=phone.files['/iTunes_Control/Music/F00/AAAA.mp3']
        with tempfile.TemporaryDirectory() as temporary:
            result=self.call(phone,'import',[self.selected('sample.m4a'),self.selected('sample.mp3')],Path(temporary)/'backups')
            self.assertEqual(result['imported'],2)
            journal=json.loads((Path(result['backup'])/'journal.json').read_text(encoding='utf-8'))
            self.assertEqual(journal['phase'],'completed')
            tracks=self.tracks(phone,temporary)
            self.assertEqual(len(tracks),3)
            self.assertEqual(tracks[0]['id'],'1')
            self.assertEqual(phone.files['/iTunes_Control/Music/F00/AAAA.mp3'],original)
            for entry in journal['entries']:
                self.assertEqual(hashlib.sha256(phone.files['/'+entry['destination']]).hexdigest(),entry['source']['id'])
            self.assertFalse(phone.handles)
            self.assertTrue(phone.closed)
            self.assertEqual(len([m for m in phone.sent if m['Command']=='FileError']),1)
            self.assertTrue((Path(result['backup'])/'before/1/MediaLibrary.sqlitedb').exists())

    def test_import_accepts_bounded_alternate_header_and_stale_host_media_anchor(self):
        phone=Phone()
        original=host_database()
        root=bytearray(original[:244])+bytearray(80)
        struct.pack_into('<IIIII',root,4,324,324+144,1,118,1)
        phone.files[PREF+'iTunesCDB']=bytes(root)+original[244:]
        stale=bytearray(original)
        struct.pack_into('<I',stale,244+96,6)
        phone.files[PREF+'iTunesDB']=bytes(stale)
        with tempfile.TemporaryDirectory() as temporary:
            result=self.call(phone,'import',[self.selected()],temporary)
            self.assertEqual(result['imported'],1)
            request=next(message for message in phone.sent if message['Command']=='RequestingSync')
            self.assertEqual(request['Params']['DataclassAnchors']['Media'],'7')

    def test_anchor_drift_never_stages_metadata_or_audio(self):
        phone=Phone();phone.fail='anchor'
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(TransferError,'importación') as caught:
                self.call(phone,'import',[self.selected()],temporary)
            self.assertIn('anchor-mismatch',caught.exception.diagnostic)
            self.assertFalse(phone.writes)
            self.assertFalse(any(m['Command']=='FinishedSyncingMetadata' for m in phone.sent))

    def test_saved_host_media_never_selects_request_or_delta_revision(self):
        for saved in (0,6,8,0xffffffff):
            with self.subTest(saved=saved),tempfile.TemporaryDirectory() as temporary:
                phone=Phone();data=bytearray(host_database())
                struct.pack_into('<I',data,244+96,saved)
                phone.files[PREF+'iTunesCDB']=bytes(data)
                phone.files[PREF+'iTunesDB']=host_database()
                result=self.call(phone,'import',[self.selected()],temporary)
                self.assertEqual(result['imported'],1)
                request=next(m for m in phone.sent if m['Command']=='RequestingSync')
                self.assertEqual(request['Params']['DataclassAnchors']['Media'],'7')
                finished=next(m for m in phone.sent if m['Command']=='FinishedSyncingMetadata')
                self.assertEqual(finished['Params']['DataclassAnchors']['Media'],'8')
                self.assertEqual(finished['Params']['SyncTypes']['Media'],1)
                self.assertEqual(len(self.tracks(phone,temporary)),2)

    def test_ahead_host_does_not_override_a_live_ready_mismatch(self):
        phone=Phone();phone.fail='anchor';data=bytearray(host_database())
        struct.pack_into('<I',data,244+96,8)
        phone.files[PREF+'iTunesCDB']=bytes(data)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(TransferError) as caught:self.call(phone,'import',[self.selected()],temporary)
            self.assertIn('anchor-mismatch',caught.exception.diagnostic)
            self.assertFalse(phone.writes)
            self.assertFalse(any(m['Command']=='FinishedSyncingMetadata' for m in phone.sent))

    def test_ahead_host_does_not_bypass_live_catalogue_change_after_ready(self):
        phone=Phone();phone.fail='catalogue-after-ready';data=bytearray(host_database())
        struct.pack_into('<I',data,244+96,10)
        phone.files[PREF+'iTunesCDB']=bytes(data)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(TransferError) as caught:self.call(phone,'import',[self.selected()],temporary)
            self.assertIn('catalogue-changed-before-stage',caught.exception.diagnostic)
            self.assertFalse(phone.writes)
            self.assertFalse(any(m['Command']=='FinishedSyncingMetadata' for m in phone.sent))

    def test_host_database_identity_and_voice_profile_still_required(self):
        for offset,value,code in [(72,99,'host-catalogue-identity'),(244+96+8,2,'host-anchor-unavailable')]:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as temporary:
                phone=Phone();data=bytearray(host_database())
                struct.pack_into('<I',data,244+96,10)
                struct.pack_into('<I',data,offset,value)
                phone.files[PREF+'iTunesCDB']=bytes(data)
                with self.assertRaises(TransferError) as caught:self.call(phone,'import',[self.selected()],temporary)
                self.assertIn(code,caught.exception.diagnostic)
                self.assertFalse(phone.writes)
                self.assertFalse(phone.sent)

    def test_entire_manifest_checked_before_any_audio_or_ancillary_ack(self):
        phone=Phone();phone.fail='manifest'
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(TransferError) as caught:self.call(phone,'import',[self.selected()],temporary)
            self.assertIn('manifest-unknown-asset',caught.exception.diagnostic)
            self.assertFalse(any(m['Command'] in ('FileComplete','FileError') for m in phone.sent))
            self.assertFalse(any('/Airlock/' in p for p in phone.writes))
            self.assertEqual(len(self.tracks(phone,temporary)),1)

    def test_uncertain_completion_can_be_verified_without_reimporting(self):
        phone=Phone();phone.fail='lost-finished'
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(TransferError):self.call(phone,'import',[self.selected()],temporary)
            before=len(phone.sent);phone.fail=None
            result=self.call(phone,'verify',[],temporary)
            self.assertEqual(result['verified'],1)
            self.assertEqual(len(phone.sent),before)
            self.assertEqual(len(self.tracks(phone,temporary)),2)

    def test_export_preserves_bytes_and_never_overwrites_an_existing_file(self):
        phone=Phone()
        with tempfile.TemporaryDirectory() as temporary:
            track=self.tracks(phone,temporary)[0]
            out=Path(temporary)/'out';out.mkdir()
            existing=out/export_name(track);existing.write_bytes(b'keep me')
            result=self.call(phone,'export',[track],out)
            self.assertEqual(result['exported'],1)
            self.assertEqual(existing.read_bytes(),b'keep me')
            self.assertEqual(Path(result['files'][0]).read_bytes(),phone.files['/'+track['afc_path']])
            self.assertFalse(phone.writes)
            self.assertFalse(phone.sent)

    def test_source_changed_since_selection_never_connects_to_device(self):
        with tempfile.TemporaryDirectory() as temporary,patch('importios.transfers.device') as connection:
            source=self.selected();source['id']='bad'
            with self.assertRaises(TransferError):run_transfer('import',[source],temporary,lambda *args:None)
            connection.assert_not_called()

    def test_each_supported_format_completes_a_replayed_import(self):
        for name in ['sample.mp3','sample.m4a','covered-aac.m4a','sample.wav','sample.aiff']:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                phone=Phone()
                result=self.call(phone,'import',[self.selected(name)],temporary)
                self.assertEqual(result['imported'],1)
                self.assertEqual(len(self.tracks(phone,temporary)),2)

    def test_reimport_of_an_intact_completed_tupaq_transfer_is_skipped(self):
        phone=Phone()
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(self.call(phone,'import',[self.selected()],temporary)['imported'],1)
            before=len(phone.sent)
            result=self.call(phone,'import',[self.selected()],temporary)
            self.assertEqual(result['imported'],0)
            self.assertEqual(result['already_imported'],1)
            self.assertEqual(len(phone.sent),before)
            self.assertEqual(len(self.tracks(phone,temporary)),2)

    def test_unconfigured_identity_stops_before_metadata_and_keeps_no_pending_send(self):
        phone=Phone();prefs=bytearray(preferences());prefs[8]=0;phone.files[PREF+'iTunesPrefs']=bytes(prefs)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(TransferError) as caught:self.call(phone,'import',[self.selected()],temporary)
            self.assertIn('identity-not-configured',caught.exception.diagnostic)
            self.assertFalse(phone.sent)
            self.assertFalse(phone.writes)
            record=json.loads(next(Path(temporary).glob('*/journal.json')).read_text(encoding='utf-8'))
            self.assertEqual(record['phase'],'before-write-failed')

    def test_permanent_audio_corruption_is_not_reported_as_success(self):
        phone=Phone();phone.fail='tamper'
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(TransferError) as caught:self.call(phone,'import',[self.selected()],temporary)
            self.assertIn('verify-permanent-audio',caught.exception.diagnostic)
            journal=next(Path(temporary).glob('*/journal.json'))
            self.assertEqual(json.loads(journal.read_text(encoding='utf-8'))['phase'],'verifying')

    def test_verified_audio_after_lost_completion_unblocks_the_next_import(self):
        phone=Phone();phone.fail='lost-finished'
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(TransferError):self.call(phone,'import',[self.selected()],temporary)
            previous=len(phone.sent)
            phone.fail=None
            result=self.call(phone,'import',[self.selected('aac.m4a')],temporary)
            self.assertEqual(result['imported'],1)
            self.assertEqual(result['reconciled'],1)
            records=[json.loads(path.read_text()) for path in Path(temporary).glob('*/journal.json')]
            self.assertEqual(sum(r['phase']=='observed-present' for r in records),1)
            self.assertGreater(len(phone.sent),previous)

    def test_unrequested_m4p_format_is_excluded_without_touching_its_audio(self):
        from importios.library_fields import local_tracks
        phone=Phone()
        with closing(sqlite3.connect(':memory:')) as db:
            db.deserialize(phone.files[PREF+'MediaLibrary.sqlitedb'])
            db.execute("UPDATE item_extra SET location='AAAA.m4p'")
            db.commit();phone.files[PREF+'MediaLibrary.sqlitedb']=db.serialize()
        path='/iTunes_Control/Music/F00/AAAA.m4p'
        phone.files[path]=b'protected-original-test-data'
        before=dict(phone.files)
        with tempfile.TemporaryDirectory() as temporary:
            track=self.tracks(phone,temporary)[0]
            self.assertEqual(local_tracks([track]),[])
            with self.assertRaises(TransferError) as caught:self.call(phone,'export',[track],temporary)
            self.assertIn('export-format',caught.exception.diagnostic)
            self.assertEqual(phone.files,before)
            self.assertFalse(phone.writes)
            self.assertFalse(list(Path(temporary).glob('*.m4p')))

    def test_private_identities_parse_without_accepting_unconfigured_preferences(self):
        self.assertEqual(library_identity(preferences()),(0x1234,0xab))
        value=bytearray(preferences());value[8]=0
        with self.assertRaises(ProtocolError):library_identity(bytes(value))
        self.assertEqual(saved_anchors(host_database()),{'database':11,'media':7,'voice':1})

    def test_host_catalogue_variants_retain_section_and_live_identity_checks(self):
        for header,minor in [(208,105),(244,116),(324,118)]:
            with self.subTest(header=header,minor=minor):
                original=host_database()
                data=bytearray(header)+original[244:]
                data[:min(header,244)]=original[:min(header,244)]
                struct.pack_into('<I',data,4,header)
                struct.pack_into('<I',data,8,len(data))
                struct.pack_into('<I',data,16,minor)
                self.assertEqual(saved_anchors(data),{'database':11,'media':7,'voice':1})
        original=host_database()
        for declared in (244+144,244+len(zlib.compress(original[244:]))):
            data=bytearray(original[:244])+zlib.compress(original[244:])
            struct.pack_into('<I',data,8,declared)
            struct.pack_into('<I',data,12,2);data[168]=1
            self.assertEqual(saved_anchors(data)['voice'],1)

    def test_host_catalogue_failure_reports_only_public_header_numbers(self):
        data=bytearray(host_database());struct.pack_into('<I',data,4,9000)
        with self.assertRaises(ProtocolError) as caught:saved_anchors(data)
        from importios.transfers import transfer_error
        report=transfer_error(caught.exception,'import').diagnostic
        self.assertIn('9000',report)
        self.assertNotIn('database',report)
        for offset,value in [(8,1),(20,0)]:
            data=bytearray(host_database());struct.pack_into('<I',data,offset,value)
            with self.assertRaises(ProtocolError):saved_anchors(data)
        data=bytearray(host_database());struct.pack_into('<I',data,244+8,9999)
        with self.assertRaises(ProtocolError):saved_anchors(data)

    def test_phone_path_validation_never_allows_traversal(self):
        for base,leaf in [('../Music/F00','A.mp3'),('iTunes_Control/Music/F00','../A.mp3'),
                          ('iTunes_Control/Music/F00','/A.mp3'),('iTunes_Control/Music/F00','C:A.mp3')]:
            self.assertIsNone(media_path(base,leaf))
        self.assertEqual(media_path('Purchases','ABC.m4p'),'Purchases/ABC.m4p')
        self.assertEqual(media_path('Downloads/group_1','ABC.m4a'),'Downloads/group_1/ABC.m4a')


class FrameTests(unittest.IsolatedAsyncioTestCase):
    async def test_frame_limit_poisoning_and_real_little_endian_ping_reply(self):
        ping={'Session':2,'Command':'Ping'}
        reply={'Session':2,'Command':'SyncFinished'}
        def frame(value):
            raw=plistlib.dumps(value,fmt=plistlib.FMT_BINARY)
            return struct.pack('<I',len(raw))+raw
        class Stream:
            def __init__(self):self.data=frame(ping)+frame(reply);self.sent=[]
            async def recvall(self,n):
                if not self.data:await asyncio.Future()
                data,self.data=self.data[:n],self.data[n:];return data
            async def sendall(self,data):self.sent.append(data)
            async def close(self):pass
        stream=Stream()
        async with Atc(stream) as channel:
            self.assertEqual((await channel.receive())['Command'],'SyncFinished')
            self.assertEqual(plistlib.loads(stream.sent[0][4:]),{'Session':2,'Command':'Pong'})
            self.assertEqual(struct.unpack('<I',stream.sent[0][:4])[0],len(stream.sent[0])-4)
        stream=Stream();stream.data=struct.pack('<I',16*1024*1024+1)
        async with Atc(stream) as channel:
            with self.assertRaises(ProtocolError):await channel.receive()
            with self.assertRaises(ProtocolError):await channel.send({'Session':1,'Command':'Ping'})
