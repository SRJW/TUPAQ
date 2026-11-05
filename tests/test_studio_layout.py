"""Three-column layout keeps real library actions and selection at both sizes."""
import unittest
from PySide6.QtCore import QEvent,Qt
from test_native_connection import APP,TRACK
from importios.native import Window

class StudioLayoutTests(unittest.TestCase):
    def test_details_toggle_and_resizing_preserve_the_library(self):
        w=Window(auto_connect=False);w.show()
        try:
            w.show_library([dict(TRACK,id=str(i),title=f'Song {i:02}') for i in range(40)])
            w.library_model.checked.add('4');w.library_table.selectRow(4)
            w.search.setText('Song')
            self.assertEqual(w.mood_choice.currentIndex(),3)
            for width,columns in ((1500,4),(1080,2)):
                w.resize(width,800);APP.processEvents()
                self.assertEqual(w.action_columns,columns)
                self.assertEqual(w.main_splitter.count(),2)
                self.assertTrue(w.inspector_scroll.isVisible())
                self.assertEqual(w.library_model.rowCount(),40)
                self.assertEqual(w.library_model.checked,{'4'})
                for value in (w.choose,w.import_phone,w.export_phone,w.delete_phone):
                    self.assertTrue(value.isVisible());self.assertGreater(value.width(),50)
            w.inspector_toggle.click();APP.processEvents()
            self.assertFalse(w.inspector_scroll.isVisible())
            self.assertEqual(w.library_model.checked,{'4'})
            w.inspector_toggle.click();APP.processEvents()
            self.assertTrue(w.inspector_scroll.isVisible())
            self.assertEqual(w.search.text(),'Song')
            w.show_track_details(dict(TRACK,sample_rate=96000,bit_depth=24,bit_rate=2100),'En el iPhone')
            self.assertEqual(w.info_fields['quality'].text(),'24 bits · 96 kHz')
            w.show_track_details(dict(TRACK),'En el iPhone')
            self.assertEqual(w.info_fields['quality'].text(),'—')
            self.assertEqual(w.info_fields['bitrate'].text(),'—')
        finally:
            w.tracks.clear();w.close();w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()
