"""Stable refreshes and deliberate application-wide typography changes."""
import threading
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QFont,QFontDatabase,QFontInfo
from test_native_connection import APP,Window,TRACK

class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.window=Window(auto_connect=False);self.window.resize(1400,880);self.window.show()
        self.rows=[dict(TRACK,id=str(n),title=f'Song {n:04}',afc_path=f'iTunes_Control/Music/F00/A{n:04}.mp3') for n in range(80)]
        self.window.show_library([dict(t) for t in self.rows]);APP.processEvents()
    def tearDown(self):self.window.close();self.window.deleteLater();APP.processEvents()
    def finish(self):
        deadline=time.monotonic()+8
        while self.window.library_worker is not None and time.monotonic()<deadline:APP.processEvents();time.sleep(.005)
        self.assertIsNone(self.window.library_worker)

    def test_refresh_keeps_rows_selection_scroll_and_cover_until_atomic_result(self):
        w=self.window;model=w.library_model
        w.library_table.selectRow(30);model.setData(model.index(30,0),Qt.CheckState.Checked,Qt.ItemDataRole.CheckStateRole)
        model.set_icon('30',w.default_music_icon);w.library_table.verticalScrollBar().setValue(25);APP.processEvents()
        top=model.tracks[w.library_table.indexAt(QPoint(4,4)).row()]['id'];icon=model.icons['30'].cacheKey()
        release=threading.Event();seen=[];model.modelReset.connect(lambda:seen.append(model.rowCount()))
        def read(**kwargs):release.wait(5);return [dict(TRACK,id='new',title='000 New song')]+[dict(t) for t in self.rows]
        with patch('importios.native.read_phone_library',side_effect=read):
            try:
                w.load_library();APP.processEvents()
                self.assertEqual(model.rowCount(),80);self.assertEqual(seen,[])
                self.assertEqual(w.now_title.text(),'Song 0030');self.assertEqual(model.icons['30'].cacheKey(),icon)
            finally:release.set();self.finish()
        self.assertEqual(seen,[81]);self.assertEqual(model.checked,{'30'})
        self.assertEqual([model.tracks[i.row()]['id'] for i in w.library_table.selectionModel().selectedRows()],['30'])
        self.assertEqual(model.icons['30'].cacheKey(),icon)
        self.assertEqual(model.tracks[w.library_table.indexAt(QPoint(4,4)).row()]['id'],top)

    def test_failed_refresh_keeps_last_good_snapshot_and_diagnostic(self):
        from importios.library import LibraryError
        w=self.window
        with patch('importios.native.read_phone_library',side_effect=LibraryError('Synthetic failure','test:read')):
            w.load_library();self.finish()
        self.assertEqual(w.library_model.rowCount(),80)
        self.assertIn('vista anterior',w.device_status.text());self.assertIn('test:read',w.last_diagnostic)

    def test_completion_message_survives_library_refresh(self):
        w=self.window;w.transfer_result({'imported':1,'already_imported':0});message=w.status.text()
        w.show_library([dict(t) for t in self.rows]);self.assertEqual(w.status.text(),message)

class FontApplicationTests(unittest.TestCase):
    def test_windows_has_fixed_font_without_picker_and_applies_it_everywhere(self):
        with patch('importios.native.sys.platform','win32'):
            w=Window(auto_connect=False);w.show();APP.processEvents()
            try:
                self.assertFalse(hasattr(w,'font_choice'));self.assertFalse(hasattr(w,'choose_font_button'));self.assertFalse(hasattr(w,'apply_font_button'))
                actual=QFontInfo(APP.font()).family()
                for widget in (w.choose,w.nav_buttons[0],w.now_title,w.library_table,w.library_table.horizontalHeader(),w.theme_choice,w.status):
                    self.assertEqual(QFontInfo(widget.font()).family(),actual,widget.objectName())
                from PySide6.QtWidgets import QMessageBox
                dialog=QMessageBox(w);self.assertEqual(QFontInfo(dialog.font()).family(),actual);dialog.deleteLater()
                self.assertIn('Mori',w.font_status.text())
            finally:w.close();w.deleteLater();APP.processEvents()

    def test_mac_keeps_system_font_even_when_mori_is_available(self):
        with patch('importios.native.sys.platform','darwin'):
            w=Window(auto_connect=False)
            try:
                self.assertFalse(hasattr(w,'font_choice'));self.assertFalse(hasattr(w,'apply_font_button'))
                self.assertIn('fuente del sistema',w.font_status.text());self.assertFalse(APP.typography_is_mori)
            finally:w.close();w.deleteLater();APP.processEvents()

    def test_real_mori_weights_when_personal_test_fonts_are_available(self):
        import os
        from pathlib import Path
        from importios.typography import configure
        root=Path(os.environ.get('TUPAQ_TEST_MORI_DIR','/nonexistent-private-test-fonts'))
        files=[root/f'PPMori-{weight}.ttf' for weight in ('Regular','Medium','SemiBold','Bold')]
        if not all(file.is_file() for file in files):self.skipTest('Personal Mori files are not redistributed with tests')
        identifiers=[QFontDatabase.addApplicationFont(str(file)) for file in files]
        try:
            with patch('importios.native.sys.platform','win32'):
                w=Window(auto_connect=False);w.show();APP.processEvents()
                try:
                    self.assertTrue(APP.typography_is_mori);self.assertEqual(APP.font().pixelSize(),14)
                    for weight,style in ((400,'Regular'),(500,'Medium'),(600,'SemiBold'),(700,'Bold')):
                        font=QFont('PP Mori');font.setWeight(QFont.Weight(weight));info=QFontInfo(font)
                        self.assertEqual(info.family(),'PP Mori');self.assertEqual(info.weight(),weight);self.assertEqual(info.styleName(),style)
                    from PySide6.QtGui import QFontMetrics
                    self.assertGreaterEqual(w.library_table.columnWidth(3),QFontMetrics(w.library_table.font()).horizontalAdvance('M4A · ALAC')+18)
                    for widget in (w.choose,w.heading,w.nav_buttons[0],w.library_table,w.library_table.horizontalHeader(),w.info_artist,w.status,w.font_status):
                        self.assertEqual(QFontInfo(widget.font()).family(),'PP Mori')
                finally:w.close();w.deleteLater();APP.processEvents()
        finally:
            for identifier in identifiers:QFontDatabase.removeApplicationFont(identifier)
            configure(APP)
