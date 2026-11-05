"""Equivalent Unicode is accepted; actual metadata and audio changes are not."""
from contextlib import closing
from pathlib import Path
import json
import shutil
import sqlite3
import tempfile
import unicodedata
import unittest
from unittest.mock import patch
from mutagen.mp3 import MP3
from mutagen.id3 import TIT2,TPE1,TALB
import test_transfers as support
from importios.sync.protocol import ProtocolError
from importios.transfers import TransferError


class NormalizingPhone(support.Phone):
    normalization='NFC'
    change=None
    def apply(self,operation,destination,audio):
        super().apply(operation,destination,audio)
        with closing(sqlite3.connect(':memory:')) as db:
            db.deserialize(self.files[support.PREF+'MediaLibrary.sqlitedb'])
            pid,artist,album=db.execute('''SELECT i.item_pid,i.item_artist_pid,i.album_pid
                FROM item i JOIN item_store s ON s.item_pid=i.item_pid WHERE s.sync_id=?''',(operation['pid'],)).fetchone()
            values={key:unicodedata.normalize(self.normalization,operation['item'][key]) for key in ('title','artist','album')}
            if self.change:values[self.change[0]]=self.change[1]
            db.execute('UPDATE item_extra SET title=? WHERE item_pid=?',(values['title'],pid))
            db.execute('UPDATE item_artist SET item_artist=? WHERE item_artist_pid=?',(values['artist'],artist))
            db.execute('UPDATE album SET album=? WHERE album_pid=?',(values['album'],album))
            db.commit();self.files[support.PREF+'MediaLibrary.sqlitedb']=db.serialize()


