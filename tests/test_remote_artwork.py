"""Read cover ranges from a fake AFC without copying or modifying audio."""
import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
import unittest

from PySide6.QtGui import QImage
from importios.audio import read_artwork
from importios.remote_artwork import cover_for_track, catalogue_artwork, original_path

FIXTURES = Path(__file__).parent/'fixtures'
AUDIO = 'iTunes_Control/Music/F00/AAAA.m4a'
RELATIVE = 'ab/'+'c'*38


class AFC:
    def __init__(self, files):
        self.files,self.handles,self.reads,self.opens = files,{},[],[]

    async def stat(self,path):
        return {'st_ifmt':'S_IFREG','st_size':len(self.files[path])}

    async def fopen(self,path,mode):
        assert mode == 'r'
        self.opens.append((path,mode))
        handle=len(self.opens);self.handles[handle]=[path,0]
        return handle

    async def fseek(self,handle,offset):
        self.handles[handle][1]=offset

    async def fread(self,handle,size):
        path,offset=self.handles[handle]
        block=self.files[path][offset:offset+min(size,123)]
        self.reads.append((path,offset,len(block)))
        self.handles[handle][1]+=len(block)
        return block

    async def fclose(self,handle):
        del self.handles[handle]


class RemoteArtworkTests(unittest.TestCase):
    def test_mp4_cover_reads_tags_and_skips_media_payload(self):
        data=(FIXTURES/'covered-aac.m4a').read_bytes()
        afc=AFC({AUDIO:data})
        image=QImage.fromData(asyncio.run(cover_for_track(afc,{'afc_path':AUDIO})))
        self.assertFalse(image.isNull())
        self.assertLessEqual(max(image.width(),image.height()),96)
        offset=0
        while offset+8<=len(data):
            size,kind=struct.unpack_from('>I4s',data,offset)
            if kind==b'mdat':
                self.assertFalse(any(start<offset+size and start+length>offset+8 for _,start,length in afc.reads))
            offset+=size
        self.assertFalse(afc.handles)
        self.assertEqual(afc.opens,[(AUDIO,'r')])

    def test_cached_original_preferred_and_invalid_paths_never_open(self):
        path=original_path(RELATIVE)
        afc=AFC({path:read_artwork(FIXTURES/'covered-aac.m4a')})
        result=asyncio.run(cover_for_track(afc,{'artwork_paths':['../private',path],'afc_path':AUDIO}))
        self.assertFalse(QImage.fromData(result).isNull())
        self.assertEqual(afc.opens,[(path,'r')])
        self.assertFalse(afc.handles)
        for relative in ['../secret','ab/'+'c'*39,'AB/'+'c'*38,'https://example.com']:
            self.assertIsNone(original_path(relative))

    def test_missing_corrupt_and_cancelled_covers_release_handles(self):
        for data in [b'bad',b'ID3\x04\x00\x00\x7f\x7f\x7f\x7f', (FIXTURES/'sample.mp3').read_bytes()]:
            afc=AFC({AUDIO:data})
            self.assertIsNone(asyncio.run(cover_for_track(afc,{'afc_path':AUDIO})))
            self.assertFalse(afc.handles)
            self.assertLess(sum(length for _,_,length in afc.reads),1024)
        afc=AFC({})
        self.assertIsNone(asyncio.run(cover_for_track(afc,{'afc_path':'../../secret'})))
        self.assertIsNone(asyncio.run(cover_for_track(afc,{'afc_path':AUDIO},lambda:True)))
        self.assertFalse(afc.opens)

    def test_catalogue_resolves_track_and_album_preferred_tokens(self):
        with closing(sqlite3.connect(':memory:')) as db:
            self.assertEqual(catalogue_artwork(db),{})
            db.executescript('''CREATE TABLE artwork_token(entity_pid,entity_type,artwork_token,artwork_source_type,artwork_variant_type);
                CREATE TABLE artwork(artwork_token,artwork_source_type,artwork_variant_type,relative_path);
                CREATE TABLE best_artwork_token(entity_pid,entity_type,available_artwork_token,artwork_variant_type);
                INSERT INTO artwork_token VALUES(1,0,'fallback',1,1),(2,4,'album',1,1),(3,0,'bad',1,1);
                INSERT INTO best_artwork_token VALUES(1,0,'best',1);''')
            for token,relative in [('fallback','aa/'+'b'*38),('best',RELATIVE),('album','cc/'+'d'*38),('bad','../../private')]:
                db.execute('INSERT INTO artwork VALUES(?,1,1,?)',(token,relative))
            found=catalogue_artwork(db)
            self.assertEqual(found[('1',0)],original_path(RELATIVE))
            self.assertEqual(found[('2',4)],original_path('cc/'+'d'*38))
            self.assertNotIn(('3',0),found)
