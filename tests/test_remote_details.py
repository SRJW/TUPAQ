"""Visible-row format/size inspection must use actual bytes, not filename."""
import asyncio
from pathlib import Path
import unittest

from test_remote_artwork import AFC,AUDIO
from importios.remote_details import audio_details

FIXTURES=Path(__file__).parent/'fixtures'


class RemoteDetailsTests(unittest.TestCase):
    def test_real_formats_and_exact_sizes_from_bounded_read_only_headers(self):
        for name,label in [('sample.mp3','MP3'),('sample.wav','WAV'),('sample.aiff','AIFF'),
                           ('sample.m4a','M4A · ALAC'),('covered-aac.m4a','M4A · AAC')]:
            with self.subTest(name=name):
                data=(FIXTURES/name).read_bytes();afc=AFC({AUDIO:data})
                result=asyncio.run(audio_details(afc,{'afc_path':AUDIO}))
                self.assertEqual(result['format_label'],label)
                from mutagen import File
                self.assertAlmostEqual(result['duration'],File(FIXTURES/name).info.length,delta=.1)
                self.assertEqual(result['sample_rate'],File(FIXTURES/name).info.sample_rate)
                if name in ('sample.wav','sample.aiff','sample.m4a'):
                    self.assertEqual(result['bit_depth'],File(FIXTURES/name).info.bits_per_sample)
                else:self.assertNotIn('bit_depth',result)
                self.assertEqual(result['size'],len(data));self.assertEqual(result['size_source'],'usb')
                self.assertFalse(afc.handles)
                self.assertTrue(all(mode=='r' for _,mode in afc.opens))

    def test_invalid_path_is_not_opened_and_unknown_bytes_do_not_invent_format(self):
        afc=AFC({AUDIO:b'unknown data payload'})
        self.assertEqual(asyncio.run(audio_details(afc,{'afc_path':'../private'})),{})
        self.assertFalse(afc.opens)
        result=asyncio.run(audio_details(afc,{'afc_path':AUDIO}))
        self.assertIsNone(result['format_label'])
        self.assertEqual(result['size'],20)
        self.assertNotIn('sample_rate',result);self.assertNotIn('bit_depth',result)
