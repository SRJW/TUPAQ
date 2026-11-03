import unittest

from PySide6.QtCore import Qt

from importios.models import LibraryModel


class LibraryModelTests(unittest.TestCase):
    def test_large_catalogue_renders_first_and_last_rows_without_cell_objects(self):
        tracks = [{'title': f'Canción {n}', 'artist': 'Artista', 'album': 'Álbum',
                   'duration': 125} for n in range(100_000)]
        model = LibraryModel()
        model.replace(tracks)
        self.assertIs(model.tracks, tracks)
        self.assertEqual(model.rowCount(), 100_000)
        self.assertEqual(model.data(model.index(0, 0)), 'Canción 0')
        self.assertEqual(model.data(model.index(99_999, 0)), 'Canción 99999')
        self.assertEqual(model.data(model.index(99_999, 3)), '2:05')
        self.assertIsNone(model.data(model.index(0, 0), Qt.ItemDataRole.DecorationRole))
        self.assertEqual(model.rowCount(model.index(0, 0)), 0)
        model.replace([])
        self.assertEqual(model.rowCount(), 0)
