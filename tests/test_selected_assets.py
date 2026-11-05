"""Original selected artwork and embedded lyrics stay distinct from list thumbnails."""
import asyncio
from contextlib import closing
import io
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import unittest
from PySide6.QtCore import QBuffer,QIODevice,QEvent,Qt
from PySide6.QtGui import QImage
from mutagen.id3 import ID3,USLT,SYLT,APIC
from mutagen.mp4 import MP4,MP4Cover
from importios.artwork import image_info,preview_image,thumbnail,PREVIEW_BYTES
from importios.audio import inspect_audio
from importios.lyrics import descriptor,embedded_lyrics,catalogue_lyrics,state
from importios.remote_artwork import cover_for_track,original_path
from test_remote_artwork import AFC,AUDIO,RELATIVE,FIXTURES
from test_native_connection import APP,TRACK
from importios.native import Window
from importios.models import LYRICS_ROLE,LibraryModel


def cover(width=2400,height=1600):
    image=QImage(width,height,QImage.Format.Format_RGB32);image.fill(0xff226688)
    buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly);image.save(buffer,'PNG')
    return bytes(buffer.data())


class SelectedAssetTests(unittest.TestCase):
    def test_original_dimensions_weight_and_aspect_are_not_thumbnail_values(self):
        data=cover();info=image_info(data)
        self.assertEqual((info['cover_width'],info['cover_height'],info['cover_bytes']),(2400,1600,len(data)))
        self.assertEqual(info['cover_format'],'PNG')
        self.assertLessEqual(preview_image(data).width(),1024)
        self.assertAlmostEqual(preview_image(data).width()/preview_image(data).height(),1.5,places=2)
        self.assertEqual(preview_image(data,original=True).width(),2400)
        self.assertEqual(QImage.fromData(thumbnail(data)).width(),96)
        self.assertIsNone(image_info(b'x'*(PREVIEW_BYTES+1)))
        self.assertIsNone(preview_image(b'broken'))

    def test_id3_plain_and_timed_lyrics_and_bounded_plaintext(self):
        tags=ID3();tags.add(USLT(encoding=3,lang='spa',text='Primera línea\nSegunda línea'))
        self.assertTrue(descriptor(tags)['lyrics_embedded']);self.assertNotIn('lyrics_text',descriptor(tags))
        self.assertEqual(embedded_lyrics(tags)['lyrics_text'],'Primera línea\nSegunda línea')
        tags.delall('USLT');tags.add(SYLT(encoding=3,lang='eng',format=2,type=1,text=[('First\n',1),('Second',2000)]))
        self.assertEqual(embedded_lyrics(tags)['lyrics_kind'],'timed')
        self.assertEqual(embedded_lyrics(tags)['lyrics_text'],'First\nSecond')
        long=embedded_lyrics({'\xa9lyr':['x'*(256*1024+1)]})
        self.assertTrue(long['lyrics_embedded']);self.assertIsNone(long['lyrics_text'])
        self.assertFalse(embedded_lyrics({'\xa9lyr':[' \n']})['lyrics_embedded'])

    def test_catalogue_distinguishes_text_online_flag_and_unknown_schema(self):
        with closing(sqlite3.connect(':memory:')) as db:
            self.assertIsNone(catalogue_lyrics(db))
            db.execute('CREATE TABLE lyrics(item_pid,lyrics,store_lyrics_available)')
            db.executemany('INSERT INTO lyrics VALUES(?,?,?)',[(1,'Words',0),(2,'',1),(3,'',0)])
            rows=catalogue_lyrics(db)
            self.assertEqual(state(rows['1']),'registered');self.assertEqual(state(rows['2']),'online');self.assertIsNone(state(rows['3']))
            self.assertNotIn('lyrics_text',rows['1'])

    def test_checksum_research_is_bounded_and_never_exposes_text_or_values(self):
        import zlib,json
        from importios.lyrics import checksum_probe
        with closing(sqlite3.connect(':memory:')) as db:
            self.assertFalse(checksum_probe(db)['schema_available'])
            db.execute('CREATE TABLE lyrics(checksum,lyrics)')
            text='Privado: versos de prueba'
            checksum=zlib.crc32(text.encode('utf-8'))
            db.executemany('INSERT INTO lyrics VALUES(?,?)',[(checksum,text)]*40)
            result=checksum_probe(db)
            self.assertEqual(result['samples_checked'],32);self.assertTrue(result['more_samples_available'])
            self.assertEqual(result['algorithm_matches']['crc32_utf8'],32)
            self.assertEqual(result['algorithm_matches']['crc32_utf16be'],0)
            self.assertFalse(result['usb_contract_verified'])
            self.assertNotIn(text,json.dumps(result));self.assertNotIn(str(checksum),json.dumps(result))
            db.execute('DELETE FROM lyrics');db.executemany('INSERT INTO lyrics VALUES(?,?)',[(0,text),(123,' '),(2**50,text),(123,'x'*65537)])
            self.assertEqual(checksum_probe(db)['samples_checked'],0)
            db.execute("INSERT INTO lyrics VALUES(123,CAST(x'ff' AS TEXT))")
            self.assertTrue(checksum_probe(db)['probe_unavailable'])

    def test_remote_original_prefers_larger_embedded_cover_and_reads_lyrics(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'test.m4a';shutil.copyfile(FIXTURES/'covered-aac.m4a',path)
            audio=MP4(path);data=cover();audio['covr']=[MP4Cover(data,imageformat=MP4Cover.FORMAT_PNG)];audio['\xa9lyr']=['Verso uno\nVerso dos'];audio.save()
            before=path.read_bytes();cached=original_path(RELATIVE)
            afc=AFC({AUDIO:before,cached:cover(512,512)})
            result=asyncio.run(cover_for_track(afc,{'afc_path':AUDIO,'artwork_paths':[cached]},assets=True))
            self.assertEqual(result['cover'],data);self.assertEqual(result['cover_width'],2400);self.assertEqual(result['cover_source'],'embedded')
            self.assertEqual(result['lyrics_text'],'Verso uno\nVerso dos');self.assertTrue(result['lyrics_embedded'])
            self.assertEqual(path.read_bytes(),before);self.assertFalse(afc.handles)
            self.assertTrue(inspect_audio(path,path.name)['lyrics_embedded'])
            self.assertNotIn('lyrics_text',inspect_audio(path,path.name))
            small=asyncio.run(cover_for_track(AFC({AUDIO:before}),{'afc_path':AUDIO}))
            self.assertLessEqual(QImage.fromData(small).width(),96)

    def test_remote_id3_and_wave_read_lyrics_without_cover(self):
        for filename in ('sample.mp3','sample.wav','sample.aiff'):
            with self.subTest(filename=filename),tempfile.TemporaryDirectory() as temporary:
                import mutagen
                path=Path(temporary)/filename;shutil.copyfile(FIXTURES/filename,path)
                audio=mutagen.File(path)
                if audio.tags is None:audio.add_tags()
                audio.tags.add(USLT(encoding=3,lang='spa',text='Letra de prueba'));audio.save()
                afc=AFC({AUDIO:path.read_bytes()})
                result=asyncio.run(cover_for_track(afc,{'afc_path':AUDIO},assets=True))
                self.assertTrue(result['lyrics_embedded']);self.assertEqual(result['lyrics_text'],'Letra de prueba');self.assertFalse(afc.handles)

    def test_lyrics_icon_role_does_not_imply_native_registration(self):
        model=LibraryModel();model.replace([dict(TRACK,lyrics_embedded=True)])
        self.assertEqual(model.data(model.index(0,0),LYRICS_ROLE),'embedded')
        self.assertIn('no verificado',model.data(model.index(0,0),Qt.ItemDataRole.ToolTipRole))
        model.set_details('1',{'lyrics_registered':True})
        self.assertEqual(model.data(model.index(0,0),LYRICS_ROLE),'registered')

    def test_selected_local_preview_is_full_source_and_stale_result_is_ignored(self):
        w=Window(auto_connect=False);w.show()
        try:
            self.assertFalse(hasattr(w,'album_shortcuts'))
            with tempfile.TemporaryDirectory() as temporary:
                path=Path(temporary)/'test.m4a';shutil.copyfile(FIXTURES/'covered-aac.m4a',path)
                audio=MP4(path);data=cover();audio['covr']=[MP4Cover(data,imageformat=MP4Cover.FORMAT_PNG)];audio['\xa9lyr']=['Prueba'];audio.save()
                track=inspect_audio(path,path.name);track['path']=str(path)
                w.show_track_details(track,'Para importar')
                deadline=time.monotonic()+8
                while time.monotonic()<deadline and (w.preview_pending is not None or w.thumbnail_worker is not None):APP.processEvents();time.sleep(.005)
                self.assertIsNone(w.thumbnail_worker);self.assertIsNone(w.preview_pending)
                self.assertEqual(w.preview_result['cover'],data)
                self.assertIn('2400 × 1600 px',w.cover_metadata.text());self.assertTrue(w.view_cover.isEnabled());self.assertTrue(w.view_lyrics.isEnabled())
                w.clear_inspector();w.preview_ready(w.preview_generation-1,{'cover':b'stale'})
                self.assertFalse(w.preview_result);self.assertFalse(w.view_lyrics.isEnabled())
        finally:
            w.tracks.clear();w.close();w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()
