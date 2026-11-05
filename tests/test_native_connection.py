"""Native UI behaviour with a simulated attach; never opens USB or imports."""
import os
import sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import unittest
from unittest.mock import patch, Mock
from importios.cancellation import TransferControl

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QCloseEvent,QFontDatabase,QPalette
from PySide6.QtWidgets import QApplication, QMessageBox
from importios.native import Window
from importios.visuals import app_icon

APP = QApplication.instance() or QApplication([])
# Qt's Windows offscreen plugin does not enumerate the system font collection.
# Register real OS fonts for the GUI tests; nothing is copied or distributed.
TEST_FONT_IDS=[]
if sys.platform=='win32' and len(QFontDatabase.families())<2:
    font_folder=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'
    for filename in ('arial.ttf','consola.ttf','times.ttf'):
        path=font_folder/filename
        if path.is_file():
            identifier=QFontDatabase.addApplicationFont(str(path))
            if identifier>=0:TEST_FONT_IDS.append(identifier)

TRACK = {'id':'1','title':'Prueba','artist':'Artista','album':'Álbum','duration':120,'is_local':True}


class NativeConnectionTests(unittest.TestCase):
    def setUp(self):
        self.window=Window(auto_connect=False)
        self.window.show();APP.processEvents()

    def tearDown(self):
        self.window.tracks.clear()
        self.window.theme_choice.setCurrentIndex(0)
        self.window.close();self.window.deleteLater()
        APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        APP.processEvents()

    def test_connection_indicator_tracks_usb_across_themes_and_languages(self):
        w=self.window
        from importios.i18n import set_language
        with patch.object(w,'load_library'):
            self.assertFalse(w.connection_dot.property('connected'))
            w.devices_found([{'token':'one'}]);self.assertTrue(w.connection_dot.property('connected'))
            for theme in (1,2):
                w.theme_choice.setCurrentIndex(theme);w.language_choice.setCurrentIndex(1);APP.processEvents()
                self.assertTrue(w.connection_dot.property('connected'));self.assertEqual(w.connection_badge.text(),'Connected by USB')
                color=w.connection_dot.palette().color(QPalette.ColorRole.WindowText)
                self.assertGreater(color.green(),color.red()*1.3);self.assertGreater(color.green(),color.blue()*1.3)
                w.devices_found([]);self.assertFalse(w.connection_dot.property('connected'))
                color=w.connection_dot.palette().color(QPalette.ColorRole.WindowText)
                self.assertLess(max(color.red(),color.green(),color.blue())-min(color.red(),color.green(),color.blue()),10)
                w.devices_found([{'token':'one'}]);self.assertTrue(w.connection_dot.property('connected'))
            w.device_problem('USB error');self.assertFalse(w.connection_dot.property('connected'))
            w.devices_found([{'token':'one'},{'token':'two'}]);self.assertFalse(w.connection_dot.property('connected'))
        w.language_choice.setCurrentIndex(0);set_language('es')

    def test_delayed_library_result_cannot_turn_disconnected_indicator_green(self):
        import threading
        ready=threading.Event();release=threading.Event()
        def delayed(diagnostics=None,device_info=None):
            ready.set();release.wait(3)
            if device_info is not None:device_info['name']='Stale phone'
            return [dict(TRACK)]
        w=self.window
        try:
            with patch('importios.native.read_phone_library',side_effect=delayed):
                w.devices_found([{'token':'one'}]);self.assertTrue(ready.wait(2))
                w.devices_found([]);release.set();self.drain_library()
                self.assertFalse(w.connection_dot.property('connected'));self.assertEqual(w.library_model.rowCount(),0)
                self.assertEqual(w.device_name.text(),'iPhone')
        finally:release.set()

    def drain_library(self):
        end=time.monotonic()+5
        while self.window.library_worker is not None and time.monotonic()<end:
            APP.processEvents();time.sleep(.005)
        self.assertIsNone(self.window.library_worker)

    def test_cancel_button_explains_committed_batch_and_keeps_progress_message(self):
        control=TransferControl();control.begin_commit()
        worker=Mock(mode='import',control=control)
        worker.cancel.side_effect=control.request
        self.window.transfer_worker=worker
        try:
            self.window.cancel_transfer_button.show()
            self.window.cancel_transfer_button.click()
            self.assertTrue(control.event.is_set())
            self.assertFalse(self.window.cancel_transfer_button.isEnabled())
            self.assertIn('Se finalizará este lote',self.window.status.text())
            self.window.transfer_progress(1,2,'Enviando…')
            self.assertIn('Se finalizará este lote',self.window.status.text())
        finally:self.window.transfer_worker=None

    def test_cancel_queued_intent_before_artwork_finishes_never_starts_transfer(self):
        self.window.after_artwork=('transfer','import',[dict(TRACK)],Path('/tmp'))
        self.window.cancel_transfer_button.show()
        with patch.object(self.window,'start_transfer') as start:
            self.window.cancel_transfer_button.click()
            self.assertIsNone(self.window.after_artwork)
            self.assertFalse(self.window.cancel_transfer_button.isVisible())
            self.assertIn('cancelada antes',self.window.status.text())
            start.assert_not_called()

    def test_attach_loads_once_replug_reloads_and_never_imports(self):
        with patch('importios.native.read_phone_library',return_value=[dict(TRACK)]) as read,patch('importios.native.run_transfer') as transfer:
            self.window.devices_found([{'token':'first'}]);self.drain_library()
            self.assertTrue(self.window.library_ready)
            self.assertEqual(self.window.pages.currentIndex(),0)
            self.assertEqual(self.window.library_model.rowCount(),1)
            self.assertTrue(self.window.local_tools.isVisible())
            self.window.devices_found([{'token':'first'}]);APP.processEvents()
            self.assertEqual(read.call_count,1)
            self.window.devices_found([])
            self.assertEqual(self.window.library_model.rowCount(),0)
            self.window.devices_found([{'token':'second'}]);self.drain_library()
            self.assertEqual(read.call_count,2)
            transfer.assert_not_called()

    def test_attach_preserves_computer_queue_and_inactive_preferences(self):
        with patch('importios.native.read_phone_library',return_value=[dict(TRACK)]):
            self.window.tracks['queued']={'id':'queued'}
            self.window.devices_found([{'token':'first'}]);self.drain_library()
            self.assertEqual(self.window.pages.currentIndex(),0)
            self.window.navigate(1)
            self.window.devices_found([{'token':'second'}]);self.drain_library()
            self.assertEqual(self.window.pages.currentIndex(),1)
            self.assertIn('queued',self.window.tracks)

    def test_theme_navigation_and_bounded_thumbnail_cache(self):
        for choice,dark in [(1,False),(2,True)]:
            self.window.theme_choice.setCurrentIndex(choice)
            self.assertEqual(self.window.theme_dark,dark)
            self.window.nav_buttons[0].click()
            self.assertEqual(self.window.pages.currentIndex(),0)
        model=self.window.library_model
        model.replace([dict(TRACK,id=str(n)) for n in range(260)])
        icon=app_icon()
        for n in range(260):model.set_icon(str(n),icon)
        self.assertEqual(len(model.icons),96)
        self.assertNotIn('0',model.icons)
        self.assertEqual(model.data(model.index(259,0),Qt.ItemDataRole.DecorationRole).cacheKey(),icon.cacheKey())
        model.replace([])
        self.assertFalse(model.icons)
        self.window.nav_buttons[1].click()
        self.assertEqual(self.window.pages.currentIndex(),1)

    def test_cancelling_close_keeps_automatic_detection_running(self):
        self.window.tracks['queued']={'id':'queued'}
        self.window.device_timer.start()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):
            event=QCloseEvent();self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertTrue(self.window.device_timer.isActive())
