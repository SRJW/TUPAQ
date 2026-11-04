import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock,patch
from importios.library import copy_catalogue,CatalogueChanging,LibraryError

class CatalogueRetryTests(unittest.TestCase):
    def test_continuously_busy_catalogue_stops_after_three_read_only_attempts(self):
        with tempfile.TemporaryDirectory() as root,patch('importios.library._copy_catalogue_once',new_callable=AsyncMock,side_effect=CatalogueChanging()) as read:
            with self.assertRaises(CatalogueChanging):asyncio.run(copy_catalogue(None,root))
            self.assertEqual(read.await_count,3);self.assertEqual(list(Path(root).iterdir()),[])

    def test_other_catalogue_errors_are_not_retried(self):
        with tempfile.TemporaryDirectory() as root,patch('importios.library._copy_catalogue_once',new_callable=AsyncMock,side_effect=LibraryError('Invalid schema')) as read:
            with self.assertRaises(LibraryError):asyncio.run(copy_catalogue(None,root))
            self.assertEqual(read.await_count,1)
