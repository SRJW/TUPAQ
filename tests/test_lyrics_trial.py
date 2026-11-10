"""The standalone experiment is local and preserves every byte of audio."""
from pathlib import Path
import tempfile,unittest,xml.etree.ElementTree as ET
from mutagen.mp4 import MP4
from scripts.lyrics_trial import create_trial,media_hash,ttml_from_lrc,NS

FIXTURES=Path(__file__).parent/'fixtures'


class LyricsTrialTests(unittest.TestCase):
    def source(self,root,text='[00:00.10] Prueba café & <texto>\n[00:00.50] Otra línea\n[00:00.90]'):
        source=Path(root)/'original.m4a';source.write_bytes((FIXTURES/'covered-aac.m4a').read_bytes())
        audio=MP4(source);audio.tags['\xa9lyr']=[text];audio.save()
        return source

    def test_local_copy_preserves_original_audio_cover_and_other_tags(self):
        with tempfile.TemporaryDirectory() as root:
            source=self.source(root);before=source.read_bytes();old=MP4(source);target=Path(root)/'trial.m4a'
            result=create_trial(source,target);copy=MP4(target)
            self.assertEqual(source.read_bytes(),before);self.assertEqual(media_hash(source),media_hash(target))
            self.assertEqual(result,{'lines':2,'audio_unchanged':True,'original_unchanged':True,'karaoke_verified':False})
            for key,value in old.tags.items():
                if key not in ('\xa9lyr','\xa9nam','\xa9alb'):self.assertEqual(copy.tags.get(key),value)
            self.assertIn('[Prueba TTML]',copy.tags['\xa9nam'][0]);self.assertIn('[Prueba TUPAQ]',copy.tags['\xa9alb'][0])
            tree=ET.fromstring(copy.tags['\xa9lyr'][0]);lines=tree.findall('.//{'+NS+'}p')
            self.assertEqual([line.text for line in lines],['Prueba café & <texto>','Otra línea'])
            self.assertEqual([(line.attrib['begin'],line.attrib['end']) for line in lines],
                             [('00:00:00.100','00:00:00.500'),('00:00:00.500','00:00:00.900')])
            self.assertFalse(tree.findall('.//{'+NS+'}span'))

    def test_never_overwrites_source_existing_target_or_alias(self):
        with tempfile.TemporaryDirectory() as root:
            source=self.source(root);before=source.read_bytes();target=Path(root)/'existing.m4a';target.write_bytes(b'keep')
            for output in (source,target,source.parent/'.'/source.name):
                with self.subTest(output=output),self.assertRaisesRegex(ValueError,'nombre nuevo'):create_trial(source,output)
            self.assertEqual(source.read_bytes(),before);self.assertEqual(target.read_bytes(),b'keep')

    def test_unqualified_timestamps_do_not_create_a_copy(self):
        for text in ('plain text','[00:00.50] First\n[00:00.20] Earlier','[00:00.10] A\n[00:00.10] B',
                     '[00:01.50] Outside','[00:61.00] Invalid','[00:00.10][00:00.20] repeated marker'):
            with self.subTest(text=text),tempfile.TemporaryDirectory() as root:
                source=self.source(root,text);target=Path(root)/'trial.m4a';before=source.read_bytes()
                with self.assertRaises(ValueError):create_trial(source,target)
                self.assertFalse(target.exists());self.assertEqual(source.read_bytes(),before)

    def test_empty_text_bad_control_characters_and_oversize_are_rejected(self):
        for text in ('','[00:00.10]','[00:00.10] A\x01B','x'*(256*1024+1)):
            with self.subTest(length=len(text)),self.assertRaises(ValueError):ttml_from_lrc(text,1000)

    def test_no_lyrics_tag_creates_no_output(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source.m4a';source.write_bytes((FIXTURES/'sample.m4a').read_bytes());target=Path(root)/'trial.m4a'
            audio=MP4(source);audio.tags.pop('\xa9lyr',None);audio.save()
            with self.assertRaisesRegex(ValueError,'no tiene letra'):create_trial(source,target)
            self.assertFalse(target.exists())
