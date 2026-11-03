"""Optional browser integration test: pip install playwright; requires Chromium and FFmpeg."""

import csv
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

from playwright.sync_api import sync_playwright, expect

from importios.__main__ import create_server


def main():
    server = create_server()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            files = []
            for filename, codec in [('song.mp3', 'libmp3lame'), ('song.wav', 'pcm_s16le'),
                                    ('song.aiff', 'pcm_s16be'), ('song.m4a', 'alac')]:
                path = folder/filename
                subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                                '-i', 'sine=frequency=440:duration=1', '-c:a', codec,
                                '-metadata', 'title=<img src=x onerror=alert(1)>',
                                '-metadata', 'artist=Artista de prueba', str(path)], check=True)
                files.append(str(path))
            duplicate = folder/'duplicate.mp3'
            shutil.copyfile(files[0], duplicate)
            bad = folder/'bad.wav'
            bad.write_bytes(b'broken')
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=shutil.which('chromium'), headless=True,
                                            args=['--no-sandbox'])
                page = browser.new_page(viewport={'width': 1280, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}')
                page.locator('#files').set_input_files(files + [str(duplicate), str(bad)])
                expect(page.locator('#status')).to_have_text('Añadidas: 4. Duplicadas omitidas: 1. No añadidas: 1.')
                expect(page.locator('#tracks tr')).to_have_count(4)
                expect(page.locator('#errors li')).to_have_count(1)
                expect(page.locator('#tracks img')).to_have_count(0)
                with page.expect_download() as download_info:
                    page.locator('#export').click()
                download = download_info.value
                rows = list(csv.reader(io.StringIO(Path(download.path()).read_text(encoding='utf-8-sig'))))
                assert len(rows) == 5
                assert {row[4] for row in rows[1:]} == {'MP3', 'WAV', 'AIFF', 'ALAC'}
                assert page.evaluate("csvValue('=1+1')") == '"\'=1+1"'
                page.locator('.remove').first.click()
                expect(page.locator('#tracks tr')).to_have_count(3)
                page.screenshot(path='/tmp/importios-desktop.png', full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                page.screenshot(path='/tmp/importios-mobile.png', full_page=True)
                page.locator('#clear').click()
                expect(page.locator('#count')).to_have_text('Sin canciones')
                expect(page.locator('#export')).to_be_disabled()
                assert not errors, errors
                browser.close()
                print('Browser smoke passed: 4 formats, metadata as text, deduplication, errors, CSV, remove, clear.')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()
