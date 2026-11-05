"""Build cleanup targets only its own read-only mount and handles busy readers."""
import subprocess
import unittest
from unittest.mock import patch
from pathlib import Path
from scripts.build_desktop import detach_build_image,verify_build_image,ROOT


class BuildCleanupTests(unittest.TestCase):
    def test_verify_retries_transient_resource_error_without_skipping_verification(self):
        results=[subprocess.CompletedProcess([],1,'Resource temporarily unavailable'),subprocess.CompletedProcess([],0,'verified')]
        with patch('scripts.build_desktop.subprocess.run',side_effect=results) as run,patch('scripts.build_desktop.time.sleep') as pause:
            verify_build_image(ROOT/'dist'/'test.dmg');self.assertEqual(run.call_count,2);pause.assert_called_once_with(.5)
    def test_verify_rejects_invalid_images_immediately(self):
        with patch('scripts.build_desktop.subprocess.run',return_value=subprocess.CompletedProcess([],1,'invalid image')) as run,patch('scripts.build_desktop.time.sleep') as pause:
            with self.assertRaises(subprocess.CalledProcessError):verify_build_image(ROOT/'dist'/'test.dmg')
            self.assertEqual(run.call_count,1);pause.assert_not_called()

    def test_transient_busy_mount_retries_then_finishes_without_force(self):
        results=[subprocess.CompletedProcess([],1,'Resource busy'),subprocess.CompletedProcess([],0,'detached')]
        with patch('scripts.build_desktop.subprocess.run',side_effect=results) as run,patch('scripts.build_desktop.time.sleep') as pause,patch('scripts.build_desktop.checked_run') as force:
            detach_build_image(ROOT/'dist'/'mounted-dmg')
            self.assertEqual(run.call_count,2);pause.assert_called_once_with(.5);force.assert_not_called()
    def test_persistent_busy_mount_forces_only_the_owned_readonly_image(self):
        with patch('scripts.build_desktop.subprocess.run',return_value=subprocess.CompletedProcess([],1,'Resource busy')) as run,patch('scripts.build_desktop.time.sleep') as pause,patch('scripts.build_desktop.checked_run') as force:
            detach_build_image(ROOT/'dist'/'mounted-dmg')
            self.assertEqual(run.call_count,3);self.assertEqual(pause.call_count,2)
            force.assert_called_once_with(['hdiutil','detach','-force',str((ROOT/'dist'/'mounted-dmg').resolve())],check=True)
    def test_other_mounts_and_unrelated_failures_are_never_forced(self):
        with patch('scripts.build_desktop.subprocess.run',return_value=subprocess.CompletedProcess([],1,'Permission denied')) as run,patch('scripts.build_desktop.checked_run') as force:
            with self.assertRaises(ValueError):detach_build_image(Path('/Volumes/unrelated'))
            run.assert_not_called()
            with self.assertRaises(subprocess.CalledProcessError):detach_build_image(ROOT/'dist'/'mounted-dmg')
            self.assertEqual(run.call_count,1);force.assert_not_called()