class MetadataVerificationTests(unittest.TestCase):
    call=support.TransferTests.call
    def source(self,root,form='NFD'):
        path=Path(root)/'song.mp3';shutil.copyfile(support.FIXTURES/'sample.mp3',path)
        audio=MP3(path)
        if audio.tags is None:audio.add_tags()
        for cls,key,text in ((TIT2,'TIT2','Canción única'),(TPE1,'TPE1','Artísta'),(TALB,'TALB','Álbum')):
            audio.tags.setall(key,[cls(encoding=3,text=[unicodedata.normalize(form,text)])])
        audio.save()
        return {'path':str(path)}

    def test_equivalent_unicode_in_both_directions_is_verified(self):
        for source_form,phone_form in (('NFD','NFC'),('NFC','NFD')):
            with self.subTest(source=source_form),tempfile.TemporaryDirectory() as root:
                phone=NormalizingPhone();phone.normalization=phone_form
                source=self.source(root,source_form)
                result=self.call(phone,'import',[source],Path(root)/'backups')
                self.assertEqual(result['imported'],1)
                record=json.loads((Path(result['backup'])/'journal.json').read_text(encoding='utf-8'))
                self.assertEqual(record['phase'],'completed')
                self.assertEqual(record['entries'][0]['source']['title'],unicodedata.normalize(source_form,'Canción única'))

    def test_meaningful_metadata_changes_still_fail_with_private_field_only_diagnostics(self):
        for field,value in (('title','Canción distinta'),('artist','ARTÍSTA'),('album','Álbum '),('title','Cancion única')):
            with self.subTest(field=field,value=value),tempfile.TemporaryDirectory() as root:
                phone=NormalizingPhone();phone.change=(field,value)
                source=self.source(root)
                with self.assertRaises(TransferError) as caught:self.call(phone,'import',[source],Path(root)/'backups')
                self.assertIn('verify-new-metadata',caught.exception.diagnostic)
                self.assertIn('"metadata_fields": ["'+field+'"]',caught.exception.diagnostic)
                self.assertNotIn(value,caught.exception.diagnostic)
                self.assertNotIn('Canción única',caught.exception.diagnostic)
                record=json.loads(next((Path(root)/'backups').glob('*/journal.json')).read_text(encoding='utf-8'))
                self.assertEqual(record['phase'],'verifying')
                folder=next((Path(root)/'backups').glob('*/journal.json')).parent
                self.assertEqual(len(list(folder.glob('after*'))),3)
                self.assertNotIn('verified_catalogue',record)

    def test_previous_false_mismatch_can_be_checked_without_resending_or_duplicating(self):
        with tempfile.TemporaryDirectory() as root:
            phone=NormalizingPhone();source=self.source(root);backups=Path(root)/'backups'
            with patch('importios.transfers.verify_before_after',side_effect=ProtocolError('verify-new-metadata')):
                with self.assertRaises(TransferError):self.call(phone,'import',[source],backups)
            writes=len(phone.writes);sent=len(phone.sent)
            result=self.call(phone,'verify',[],backups)
            self.assertEqual(result['verified'],1);self.assertEqual(result['metadata_unverified'],0)
            result=self.call(phone,'import',[source],backups)
            self.assertEqual(result['imported'],0);self.assertEqual(result['already_imported'],1)
            self.assertEqual(len(phone.writes),writes);self.assertEqual(len(phone.sent),sent)

    def test_canonical_metadata_does_not_hide_audio_corruption(self):
        with tempfile.TemporaryDirectory() as root:
            phone=NormalizingPhone();phone.fail='tamper';source=self.source(root)
            with self.assertRaises(TransferError) as caught:self.call(phone,'import',[source],Path(root)/'backups')
            self.assertIn('verify-permanent-audio',caught.exception.diagnostic)

    def test_late_metadata_is_reread_without_resending_the_import(self):
        from importios.transfers import capture
        with tempfile.TemporaryDirectory() as root:
            phone=NormalizingPhone();source=self.source(root);observations=[]
            async def delayed(afc,folder):
                if folder.name=='after' or folder.name.startswith('after-metadata-recheck-'):
                    observations.append(folder.name)
                    title='Pending' if folder.name=='after' else 'Canción única'
                    with closing(sqlite3.connect(':memory:')) as db:
                        db.deserialize(phone.files[support.PREF+'MediaLibrary.sqlitedb'])
                        db.execute('UPDATE item_extra SET title=? WHERE item_pid=(SELECT MAX(item_pid) FROM item)',(title,))
                        db.commit();phone.files[support.PREF+'MediaLibrary.sqlitedb']=db.serialize()
                return await capture(afc,folder)
            with patch('importios.transfers.capture',side_effect=delayed):
                result=self.call(phone,'import',[source],Path(root)/'backups')
            self.assertEqual(result['imported'],1)
            self.assertEqual(observations,['after','after-metadata-recheck-1'])
            self.assertEqual(sum(m['Command']=='RequestingSync' for m in phone.sent),1)
            self.assertEqual(sum(m['Command']=='FileComplete' for m in phone.sent),1)
            record=json.loads((Path(result['backup'])/'journal.json').read_text(encoding='utf-8'))
            self.assertEqual(record['verified_catalogue'],'after-metadata-recheck-1/1/MediaLibrary.sqlitedb')
            self.assertTrue((Path(result['backup'])/'after/1/MediaLibrary.sqlitedb').is_file())

    def test_other_verification_failures_do_not_retry(self):
        from importios.transfers import capture
        with tempfile.TemporaryDirectory() as root:
            phone=NormalizingPhone();source=self.source(root);observations=[]
            async def changed(afc,folder):
                result=await capture(afc,folder)
                if folder.name=='after':result['anchor']+=1;observations.append(folder.name)
                elif folder.name.startswith('after-metadata-recheck-'):observations.append(folder.name)
                return result
            with patch('importios.transfers.capture',side_effect=changed):
                with self.assertRaises(TransferError) as caught:self.call(phone,'import',[source],Path(root)/'backups')
            self.assertIn('verify-anchor',caught.exception.diagnostic)
            self.assertEqual(observations,['after'])

    def test_read_only_review_names_persistent_differences_and_can_recheck_them(self):
        with tempfile.TemporaryDirectory() as root:
            phone=NormalizingPhone();phone.change=('title','Wrong title');source=self.source(root);backups=Path(root)/'backups'
            with self.assertRaises(TransferError):self.call(phone,'import',[source],backups)
            writes=len(phone.writes);sent=len(phone.sent)
            for _ in range(2):
                result=self.call(phone,'verify',[],backups)
                self.assertEqual(result['metadata_unverified'],1)
                self.assertEqual(result['metadata_diagnostics'],[{'code':'verify-new-metadata','entry_index':1,'metadata_fields':['title']}])
            self.assertEqual(len(phone.writes),writes);self.assertEqual(len(phone.sent),sent)
