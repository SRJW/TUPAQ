"""Host-derived checksum vectors and privacy of the optional read-only probe."""
from contextlib import closing
import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from importios.sync.lyrics import host_checksum,MAX_TEXT_BYTES
from importios.lyrics import checksum_probe
from importios.transfers import run_transfer
from importios.audio import inspect_audio
from test_transfers import Phone,FIXTURES
from mutagen.id3 import ID3,USLT


class LyricsChecksumTests(unittest.TestCase):
    def test_exact_host_model_vectors_include_accents_non_bmp_and_whitespace(self):
        for text,value in [('',0),('a',0xcbc4ca42),('Letra de prueba',0x44e236d3),
            ('Primera línea\nSegunda línea',0x8d3a162e),('A\r\nB',0x712e7391),('🎵 café',0xbdc4a67d),(' ',0x17023eeb)]:
            with self.subTest(text=text):self.assertEqual(host_checksum(text),value)
        self.assertNotEqual(host_checksum('A\r\nB'),host_checksum('A\nB'))
        self.assertNotEqual(host_checksum('café'),host_checksum('cafe\u0301'))
        self.assertNotEqual(host_checksum('a'),host_checksum('a\0'))

    def test_zero_digest_fold_maps_nonempty_to_one_and_empty_stays_zero(self):
        with patch('importios.sync.lyrics.hashlib.md5',return_value=Mock(digest=lambda:bytes(16))):
            self.assertEqual(host_checksum('x'),1);self.assertEqual(host_checksum(''),0)

    def test_bounds_and_unicode_are_not_silently_replaced(self):
        with self.assertRaises(TypeError):host_checksum(b'words')
        with self.assertRaises(ValueError):host_checksum('x'*(MAX_TEXT_BYTES+1))
        with self.assertRaises(ValueError):host_checksum('🎵'*(MAX_TEXT_BYTES//4+1))
        with self.assertRaises(UnicodeError):host_checksum('\ud800')

    def test_signed_native_checksums_match_without_exposing_text_ids_or_values(self):
        with closing(sqlite3.connect(':memory:')) as db:
            db.execute('CREATE TABLE lyrics(item_pid,checksum,lyrics)')
            rows=[(123,0x44e236d3,'Letra de prueba'),(456,0x712e7391,'A\r\nB'),(789,0xbdc4a67d-2**32,'🎵 café')]
            db.executemany('INSERT INTO lyrics VALUES(?,?,?)',rows)
            result=checksum_probe(db)
            self.assertEqual(result['samples_checked'],3)
            self.assertEqual(result['algorithm_matches']['md5_fold_utf16be'],3)
            self.assertFalse(result['usb_contract_verified'])
            report=json.dumps(result,ensure_ascii=False)
            for identifier,checksum,text in rows:
                self.assertNotIn(text,report);self.assertNotIn(str(checksum),report);self.assertNotIn(str(identifier),report)

    def test_embedded_lyrics_keep_bytes_and_do_not_enable_unqualified_usb_parts(self):
        import hashlib
        phone=Phone()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'song.mp3';path.write_bytes((FIXTURES/'sample.mp3').read_bytes())
            tags=ID3(path);tags.add(USLT(encoding=3,lang='spa',text='Verso de prueba'));tags.save(path)
            before=path.read_bytes();track=inspect_audio(path,path.name);track.update(path=str(path),id=hashlib.sha256(before).hexdigest())
            self.assertTrue(track['lyrics_embedded'])
            with patch('importios.transfers.device',phone.device),patch('importios.transfers.Atc',lambda peer:peer):
                result=run_transfer('import',[track],Path(root)/'backups',lambda *a:None)
            self.assertEqual(result['imported'],1);self.assertEqual(path.read_bytes(),before)
            self.assertNotIn('lyrics',phone.operations[0]['item'])
            self.assertFalse(any('/Lyrics/' in value for value in phone.writes))
