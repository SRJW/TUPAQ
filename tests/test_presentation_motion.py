"""Motion stays finite, can be disabled, and never resets the music library."""
import unittest
from PySide6.QtCore import QAbstractAnimation,QVariantAnimation,QEvent,Qt,QElapsedTimer
from PySide6.QtGui import QPixmap,QColor
from PySide6.QtTest import QTest
from test_native_connection import APP,TRACK
from importios.native import Window


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.w=Window(auto_connect=False);self.w.show();APP.processEvents()
    def tearDown(self):
        self.w.tracks.clear();self.w.close();self.w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()
    def running(self):
        return [a for a in self.w.findChildren(QVariantAnimation) if a.property('tupaqMotion') and a.state()==QAbstractAnimation.State.Running]
    def wait_for_motion(self):
        # The first unified-animation tick can be delayed on a busy native
        # runner. Wait for natural completion, without forcing time/finish.
        # The production transition still has its 180 ms duration.
        timer=QElapsedTimer();timer.start()
        while (self.w.motion.overlay.isVisible() or self.running()) and timer.elapsed()<2000:
            QTest.qWait(10)
        self.assertFalse(self.w.motion.overlay.isVisible())
        self.assertFalse(self.running())

    def test_navigation_finishes_and_retains_selection_and_search(self):
        w=self.w;w.show_library([dict(TRACK,id='a'),dict(TRACK,id='b')]);w.library_model.checked.add('a');w.search.setText('Prueba')
        w.navigate(1)
        self.assertEqual(w.pages.currentIndex(),1);self.assertTrue(w.motion.overlay.isVisible())
        self.assertEqual(w.motion.overlay.transition.duration(),180)
        self.wait_for_motion()
        self.assertFalse(w.motion.overlay.isVisible());self.assertTrue(w.motion.overlay.image.isNull());self.assertFalse(self.running())
        w.navigate(0);self.wait_for_motion()
        self.assertEqual(w.library_model.checked,{'a'});self.assertEqual(w.search.text(),'Prueba');self.assertEqual(w.library_model.rowCount(),2)
        w.show_library([dict(TRACK,id='a'),dict(TRACK,id='b')])
        self.assertFalse(w.motion.overlay.isVisible());self.assertFalse(self.running())

    def test_reduce_motion_finishes_active_transitions_and_removes_frames(self):
        w=self.w;w.navigate(1);self.assertTrue(self.running())
        w.reduce_motion.setChecked(True)
        self.assertFalse(self.running());self.assertFalse(w.motion.overlay.isVisible());self.assertTrue(w.motion.overlay.image.isNull())
        w.navigate(0);self.assertFalse(self.running());self.assertEqual(w.pages.currentIndex(),0)
        w.reduce_motion.setChecked(False);w.navigate(1);self.assertTrue(self.running())

    def test_cover_blends_without_empty_frames_and_discards_old_image(self):
        w=self.w;w.inspector_toggle.setChecked(True);APP.processEvents();first=QPixmap(224,224);first.fill(QColor('red'));second=QPixmap(224,224);second.fill(QColor('blue'))
        w.now_cover.setPixmap(first);w.now_cover.setPixmap(second)
        self.assertFalse(w.now_cover.pixmap().isNull());self.assertFalse(w.now_cover.previous.isNull())
        self.assertEqual(w.now_cover.pixmap().toImage().pixelColor(10,10),QColor('blue'))
        w.reduce_motion.setChecked(True);self.assertTrue(w.now_cover.previous.isNull());self.assertFalse(self.running())

    def test_empty_state_offers_contextual_actions_and_never_covers_songs(self):
        w=self.w;self.assertTrue(w.library_empty.isVisible())
        self.assertEqual(w.library_empty.button.text(),'Comprobar USB')
        w.show_library([dict(TRACK)]);APP.processEvents();self.assertFalse(w.library_empty.isVisible())
        w.search.setText('nothing');APP.processEvents();self.assertTrue(w.library_empty.isVisible())
        self.assertEqual(w.library_empty.button.text(),'Limpiar búsqueda');w.library_empty.button.click()
        self.assertEqual(w.search.text(),'');self.assertEqual(w.library_model.rowCount(),1);self.assertFalse(w.library_empty.isVisible())

    def test_primary_hover_keeps_readable_text_in_light_and_dark_modes(self):
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QPalette
        def luminance(color):
            values=[v/255 for v in (color.red(),color.green(),color.blue())]
            values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
            return sum(v*k for v,k in zip(values,(.2126,.7152,.0722)))
        w=self.w
        for theme in (1,2):
            w.theme_choice.setCurrentIndex(theme);w.import_phone.setEnabled(True);APP.processEvents()
            QTest.mouseMove(w,QPoint(5,5));QTest.mouseMove(w.import_phone,QPoint(30,40));QTest.qWait(220)
            image=w.import_phone.grab().toImage();background=image.pixelColor(round(30*w.devicePixelRatioF()),round(40*w.devicePixelRatioF()))
            foreground=w.import_phone.palette().color(QPalette.ColorRole.ButtonText)
            a,b=sorted((luminance(foreground),luminance(background)))
            self.assertGreaterEqual((b+.05)/(a+.05),4.5)

    def test_drag_feedback_only_accepts_local_files_and_never_imports(self):
        from unittest.mock import patch
        from PySide6.QtCore import QMimeData,QUrl,QPoint,QPointF
        from PySide6.QtGui import QDragEnterEvent,QDragLeaveEvent,QDropEvent
        w=self.w;mime=QMimeData();mime.setUrls([QUrl.fromLocalFile('/tmp/sample.mp3')])
        enter=QDragEnterEvent(QPoint(30,30),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        w.dragEnterEvent(enter);self.assertTrue(enter.isAccepted());self.assertTrue(w.drop_veil.isVisible())
        w.dragLeaveEvent(QDragLeaveEvent());self.assertFalse(w.drop_veil.isVisible())
        w.dragEnterEvent(enter)
        with patch.object(w,'add_paths') as add,patch.object(w,'import_songs') as transfer:
            drop=QDropEvent(QPointF(30,30),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
            w.dropEvent(drop);add.assert_called_once_with(['/tmp/sample.mp3']);transfer.assert_not_called()
        self.assertFalse(w.drop_veil.isVisible())
        mime.setUrls([QUrl('https://example.com/file.mp3')]);bad=QDragEnterEvent(QPoint(30,30),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        w.dragEnterEvent(bad);self.assertFalse(bad.isAccepted());self.assertFalse(w.drop_veil.isVisible())

    def test_repeated_original_preview_updates_do_not_flash_thumbnail(self):
        from importios.artwork import preview_image,image_info
        from test_selected_assets import cover
        w=self.w;w.inspector_toggle.setChecked(True);APP.processEvents();track=dict(TRACK);w.show_track_details(track,'En el iPhone')
        data=cover(500,500);w.preview_ready(w.preview_generation,{'cover':data,'image':preview_image(data),**image_info(data)})
        w.reduce_motion.setChecked(True);original=w.now_cover.pixmap().toImage().pixelColor(100,100)
        w.reduce_motion.setChecked(False);w.show_track_details(track,'En el iPhone')
        self.assertEqual(w.now_cover.pixmap().toImage().pixelColor(100,100),original)
        # Re-rendering the same source must not blend a placeholder into it.
        self.assertTrue(w.now_cover.previous.isNull())
