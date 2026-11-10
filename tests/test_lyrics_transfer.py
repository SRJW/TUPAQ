"""Replay native part-8 delivery; these are not physical iPhone UI tests."""
from contextlib import closing
import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

import mutagen
from mutagen.id3 import ID3,USLT,SYLT

from importios.sync.lyrics import host_checksum,MAX_TEXT_BYTES
from importios.sync.protocol import validate_manifest,ProtocolError
from importios.transfers import run_transfer,TransferError
from test_transfers import Phone,FIXTURES,PREF,MEDIA
from test_recovery import PendingPhone


class LyricsTransferTests(unittest.TestCase):
    def source(self,folder,text='Primera línea\r\n🎵 café\nÚltima línea',name='sample.mp3'):
        path=Path(folder)/name;path.write_bytes((FIXTURES/name).read_bytes())
        if name.endswith('.m4a'):
            audio=mutagen.File(path);audio.tags['\xa9lyr']=[text];audio.save()
        else:
            tags=ID3(path);tags.add(USLT(encoding=3,lang='spa',text=text));tags.save(path)
        return {'path':str(path),'id':hashlib.sha256(path.read_bytes()).hexdigest()}

    def call(self,phone,mode,selected,root):
        with patch('importios.transfers.device',phone.device),patch('importios.transfers.Atc',lambda peer:peer):
            return run_transfer(mode,selected,root,lambda *args:None)

    def rows(self,phone):
        with closing(sqlite3.connect(':memory:')) as db:
            db.deserialize(phone.files[PREF+'MediaLibrary.sqlitedb'])
            return db.execute('SELECT checksum,lyrics FROM lyrics ORDER BY item_pid').fetchall()

    def test_exact_utf8_and_checksum_with_and_without_cover_originals_unchanged(self):
        text='Primera línea\r\n🎵 café\nÚltima línea'
        for name,mask in [('sample.mp3',9),('covered-aac.m4a',11),('sample.m4a',9)]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as folder:
                phone=Phone();selected=self.source(folder,text,name);original=Path(selected['path']).read_bytes()
                written=[];old=phone.fwrite
                async def write(handle,data):
                    if '/Lyrics/' in phone.handles[handle][0]:written.append(data)
                    await old(handle,data)
                phone.fwrite=write
                result=self.call(phone,'import',[selected],Path(folder)/'backups')
                self.assertEqual(result['imported'],1);self.assertEqual(Path(selected['path']).read_bytes(),original)
                self.assertEqual(b''.join(written),text.encode('utf-8'))
                self.assertEqual(self.rows(phone),[(host_checksum(text),text)])
                journal=(Path(result['backup'])/'journal.json').read_text(encoding='utf-8')
                self.assertNotIn(text,json.dumps(json.loads(journal),ensure_ascii=False))
                self.assertNotIn('lyrics_text',journal)
                record=json.loads(journal);self.assertEqual(record['phase'],'completed');self.assertIn(mask,record['manifest_parts'])
                entry=record['entries'][0];identifier=str(entry['track_id'])
                self.assertLess(phone.writes.index('/Airlock/Media/Lyrics/'+identifier),
                                phone.writes.index('/Airlock/Media/'+identifier+entry['source']['extension']))
                completions=[m for m in phone.sent if m['Command']=='FileComplete']
                self.assertEqual(len(completions),1);self.assertEqual(completions[0]['Params']['AssetPath'],entry['destination'])

    def test_disable_lyrics_keeps_embedded_tags_but_omits_native_declaration(self):
        with tempfile.TemporaryDirectory() as folder:
            phone=Phone();selected=self.source(folder);selected['send_lyrics']=False
            result=self.call(phone,'import',[selected],Path(folder)/'backups')
            self.assertEqual(result['imported'],1);self.assertNotIn('lyrics',phone.operations[0]['item'])
            self.assertFalse(self.rows(phone));self.assertFalse(any('/Lyrics/' in p for p in phone.writes))

    def test_missing_text_changed_text_or_checksum_never_claim_verified(self):
        for failure in ('ignore-lyrics','tamper-lyrics','tamper-lyrics-checksum'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as folder:
                phone=Phone();phone.fail=failure;selected=self.source(folder)
                root=Path(folder)/'backups'
                with self.assertRaises(TransferError) as caught:self.call(phone,'import',[selected],root)
                self.assertIn('verify-lyrics-registration',caught.exception.diagnostic)
                record=json.loads(next(root.glob('*/journal.json')).read_text(encoding='utf-8'))
                self.assertNotEqual(record['phase'],'completed')
                self.assertTrue(phone.files['/'+record['entries'][0]['destination']])

    def test_oversized_lyrics_or_unknown_schema_stop_before_metadata(self):
        for failure in ('oversized','schema'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as folder:
                phone=Phone();selected=self.source(folder,'x'*(MAX_TEXT_BYTES+1) if failure=='oversized' else 'Letra')
                if failure=='schema':
                    with closing(sqlite3.connect(':memory:')) as db:
                        db.deserialize(phone.files[PREF+'MediaLibrary.sqlitedb']);db.execute('DROP TABLE lyrics')
                        db.commit();phone.files[PREF+'MediaLibrary.sqlitedb']=db.serialize()
                with self.assertRaises(TransferError) as caught:self.call(phone,'import',[selected],Path(folder)/'backups')
                self.assertIn('lyrics-source-size' if failure=='oversized' else 'lyrics-catalogue-schema',caught.exception.diagnostic)
                self.assertFalse(phone.operations);self.assertFalse(any(m['Command']=='FinishedSyncingMetadata' for m in phone.sent))

    def test_pending_native_lyrics_resume_same_id_and_preserve_existing_lyrics(self):
        with tempfile.TemporaryDirectory() as folder:
            phone=PendingPhone();selected=self.source(folder);root=Path(folder)/'backups'
            phone.modify("INSERT INTO lyrics VALUES(1,123,'Letra original sin tocar');")
            with patch('importios.transfers.validate_manifest',side_effect=ProtocolError('manifest-own-parts')):
                with self.assertRaises(TransferError):self.call(phone,'import',[selected],root)
            journal=next(root.glob('*/journal.json'));record=json.loads(journal.read_text(encoding='utf-8'))
            identifier=str(record['entries'][0]['track_id']);phone.sent.clear();phone.writes.clear()
            result=self.call(phone,'resume',[],root)
            self.assertEqual(result['verified'],1)
            self.assertEqual(self.rows(phone)[0],(123,'Letra original sin tocar'))
            self.assertEqual(len(self.rows(phone)),2)
            self.assertEqual(next(m for m in phone.sent if m['Command']=='FileComplete')['Params']['AssetID'],identifier)
            self.assertFalse(any(p.startswith(MEDIA) for p in phone.writes))

    def test_corrupt_staged_lyrics_stop_before_filecomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            phone=PendingPhone();selected=self.source(folder);old=phone.fwrite
            async def corrupt(handle,data):
                await old(handle,data+b'wrong' if '/Lyrics/' in phone.handles[handle][0] else data)
            phone.fwrite=corrupt
            with self.assertRaises(TransferError):self.call(phone,'import',[selected],Path(folder)/'backups')
            self.assertFalse(any(m['Command']=='FileComplete' for m in phone.sent))

    def test_manifest_part8_allowed_only_for_declared_own_payload(self):
        for declared in (9,11):
            for requested in (declared,declared|4):
                message={'Session':2,'Params':{'AssetManifest':{'Media':[
                    {'AssetType':'Music','IsDownload':True,'AssetID':'100','Variant':{'AssetParts':requested}}]}}}
                self.assertEqual(validate_manifest(message,{'100'},set(),{'100':declared}),(['100'],[]))
                with self.assertRaises(ProtocolError):validate_manifest(message,{'100'},set(),{'100':1})
        for invalid in (0,1,2,3,8,10,16,255):
            message={'Session':2,'Params':{'AssetManifest':{'Media':[
                {'AssetType':'Music','IsDownload':True,'AssetID':'100','Variant':{'AssetParts':invalid}}]}}}
            with self.assertRaises(ProtocolError):validate_manifest(message,{'100'},set(),{'100':9})

    def test_already_imported_lyrics_song_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as folder:
            phone=Phone();selected=self.source(folder);root=Path(folder)/'backups'
            self.call(phone,'import',[selected],root);phone.sent.clear();phone.writes.clear()
            result=self.call(phone,'import',[selected],root)
            self.assertEqual((result['imported'],result['already_imported']),(0,1))
            self.assertFalse(phone.sent);self.assertFalse(phone.writes);self.assertEqual(len(self.rows(phone)),1)

    def test_sylt_timestamps_in_original_are_preserved_without_claiming_native_karaoke(self):
        with tempfile.TemporaryDirectory() as folder:
            phone=Phone();selected=self.source(folder)
            tags=ID3(selected['path']);tags.delall('USLT')
            tags.add(SYLT(encoding=3,lang='spa',format=2,type=1,text=[('Hola ',1000),('mundo',2300)]));tags.save(selected['path'])
            original=Path(selected['path']).read_bytes();selected['id']=hashlib.sha256(original).hexdigest()
            result=self.call(phone,'import',[selected],Path(folder)/'backups')
            self.assertEqual(Path(selected['path']).read_bytes(),original)
            self.assertEqual(ID3(selected['path']).getall('SYLT')[0].text,[('Hola ',1000),('mundo',2300)])
            self.assertEqual(self.rows(phone),[(host_checksum('Hola mundo'),'Hola mundo')])
            record=json.loads((Path(result['backup'])/'journal.json').read_text(encoding='utf-8'))
            self.assertEqual(record['entries'][0]['lyrics']['kind'],'plain')
            self.assertEqual(record['entries'][0]['lyrics']['source_kind'],'timed')
            self.assertFalse(result.get('karaoke_verified',False))
