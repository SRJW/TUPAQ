"""Live language changes preserve music, selection, queue and diagnostic codes."""
import ast
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QEvent
from test_native_connection import APP
from importios.native import Window
from importios.i18n import tr, set_language, language
from importios.translations import EN


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.window=Window(auto_connect=False)
        self.window.show();APP.processEvents()

    def tearDown(self):
        self.window.tracks.clear();self.window.close();self.window.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()
        set_language('es')

    def test_switch_translates_controls_headers_status_and_preserves_music(self):
        w=self.window
        track={'id':'song','title':'Biblioteca','artist':'Preferencias','album':'Canción',
               'duration':120,'is_local':True,'afc_path':'/iTunes_Control/Music/a.mp3'}
        w.show_library([track]);w.library_model.checked.add('song')
        w.library_table.selectRow(0)
        w.add_paths([Path('tests/fixtures/sample.mp3')])
        import time
        deadline=time.monotonic()+5
        while w.worker is not None and time.monotonic()<deadline:APP.processEvents();time.sleep(.005)
        self.assertIsNone(w.worker)
        original=dict(w.tracks)
        w.table.item(0,6).setText(tr('Enviando…'))
        w.library_table.selectRow(0);w.show_track_details(track,'En el iPhone')
        w.search.setText('Biblioteca');w.navigate(1)
        w.status.setText(tr('Importando: Biblioteca: Canción'))
        with patch('importios.native.read_phone_library') as read,patch('importios.native.run_transfer') as transfer:
            w.language_choice.setCurrentIndex(1)
            self.assertEqual(language(),'en');self.assertEqual(w.pages.currentIndex(),1)
            self.assertEqual(w.heading.text(),'Library');self.assertEqual(w.nav_buttons[1].text(),'Settings')
            self.assertEqual(w.library_model.headerData(0,Qt.Orientation.Horizontal),'Song')
            self.assertEqual(w.table.horizontalHeaderItem(5).text(),'Size');self.assertEqual(w.table.item(0,6).text(),'Sending…')
            self.assertEqual(w.theme_choice.itemText(2),'Dark');self.assertEqual(w.mood_choice.itemText(2),'Sunset')
            self.assertEqual(w.now_title.text(),'Biblioteca');self.assertEqual(w.info_artist.text(),'Preferencias')
            self.assertEqual(w.info_fields['album'].text(),'Canción');self.assertEqual(w.search.text(),'Biblioteca')
            self.assertEqual(w.status.text(),'Importing: Biblioteca: Canción')
            self.assertEqual(w.tracks,original);self.assertEqual(w.library_model.checked,{'song'})
            self.assertEqual(w.library_table.selectionModel().selectedRows()[0].row(),0)
            w.language_choice.setCurrentIndex(0)
            self.assertEqual(w.heading.text(),'Biblioteca');self.assertEqual(w.status.text(),'Importando: Biblioteca: Canción');self.assertEqual(w.table.item(0,6).text(),'Enviando…')
            read.assert_not_called();transfer.assert_not_called()

    def test_progress_errors_and_cancellation_follow_current_language(self):
        w=self.window;w.language_choice.setCurrentIndex(1)
        self.assertEqual(str(tr('1 canciones en el iPhone')),'1 song on iPhone')
        w.transfer_progress(1,2,'Leyendo el estado actual de Música…')
        self.assertEqual(w.status.text(),'Reading the current Music state…')
        raw='TUPAQ 0.3.0-preview.13\nLa importación se detuvo o no pudo verificarse. Revisa el diagnóstico y el respaldo del catálogo antes de repetirla.\nDiagnóstico: import:artwork-cache-token'
        w.show_library_error(raw)
        self.assertIn('The import stopped',w.device_status.text())
        self.assertIn('Diagnostics: import:artwork-cache-token',w.device_status.text())
        self.assertEqual(w.last_diagnostic,raw)
        w.transfer_result({'cancelled':True,'exported':2})
        self.assertEqual(w.status.text(),'Export cancelled. Kept 2 complete files.')
        w.language_choice.setCurrentIndex(0)
        self.assertIn('La importación se detuvo',w.device_status.text())
        self.assertEqual(w.status.text(),'Exportación cancelada. Se conservaron 2 archivos completos.')
        details=[{'code':'verify-new-metadata','entry_index':1,'metadata_fields':['album']}]
        w.transfer_result({'imported':0,'already_imported':1,'metadata_unverified':1,'metadata_diagnostics':details})
        self.assertIn('metadatos pendientes de revisión',w.status.text())
        w.language_choice.setCurrentIndex(1)
        self.assertEqual(w.status.text(),'Audio verified. Metadata review pending for 1 song.')
        diagnostic=w.last_diagnostic
        w.show_library([],diagnostic='library counts')
        self.assertEqual(w.last_diagnostic,diagnostic)
        self.assertIn('"metadata_fields": ["album"]',diagnostic)

    def test_choice_is_saved_and_restored_and_invalid_saved_value_falls_back(self):
        data={'automatic_library':False}
        class Settings:
            def value(self,key,default=None,**kwargs):return data.get(key,default)
            def setValue(self,key,value):data[key]=value
            def remove(self,key):data.pop(key,None)
        with patch('importios.native.QSettings',Settings):
            w=self.window;w.persist_settings=True;w.language_choice.setCurrentIndex(1)
            self.assertEqual(data['language'],'en')
            other=Window(auto_connect=True)
            try:
                self.assertEqual(other.language_choice.currentData(),'en');self.assertEqual(other.heading.text(),'Library')
            finally:other.close();other.deleteLater()
            data['language']=['unknown']
            other=Window(auto_connect=True)
            try:self.assertEqual(other.language_choice.currentData(),'es');self.assertEqual(other.heading.text(),'Biblioteca')
            finally:other.close();other.deleteLater()

    def test_catalogue_preserves_template_fields_and_covers_explicit_ui_literals(self):
        from string import Formatter
        for source,target in EN.items():
            fields=lambda text:{field for _,field,_,_ in Formatter().parse(text) if field}
            self.assertEqual(fields(source),fields(target),source)
        # Explicit static UI messages must have English entries. Symbols and brands need none.
        for filename in ('interface.py','native.py'):
            for node in ast.walk(ast.parse(Path('importios',filename).read_text(encoding='utf-8'))):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='tr' and node.args:
                    arg=node.args[0]
                    if isinstance(arg,ast.Constant) and isinstance(arg.value,str) and any(c.isalpha() for c in arg.value) and arg.value not in ('iPhone','CSV (*.csv)'):
                        self.assertIn(arg.value,EN)
