"""Large preparation/deletion views stay bounded and retain partial outcomes."""
from pathlib import Path
from unittest.mock import patch,Mock
import unittest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox
from test_native_connection import APP,TRACK
from importios.native import Reader,Window
from importios.audio import inspect_audio

FIXTURES=Path(__file__).parent/'fixtures'

class BulkUITests(unittest.TestCase):
    def test_preparation_bounds_thumbnail_decoding_and_reports_all_input(self):
        reader=Reader([FIXTURES/'covered-aac.m4a']*150);tracks=[]
        def consume(track):tracks.append(track);reader.credits.release()
        reader.track.connect(consume);reader.run()
        images=[QImage.fromData(t['thumbnail']) for t in tracks if t.get('thumbnail')]
        self.assertEqual(len(tracks),150);self.assertEqual(len(images),96)
        self.assertTrue(all(max(i.width(),i.height())<=64 for i in images))

    def test_malformed_input_does_not_flood_the_gui_with_ten_thousand_errors(self):
        reader=Reader([Path('/missing/bad.mp3')]*10000);errors=[];reader.problem.connect(errors.append);reader.run()
        self.assertEqual(reader.problem_count,10000);self.assertEqual(len(errors),101)
        self.assertIn('9900',errors[-1])

    def test_large_delete_requires_confirmation_with_bounded_preview(self):
        w=Window(auto_connect=False)
        try:
            w.show_library([dict(TRACK,id=str(n)) for n in range(5000)]);w.library_model.check_visible(True)
            with patch.object(QMessageBox,'exec',return_value=QMessageBox.StandardButton.Cancel),patch.object(w,'start_transfer') as start:
                w.delete_songs();start.assert_not_called()
            dialog=w.findChildren(QMessageBox)[-1]
            self.assertIn('5000',dialog.text());self.assertLess(len(dialog.detailedText().splitlines()),105)
        finally:w.close();w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()

    def test_partial_import_only_removes_confirmed_rows_from_the_queue(self):
        w=Window(auto_connect=False)
        try:
            track=inspect_audio(FIXTURES/'sample.mp3','sample.mp3')
            for n in range(101):w.accept_track(dict(track,id=str(n)))
            result={'bulk':True,'cancelled':True,'requested':101,'processed':49,'imported':49,'source_ids':[str(n) for n in range(49)]}
            w.transfer_result(result);self.assertIn('49 de 101',w.status.text())
            w.transfer_worker=Mock()
            with patch.object(w,'load_library'):w.transfer_finished()
            self.assertEqual(len(w.tracks),52);self.assertEqual(w.table.rowCount(),52)
            self.assertTrue(all(str(n) in w.tracks for n in range(49,101)))
        finally:w.tracks.clear();w.close();w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()
