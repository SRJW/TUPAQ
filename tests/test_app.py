import http.client
import json
from pathlib import Path
import re
import shutil
import tempfile
import threading
import unittest

from importios.audio import inspect_audio
from importios.__main__ import MAX_FILE_SIZE, create_server


class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        for fixture in Path(__file__).with_name('fixtures').glob('*'):
            if fixture.suffix in {'.mp3', '.wav', '.aiff', '.m4a'}:
                shutil.copyfile(fixture, cls.folder/fixture.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_supported_formats(self):
        for filename, expected in [('sample.mp3', 'MP3'), ('sample.wav', 'WAV'),
                                   ('sample.aiff', 'AIFF'), ('sample.m4a', 'ALAC')]:
            with self.subTest(filename=filename):
                data = inspect_audio(self.folder/filename, filename)
                self.assertEqual(data['format'], expected)
                self.assertGreater(data['duration'], 0.9)
                self.assertLess(data['duration'], 1.2)
                self.assertGreater(data['size'], 0)
                self.assertEqual(len(data['id']), 64)

    def test_metadata_and_fingerprint(self):
        first = inspect_audio(self.folder/'sample.m4a', 'song.m4a')
        second = inspect_audio(self.folder/'sample.m4a', 'renamed.m4a')
        self.assertEqual(first['title'], 'Prueba áé')
        self.assertEqual(first['artist'], 'Importios')
        self.assertEqual(first['album'], 'Álbum')
        self.assertEqual(first['id'], second['id'])

    def test_reject_aac_disguised_as_alac(self):
        with self.assertRaisesRegex(ValueError, 'AAC'):
            inspect_audio(self.folder/'aac.m4a', 'audio.m4a')

    def test_reject_mismatched_extension(self):
        with self.assertRaisesRegex(ValueError, 'extensión'):
            inspect_audio(self.folder/'sample.wav', 'audio.mp3')

    def test_reject_corrupt_audio(self):
        path = self.folder/'bad.wav'
        path.write_bytes(b'not an audio file')
        with self.assertRaises(ValueError):
            inspect_audio(path, 'bad.wav')

    def test_http_workflow_and_access_controls(self):
        server = create_server()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port

        def request(method, path, body=None, headers=None):
            conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            try:
                conn.request(method, path, body=body, headers=headers or {})
                response = conn.getresponse()
                return response.status, response.read()
            finally:
                conn.close()

        try:
            status, page = request('GET', '/')
            self.assertEqual(status, 200)
            token = re.search(rb"const token = '([^']+)'", page)[1].decode()
            content = (self.folder/'sample.m4a').read_bytes()
            headers = {'X-Importios-Token': token, 'X-Filename': 'sample.m4a'}
            status, body = request('POST', '/api/inspect', content, headers)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['format'], 'ALAC')
            self.assertEqual(request('POST', '/api/inspect', content)[0], 403)
            self.assertEqual(request('GET', '/', headers={'Host': 'attacker.example'})[0], 403)
            self.assertEqual(request('POST', '/api/inspect', content,
                                     headers | {'Origin': 'https://attacker.example'})[0], 403)
            self.assertEqual(request('POST', '/api/transfer', b'', headers)[0], 404)
            status, _ = request('POST', '/api/inspect', b'', headers | {'Content-Length': str(MAX_FILE_SIZE+1)})
            self.assertEqual(status, 413)
            status, _ = request('POST', '/api/inspect', b'broken', headers | {'X-Filename': 'bad.wav'})
            self.assertEqual(status, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
