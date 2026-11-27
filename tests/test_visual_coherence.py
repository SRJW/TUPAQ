"""Visual coherence regressions across all 5 pages, both themes, and both languages."""
from datetime import datetime
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QPushButton

from importios.i18n import set_language
from importios.interface import theme_thumbnail
from importios.models import FormatBadgeDelegate
from importios.native import Window
from test_native_connection import APP, TRACK


class VisualCoherenceTests(unittest.TestCase):
    def setUp(self):
        self.window = Window(auto_connect=False)
        self.window.resize(1080, 720)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.tracks.clear()
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        set_language('es')

    def test_import_side_cards_are_aligned_and_never_clip_titles_or_chips(self):
        w = self.window
        for lang_idx in (0, 1):
            w.language_choice.setCurrentIndex(lang_idx)
            w.navigate(2)
            APP.processEvents()
            self.assertEqual(w.formats_card.width(), w.queue_summary_card.width())
            title_font = QFont(w.font())
            title_font.setPointSizeF(w.font().pointSizeF() + 1)
            title_font.setWeight(QFont.Weight.DemiBold)
            metrics = QFontMetrics(title_font)
            expected_title = 'Formatos compatibles' if lang_idx == 0 else 'Supported formats'
            self.assertGreaterEqual(w.formats_card.width(), metrics.horizontalAdvance(expected_title) + 40)

    def test_system_theme_thumbnail_splits_light_and_dark_halves(self):
        light_img = theme_thumbnail('light').toImage()
        dark_img = theme_thumbnail('dark').toImage()
        sys_img = theme_thumbnail('system').toImage()
        # Left canvas should be bright (light theme) and right canvas dark (dark theme).
        left_pixel = sys_img.pixelColor(70, 90)
        right_pixel = sys_img.pixelColor(sys_img.width() - 30, 90)
        self.assertGreater(left_pixel.lightness(), 200)
        self.assertLess(right_pixel.lightness(), 80)
        self.assertNotEqual(sys_img, light_img)
        self.assertNotEqual(sys_img, dark_img)

    def test_tables_use_format_badges_and_aligned_numeric_columns(self):
        w = self.window
        self.assertIsInstance(w.library_table.itemDelegateForColumn(3), FormatBadgeDelegate)
        self.assertIsInstance(w.table.itemDelegateForColumn(3), FormatBadgeDelegate)
        w.show_library([dict(TRACK, id='1', format_label='M4A · ALAC', duration=215, size=12 * 1024**2)])
        m = w.library_model
        self.assertEqual(m.data(m.index(0, 3), Qt.ItemDataRole.TextAlignmentRole), int(Qt.AlignmentFlag.AlignCenter))
        self.assertEqual(m.data(m.index(0, 4), Qt.ItemDataRole.TextAlignmentRole), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        self.assertEqual(m.data(m.index(0, 5), Qt.ItemDataRole.TextAlignmentRole), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
        for theme in (1, 2):
            w.theme_choice.setCurrentIndex(theme)
            APP.processEvents()
            expected_dark = theme == 2
            self.assertEqual(w.library_table.property('darkTheme'), expected_dark)
            self.assertEqual(w.table.property('darkTheme'), expected_dark)

    def test_diagnostics_pill_is_compact_and_usb_card_has_transport_detail(self):
        w = self.window
        w.navigate(3)
        APP.processEvents()
        self.assertLessEqual(w.diagnostic_state.height(), 46)
        self.assertIn('Conecta el iPhone', w.diagnostic_fields['connection_detail'].text())
        w.set_connection_status(True, 'Conectado por USB')
        self.assertIn('AFC', w.diagnostic_fields['connection_detail'].text())

    def test_app_files_breadcrumbs_navigate_and_translate_live(self):
        w = self.window
        w.navigate(4)
        w.app_current_bundle = 'org.videolan.vlc-ios'
        w.app_action_result({
            'action': 'list_folder',
            'bundle_id': 'org.videolan.vlc-ios',
            'relative': 'Videos/Clips',
            'entries': [
                {'name': 'Demo.mp4', 'relative': 'Videos/Clips/Demo.mp4', 'kind': 'file', 'size': 4096, 'modified': datetime(2026, 5, 1, 12, 0)},
            ],
        })
        APP.processEvents()
        crumbs = [w.app_breadcrumbs.itemAt(i).widget() for i in range(w.app_breadcrumbs.count()) if isinstance(w.app_breadcrumbs.itemAt(i).widget(), QPushButton)]
        self.assertEqual([c.text() for c in crumbs], ['Documentos', 'Videos', 'Clips'])
        self.assertTrue(crumbs[0].isEnabled())
        self.assertTrue(crumbs[1].isEnabled())
        self.assertFalse(crumbs[2].isEnabled())

        with patch.object(w, 'load_app_folder') as load:
            crumbs[0].click()
            load.assert_called_once_with('')
            load.reset_mock()
            crumbs[1].click()
            load.assert_called_once_with('Videos')

        w.language_choice.setCurrentIndex(1)
        APP.processEvents()
        crumbs_en = [w.app_breadcrumbs.itemAt(i).widget() for i in range(w.app_breadcrumbs.count()) if isinstance(w.app_breadcrumbs.itemAt(i).widget(), QPushButton)]
        self.assertEqual([c.text() for c in crumbs_en], ['Documents', 'Videos', 'Clips'])

    def test_bottom_status_bar_adapts_to_active_page_when_idle(self):
        w = self.window
        w.activity_message = ''
        w.navigate(1)
        self.assertIn('apariencia', w.status.text().casefold())
        w.navigate(3)
        self.assertIn('usb', w.status.text().casefold())
        w.navigate(4)
        self.assertIn('apps', w.status.text().casefold())
        w.navigate(2)
        self.assertEqual(w.status.text(), 'Sin canciones para importar.')

    def test_lightweight_redesign_status_badges_and_single_primary_import_cta(self):
        from importios.models import StatusBadgeDelegate
        w = self.window
        self.assertIsInstance(w.table.itemDelegateForColumn(6), StatusBadgeDelegate)
        self.assertEqual(w.import_choose.objectName(), 'primary')
        w.accept_track({
            'id': 'q1', 'filename': 'a.mp3', 'path': '/tmp/a.mp3',
            'title': 'Pista', 'artist': 'Artista', 'album': 'Disco',
            'format': 'MP3', 'duration': 60.0, 'size': 1024,
        })
        w.update_buttons()
        self.assertEqual(w.import_choose.objectName(), '')
        self.assertEqual(w.import_submit.objectName(), 'primary')
        w.clear_tracks()
        self.assertEqual(w.import_choose.objectName(), 'primary')
        # Diagnostics 2x2 footer stays within 720px height without clipping.
        w.navigate(3)
        APP.processEvents()
        self.assertLessEqual(w.copy_diagnostic.geometry().bottom(), 700)

    def test_apple_music_visual_style_applies_palette_thumbnails_and_persists(self):
        w = self.window
        self.assertEqual(w.style_choice.currentIndex(), 0)
        self.assertEqual(w.colors['orange'], '#f27620')

        # Switch to Apple Music visual style in dark and light modes
        w.style_choice.setCurrentIndex(1)
        APP.processEvents()
        self.assertEqual(w.colors['orange'], '#fa233b')
        self.assertEqual(w.colors['card'], '#1c1c1e')
        self.assertTrue(w.library_table.property('appleMusic'))
        self.assertTrue(w.use_accent.isHidden())

        w.theme_choice.setCurrentIndex(1)  # Claro
        APP.processEvents()
        self.assertEqual(w.colors['orange'], '#fa233b')
        self.assertEqual(w.colors['bg'], '#f5f5f7')
        self.assertEqual(w.colors['card'], '#ffffff')
        self.assertTrue(w.library_table.property('appleMusic'))

        # Verify thumbnails differ between TUPAQ and Apple Music styles
        tupaq_thumb = theme_thumbnail('dark', 'tupaq').toImage()
        apple_thumb = theme_thumbnail('dark', 'apple_music').toImage()
        self.assertNotEqual(tupaq_thumb, apple_thumb)

        # Switch back to TUPAQ
        w.style_choice.setCurrentIndex(0)
        w.theme_choice.setCurrentIndex(2)
        APP.processEvents()
        self.assertEqual(w.colors['orange'], '#f27620')
        self.assertFalse(w.library_table.property('appleMusic'))
        self.assertFalse(w.use_accent.isHidden())


