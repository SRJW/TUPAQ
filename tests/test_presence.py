"""Directory inventories exclude deleted payloads without changing the phone."""
import asyncio
import unittest
from importios.presence import probe_files
from importios.library_fields import local_tracks

class PresenceTests(unittest.TestCase):
    def test_missing_audio_hidden_but_protected_download_without_usb_path_preserved(self):
        class AFC:
            calls=[]
            async def listdir(self,path):self.calls.append(path);return ['AAAA.mp3']
        afc=AFC();rows=[{'id':'one','is_local':True,'afc_path':'iTunes_Control/Music/F00/AAAA.mp3'},
                        {'id':'deleted','is_local':True,'afc_path':'iTunes_Control/Music/F00/BBBB.mp3'},
                        {'id':'protected','is_local':True}]
        diagnostics={};asyncio.run(probe_files(afc,rows,diagnostics))
        self.assertEqual([r['id'] for r in local_tracks(rows)],['one','protected'])
        self.assertEqual(len(afc.calls),1);self.assertEqual(diagnostics['usb_missing_references'],1)

    def test_unavailable_directory_does_not_claim_audio_is_deleted(self):
        class AFC:
            async def listdir(self,path):raise PermissionError('unavailable')
        rows=[{'is_local':True,'afc_path':'iTunes_Control/Music/F00/AAAA.mp3'}]
        asyncio.run(probe_files(AFC(),rows))
        self.assertNotIn('usb_exists',rows[0]);self.assertEqual(len(local_tracks(rows)),1)
