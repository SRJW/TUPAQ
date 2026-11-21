"""Checkboxes select by identity; filters never silently change the target set."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from test_native_connection import APP,Window
from importios.search import matches, matches_format

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

    def test_footer_shows_selection_and_total_library_size(self):
        from importios.i18n import set_language
        w=self.window
        try:
            sized=[
                dict(ROWS[0],size=10*1024**2),
                dict(ROWS[1],size=30*1024**2),
                {'id':'c','title':'Gamma','artist':'Artist','album':'Album','duration':60,'is_local':True,'usb_exists':True,
                 'afc_path':'iTunes_Control/Music/F00/CCCC.m4a','format_label':'M4A · ALAC','size':20*1024**2},
            ]
            w.show_library(sized);APP.processEvents()
            # Without selection: show total library size only.
            self.assertEqual(w.library_size_summary.text(),'Biblioteca: 60.0 MB')
            self.assertTrue(w.library_size_summary.isVisible())
            # Select one track: show both selection and total library size.
            w.library_model.checked.add('a');w.checks_changed()
            self.assertEqual(w.library_size_summary.text(),'Selección: 10.0 MB · Biblioteca: 60.0 MB')
            # Filter by ALAC and select visible ALAC tracks: selection reflects ALAC (50 MB), library stays 60 MB.
            w.library_model.checked.clear()
            w.format_filter.setCurrentIndex(w.format_filter.findText('ALAC'));APP.processEvents()
            w.library_model.check_visible(True);APP.processEvents()
            self.assertEqual(w.library_size_summary.text(),'Selección: 50.0 MB · Biblioteca: 60.0 MB')
            # Live language switch to English translates both the size summary and header song count.
            w.language_choice.setCurrentIndex(1);APP.processEvents()
            self.assertEqual(w.library_size_summary.text(),'Selection: 50.0 MB · Library: 60.0 MB')
            self.assertEqual(w.device_metric.text(),'3 songs')
            # Remote details updating size refresh the summary live.
            w.phone_details_ready(w.library_epoch,'b',{'size':1024**3})
            self.assertEqual(w.library_size_summary.text(),'Selection: 1.02 GB · Library: 1.03 GB')
            # Disconnecting clears and hides the size summary.
            w.devices_found([]);APP.processEvents()
            self.assertEqual(w.library_size_summary.text(),'')
            self.assertFalse(w.library_size_summary.isVisible())
        finally:
            set_language('es')

class SearchTests(unittest.TestCase):
    def test_extensions_codecs_and_combined_metadata(self):
        self.assertTrue(matches(ROWS[0],'.mp3'));self.assertFalse(matches(ROWS[0],'.m4a'))
        self.assertTrue(matches(ROWS[1],'m4a'));self.assertTrue(matches(ROWS[1],'.m4a artist'))
        self.assertTrue(matches(ROWS[1],'alac'));self.assertTrue(matches({'title':'Piano','format_label':'WAV'},'.wav'))
        self.assertFalse(matches(dict(ROWS[0],format_label='WAV',format_source='header'),'.mp3'))

    def test_format_filter_never_matches_title_artist_or_album_substrings(self):
        tricky={'title':'Heat Waves','artist':'Isaac Palace','album':'New Wave MP3 M4A AIFF',
                'afc_path':'iTunes_Control/Music/F00/AAAA.mp3','format_label':'MP3'}
        self.assertTrue(matches_format(tricky,'MP3'))
        for other in ('WAV','AAC','ALAC','M4A','AIFF'):
            with self.subTest(other=other):
                self.assertFalse(matches_format(tricky,other))
        self.assertTrue(matches(tricky,'waves'))
        self.assertTrue(matches(tricky,'isaac'))

    def test_aiff_variants_and_alac_container_and_header_unknown_bytes(self):
        aifc={'title':'AIFC','afc_path':'iTunes_Control/Music/F00/A.aif','format_label':'AIFF-C','format_source':'header'}
        self.assertTrue(matches_format(aifc,'AIFF'))
        self.assertTrue(matches(aifc,'.aif'))
        self.assertTrue(matches(aifc,'aiff'))
        aif_no_label={'title':'AIF','afc_path':'iTunes_Control/Music/F00/B.aif'}
        self.assertTrue(matches_format(aif_no_label,'AIFF'))
        aif_pcm={'title':'PCM','afc_path':'iTunes_Control/Music/F00/C.aif','format_label':'PCM','format_source':'catalogue'}
        self.assertTrue(matches_format(aif_pcm,'AIFF'))
        alac_ext={'title':'ALAC','afc_path':'iTunes_Control/Music/F00/D.alac'}
        self.assertTrue(matches_format(alac_ext,'ALAC'))
        self.assertTrue(matches_format(alac_ext,'M4A'))
        local_alac={'title':'Local','format':'ALAC','container':'M4A'}
        self.assertTrue(matches_format(local_alac,'M4A'))
        self.assertTrue(matches_format(local_alac,'ALAC'))
        self.assertFalse(matches_format(local_alac,'AAC'))
        bad_header={'title':'Corrupt','afc_path':'iTunes_Control/Music/F00/E.mp3','format_label':None,'format_source':'header'}
        self.assertFalse(matches_format(bad_header,'MP3'))
        self.assertFalse(matches(bad_header,'.mp3'))
        self.assertFalse(matches({'title':'Song','artist':None,'album':None,'format_label':'MP3'},'none'))

