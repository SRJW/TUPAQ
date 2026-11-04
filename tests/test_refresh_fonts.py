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
    def test_installed_font_is_staged_then_applied_to_buttons_labels_headers_and_dialogs(self):
        # Exercise Windows controls on every runner, including native Mac runners.
        with patch('importios.native.sys.platform','win32'):
            w=Window(auto_connect=False);w.show();APP.processEvents()
            try:
                current=w.font_choice.currentFont().family()
                family=next(f for f in QFontDatabase.families() if f not in (current,w.font_choice.currentText()))
                old=QFontInfo(w.choose.font()).family();w.font_choice.setCurrentFont(QFont(family));APP.processEvents()
                self.assertEqual(QFontInfo(w.choose.font()).family(),old);self.assertTrue(w.apply_font_button.isEnabled())
                w.apply_font();APP.processEvents()
                resolved=QFontInfo(APP.font()).family()
                self.assertEqual(APP.font().family(),family)
                for widget in (w.choose,w.nav_buttons[0],w.now_title,w.library_table,w.library_table.horizontalHeader(),w.theme_choice,w.status):
                    self.assertEqual(QFontInfo(widget.font()).family(),resolved,widget.objectName())
                    self.assertIn(family,widget.font().families())
                from PySide6.QtWidgets import QMessageBox
                dialog=QMessageBox(w);self.assertEqual(QFontInfo(dialog.font()).family(),resolved);dialog.deleteLater()
                self.assertFalse(w.apply_font_button.isEnabled())
                w.reset_font();self.assertEqual(QFontInfo(w.choose.font()).family(),resolved)
                w.apply_font();APP.processEvents()
            finally:w.close();w.deleteLater();APP.processEvents()

    def test_mac_exposes_system_typography_without_custom_font_controls(self):
        with patch('importios.native.sys.platform','darwin'):
            w=Window(auto_connect=False)
            try:
                self.assertFalse(hasattr(w,'font_choice'));self.assertFalse(hasattr(w,'apply_font_button'))
                self.assertIn('fuente del sistema',w.font_status.text())
            finally:w.close();w.deleteLater();APP.processEvents()

    def test_font_file_waits_for_apply_then_updates_entire_window(self):
        from pathlib import Path
        candidates=[Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),Path('C:/Windows/Fonts/arial.ttf'),Path('/System/Library/Fonts/Supplemental/Arial.ttf')]
        file=next((path for path in candidates if path.is_file()),None)
        if file is None:self.skipTest('No test font file available on this runner')
        with patch('importios.native.sys.platform','win32'):
            w=Window(auto_connect=False)
            try:
                original=APP.font()
                with patch('importios.native.QFileDialog.getOpenFileName',return_value=(str(file),'')):w.choose_font()
                self.assertEqual(APP.font(),original);self.assertTrue(w.apply_font_button.isEnabled())
                w.apply_font();APP.processEvents()
                actual=QFontInfo(APP.font()).family()
                self.assertEqual(APP.typography_font_path,str(file))
                self.assertEqual(QFontInfo(w.library_table.horizontalHeader().font()).family(),actual)
                self.assertEqual(QFontInfo(w.nav_buttons[1].font()).family(),actual)
                w.reset_font();w.apply_font()
            finally:w.close();w.deleteLater();APP.processEvents()
