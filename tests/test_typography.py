"""Show the resolved font truthfully; never label a fallback as San Francisco."""
import unittest
from unittest.mock import patch
from PySide6.QtGui import QFont,QFontInfo
from test_native_connection import APP
from importios.typography import configure

class TypographyTests(unittest.TestCase):
    def test_native_font_status_matches_actual_resolution(self):
        status=configure(APP);actual=QFontInfo(APP.font()).family()
        if not APP.typography_is_apple:self.assertIn(actual,status);self.assertIn('fuente del sistema',status)
        self.assertEqual(APP.font().pixelSize(),13)

    def test_reset_removes_previous_application_font(self):
        APP.typography_font_id=777
        with patch('importios.typography.QFontDatabase.removeApplicationFont') as remove:
            configure(APP)
            remove.assert_called_once_with(777)
        self.assertIsNone(APP.typography_font_id)

    def test_mac_fallback_is_never_mislabelled_as_san_francisco(self):
        # Force the resolved family: DejaVu is absent on stock macOS, where
        # requesting it may legitimately resolve to San Francisco instead.
        with patch('importios.typography.sys.platform','darwin'),patch('importios.typography.QFontInfo') as resolved:
            resolved.return_value.family.return_value='Helvetica'
            status=configure(APP)
            self.assertFalse(APP.typography_is_apple)
            self.assertIn('Helvetica',status);self.assertFalse(status.startswith('San Francisco'))
        configure(APP)

    def test_mac_ignores_saved_custom_file_and_family(self):
        with patch('importios.typography.sys.platform','darwin'),patch('importios.typography.QFontDatabase.addApplicationFont') as load:
            configure(APP,'missing-font.ttf','unavailable custom family')
            load.assert_not_called();self.assertIsNone(APP.typography_font_path)
        configure(APP)

    def test_invalid_file_does_not_remove_existing_font_or_change_application(self):
        original=APP.font();APP.typography_font_id=777
        with patch('importios.typography.sys.platform','win32'),patch('importios.typography.QFontDatabase.removeApplicationFont') as remove:
            with self.assertRaises(ValueError):configure(APP,'/missing/font.otf')
            remove.assert_not_called();self.assertEqual(APP.font(),original)
        APP.typography_font_id=None;configure(APP)
