"""Exercise the actual frozen binary, including bundled HTML and audio parsers."""

import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    executable = Path(sys.argv[1]).resolve()
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    address = f'http://127.0.0.1:{port}'
    process = subprocess.Popen([str(executable), '--no-browser', '--port', str(port)])
    try:
        deadline = time.monotonic() + 90
        while True:
            if process.poll() is not None:
                raise RuntimeError(f'Application exited before readiness: {process.returncode}')
            try:
                with urllib.request.urlopen(address, timeout=2) as response:
                    page = response.read().decode('utf-8')
                break
            except (urllib.error.URLError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise RuntimeError('Application did not become ready')
                time.sleep(0.25)
        token = re.search("const token = '([^']+)'", page)[1]
        for filename, expected in [('sample.mp3', 'MP3'), ('sample.wav', 'WAV'),
                                   ('sample.aiff', 'AIFF'), ('sample.m4a', 'ALAC')]:
            request = urllib.request.Request(address+'/api/inspect',
                data=(ROOT/'tests'/'fixtures'/filename).read_bytes(),
                headers={'X-Importios-Token': token, 'X-Filename': filename})
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.load(response)
            assert result['format'] == expected, result
        request = urllib.request.Request(address+'/api/shutdown', data=b'',
            headers={'X-Importios-Token': token})
        with urllib.request.urlopen(request, timeout=5) as response:
            assert json.load(response)['closed']
        assert process.wait(timeout=15) == 0
        print('Packaged application passed: startup, bundled page, four audio formats, shutdown.')
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


if __name__ == '__main__':
    main()
