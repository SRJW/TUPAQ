"""Checkboxes select by identity; filters never silently change the target set."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from test_native_connection import APP,Window
from importios.search import matches

ROWS=[{'id':'a','title':'Alpha','artist':'Artist','album':'Album','duration':42,'is_local':True,'usb_exists':True,
       'afc_path':'iTunes_Control/Music/F00/AAAA.mp3','format_label':'MP3'},
      {'id':'b','title':'Beta','artist':'Artist','album':'Album','duration':52,'is_local':True,'usb_exists':True,
       'afc_path':'iTunes_Control/Music/F00/BBBB.m4a','format_label':'M4A · ALAC'}]

class SelectionTests(unittest.TestCase):
    def setUp(self):self.window=Window(auto_connect=False);self.window.show();self.window.show_library([dict(t) for t in ROWS]);APP.processEvents()
    def tearDown(self):self.window.close();self.window.deleteLater();APP.processEvents()

    def test_keyboard_checks_survive_sort_search_and_select_visible(self):
        w=self.window;w.library_table.setCurrentIndex(w.library_model.index(0,0));w.library_table.setFocus()
        QTest.keyClick(w.library_table,Qt.Key.Key_Space);APP.processEvents()
        self.assertEqual(w.library_model.checked,{'a'});self.assertTrue(w.export_phone.isEnabled())
        w.library_table.sortByColumn(0,Qt.SortOrder.DescendingOrder)
        self.assertEqual(w.marked_tracks()[0]['id'],'a')
        w.search.setText('.m4a');self.assertEqual(w.library_model.rowCount(),1)
        w.library_model.check_visible(True);self.assertEqual(w.library_model.checked,{'a','b'})
        w.library_model.check_visible(False);self.assertEqual(w.library_model.checked,{'a'})
        self.assertEqual(w.selection_count.text(),'1 seleccionadas')
        w.devices_found([]);self.assertFalse(w.library_model.checked)

    def test_delete_requires_checks_and_explicit_confirmation(self):
        w=self.window
        with patch.object(w,'start_transfer') as transfer,patch.object(QMessageBox,'exec',return_value=QMessageBox.StandardButton.Cancel) as dialog:
            w.library_table.selectRow(0);w.delete_songs();dialog.assert_not_called()
            w.library_model.check_visible(True);w.delete_songs();dialog.assert_called_once();transfer.assert_not_called()
        with patch.object(w,'start_transfer') as transfer,patch.object(QMessageBox,'exec',return_value=QMessageBox.StandardButton.Yes):
            w.delete_songs();self.assertEqual(transfer.call_args.args[0],'delete');self.assertEqual(len(transfer.call_args.args[1]),2)

    def test_recovery_tools_are_collapsed_by_default(self):
        w=self.window;w.navigate(3);APP.processEvents()
        self.assertFalse(w.verify_import.isVisible());w.advanced.setChecked(True);APP.processEvents();self.assertTrue(w.verify_import.isVisible())

class SearchTests(unittest.TestCase):
    def test_extensions_codecs_and_combined_metadata(self):
        self.assertTrue(matches(ROWS[0],'.mp3'));self.assertFalse(matches(ROWS[0],'.m4a'))
        self.assertTrue(matches(ROWS[1],'m4a'));self.assertTrue(matches(ROWS[1],'.m4a artist'))
        self.assertTrue(matches(ROWS[1],'alac'));self.assertTrue(matches({'title':'Piano','format_label':'WAV'},'.wav'))
        self.assertFalse(matches(dict(ROWS[0],format_label='WAV',format_source='header'),'.mp3'))
