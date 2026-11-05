"""Optional track/disc tags must not reject otherwise supported audio."""
import hashlib
import json
import plistlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mutagen import File as AudioFile
from mutagen.id3 import TIT2,TRCK,TPOS
from mutagen.mp4 import MP4
from importios.sync.source import inspect_source
from importios.sync.protocol import encode_operations
from importios.transfers import run_transfer,PREF
from importios.library import read_catalogue
from test_deletion import Phone

FIXTURES=Path(__file__).parent/'fixtures'
FORMATS=('sample.mp3','sample.wav','sample.aiff','sample.m4a','covered-aac.m4a')


def tagged(folder,name,track,disc,title='Numbering'):
    path=Path(folder)/name;path.write_bytes((FIXTURES/name).read_bytes());audio=AudioFile(path)
    if audio.tags is None:audio.add_tags()
    if isinstance(audio,MP4):
        audio['trkn']=[track];audio['disk']=[disc];audio['\xa9nam']=[title]
    else:
        audio.tags.add(TRCK(encoding=3,text=f'{track[0]}/{track[1]}'))
        audio.tags.add(TPOS(encoding=3,text=f'{disc[0]}/{disc[1]}'))
        audio.tags.add(TIT2(encoding=3,text=title))
    audio.save();return path


class SourceNumberingTests(unittest.TestCase):
    def test_all_formats_keep_valid_numbers_and_omit_incoherent_totals(self):
        cases=[((0,12),{}),((9,3),{'number':9}),((8,0),{'number':8}),
               ((3,12),{'number':3,'count':12}),((0,0),{}),
               ((65535,65535),{'number':65535,'count':65535})]
        with tempfile.TemporaryDirectory() as root:
            for name in FORMATS:
                for pair,expected in cases:
                    with self.subTest(name=name,pair=pair):
                        path=tagged(root,name,pair,pair);original=path.read_bytes()
                        source=inspect_source(path)
                        for prefix in ('track','disc'):
                            actual={k:source[prefix+'_'+k] for k in ('number','count') if prefix+'_'+k in source}
                            self.assertEqual(actual,expected)
                        wire=plistlib.loads(encode_operations(1,2,3,[{'track_id':4,'album_id':5,'artist_id':6,'source':source}]))['operations'][1]['item']
                        for prefix in ('track','disc'):
                            self.assertEqual({k:wire[prefix+'_'+k] for k in ('number','count') if prefix+'_'+k in wire},expected)
                        self.assertEqual(path.read_bytes(),original)
                        self.assertEqual(source['id'],hashlib.sha256(original).hexdigest())

    def test_id3_whitespace_leading_zeroes_and_invalid_optional_values(self):
        cases=[(' 003 / 012 ',{'track_number':3,'track_count':12}),
               ('٠٣/٠١٢',{'track_number':3,'track_count':12}),
               ('/12',{}),('unknown/12',{}),('65536/65536',{}),
               ('3/unknown',{'track_number':3}),('65535/65536',{'track_number':65535}),('²/12',{}),
               ('-1/12',{}),('3/2',{'track_number':3})]
        with tempfile.TemporaryDirectory() as root:
            path=tagged(root,'sample.mp3',(1,1),(0,0))
            for value,expected in cases:
                with self.subTest(value=value):
                    audio=AudioFile(path);audio.tags.add(TRCK(encoding=3,text=value));audio.save()
                    source=inspect_source(path)
                    self.assertEqual({k:v for k,v in source.items() if k.startswith('track_')},expected)

    def test_missing_optional_numbering_is_not_invented(self):
        for name in FORMATS:
            with self.subTest(name=name):
                source=inspect_source(FIXTURES/name)
                self.assertFalse(any(k in source for k in ('track_number','track_count','disc_number','disc_count')))

    def test_mixed_numbering_imports_across_batches_without_rewriting_audio(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);selected=[];phone=Phone();original=phone.files['/iTunes_Control/Music/F00/AAAA.mp3']
            for n in range(51):
                folder=root/str(n);folder.mkdir()
                path=tagged(folder,FORMATS[n%5],(0,12) if n%2 else (9,3),(0,2),f'Numbering {n}')
                selected.append({'path':str(path),'id':hashlib.sha256(path.read_bytes()).hexdigest()})
            with patch('importios.transfers.device',phone.device),patch('importios.transfers.Atc',lambda peer:peer):
                result=run_transfer('import',selected,root/'backups',lambda *a:None)
            self.assertFalse(result.get('bulk_stopped'));self.assertEqual(result['imported'],51)
            self.assertEqual(result['batches_completed'],2)
            for batch in json.loads(Path(result['bulk_journal']).read_text())['completed_batches']:
                receipt=json.loads((Path(batch['backup'])/'journal.json').read_text())
                for entry in receipt['entries']:
                    self.assertEqual(hashlib.sha256(phone.files['/'+entry['destination']]).hexdigest(),entry['source']['id'])
                    self.assertEqual(Path(entry['source']['path']).read_bytes(),phone.files['/'+entry['destination']])
            database=root/'catalogue.sqlite';database.write_bytes(phone.files[PREF+'MediaLibrary.sqlitedb'])
            self.assertEqual(len(read_catalogue(database)),52)
            self.assertEqual(phone.files['/iTunes_Control/Music/F00/AAAA.mp3'],original)
            self.assertFalse(phone.handles)
