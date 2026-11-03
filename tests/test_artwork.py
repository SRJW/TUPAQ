from pathlib import Path
import unittest
from PySide6.QtGui import QImage

from importios.audio import inspect_audio, read_artwork
from importios.artwork import thumbnail


class ArtworkTests(unittest.TestCase):
    def test_embedded_m4a_cover_becomes_bounded_png(self):
        path = Path(__file__).parent/'fixtures/covered-aac.m4a'
        self.assertEqual(inspect_audio(path, path.name)['format'], 'AAC')
        self.assertTrue(inspect_audio(path, path.name)['has_artwork'])
        image = QImage.fromData(thumbnail(read_artwork(path)))
        self.assertFalse(image.isNull())
        self.assertLessEqual(max(image.width(), image.height()), 96)

    def test_no_cover_and_invalid_image_use_placeholder(self):
        self.assertIsNone(read_artwork(Path(__file__).parent/'fixtures/sample.wav'))
        self.assertIsNone(thumbnail(b'not an image'))
        self.assertIsNone(thumbnail(b'x'*(5*1024*1024+1)))
