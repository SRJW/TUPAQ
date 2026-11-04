"""Show the resolved font truthfully; never label a fallback as San Francisco."""
import unittest
from unittest.mock import patch
from PySide6.QtGui import QFont,QFontInfo
from test_native_connection import APP
from importios.typography import configure

class TypographyTests(unittest.TestCase):
    def test_native_font_status_matches_actual_resolution(self):
        status=configure(APP);actual=QFontInfo(APP.font()).family()
        if not APP.typography_is_apple:self.assertIn(actual,status);self.assertIn('no está disponible',status)
        self.assertEqual(APP.font().pixelSize(),13)

    def test_reset_removes_previous_application_font(self):
        APP.typography_font_id=777
        with patch('importios.typography.QFontDatabase.removeApplicationFont') as remove:
            configure(APP)
            remove.assert_called_once_with(777)
        self.assertIsNone(APP.typography_font_id)

    def test_mac_fallback_is_never_mislabelled_as_san_francisco(self):
        with patch('importios.typography.sys.platform','darwin'),patch('importios.typography.QFontDatabase.systemFont',return_value=QFont('DejaVu Sans')):
            status=configure(APP)
            self.assertFalse(APP.typography_is_apple)
            self.assertIn('no está disponible',status)
        configure(APP)
