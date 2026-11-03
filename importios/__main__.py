"""Loopback-only application. No device write or transfer operation exists."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading
from urllib.parse import unquote, urlsplit
import webbrowser

from .audio import EXTENSIONS, inspect_audio

MAX_FILE_SIZE = 256 * 1024 * 1024


def create_server(port=0):
    token = secrets.token_urlsafe(32)
    page = Path(__file__).with_name('index.html').read_text(encoding='utf-8').replace('__TOKEN__', token)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            # Avoid logging filenames, music metadata or the access token.
            pass

        def reply(self, status, data, content_type='application/json; charset=utf-8'):
            body = data.encode('utf-8') if isinstance(data, str) else json.dumps(data).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self.valid_host():
                return self.reply(403, {'error': 'Acceso local no válido.'})
            if self.path == '/':
                self.reply(200, page, 'text/html; charset=utf-8')
            else:
                self.reply(404, {'error': 'Ruta no encontrada.'})

        def do_POST(self):
            self.close_connection = True
            expected_origin = f'http://127.0.0.1:{self.server.server_port}'
            if (not self.valid_host()
                or self.headers.get('X-Importios-Token') != token
                or self.headers.get('Origin') not in (None, expected_origin)):
                return self.reply(403, {'error': 'Acceso no autorizado.'})
            if self.path == '/api/shutdown':
                self.reply(200, {'closed': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if urlsplit(self.path).path != '/api/inspect':
                return self.reply(404, {'error': 'Ruta no encontrada.'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                return self.reply(400, {'error': 'Tamaño no válido.'})
            if not 0 < size <= MAX_FILE_SIZE:
                return self.reply(413, {'error': 'Elige un archivo de entre 1 byte y 256 MB.'})
            filename = unquote(self.headers.get('X-Filename', ''))
            suffix = Path(filename).suffix.lower()
            if suffix not in EXTENSIONS:
                return self.reply(400, {'error': 'Extensión no admitida.'})
            self.connection.settimeout(30)
            try:
                # Close before Mutagen opens it, including on Windows.
                with tempfile.TemporaryDirectory(prefix='importios-') as folder:
                    path = Path(folder) / ('audio' + suffix)
                    with path.open('wb') as output:
                        remaining = size
                        while remaining:
                            block = self.rfile.read(min(1024 * 1024, remaining))
                            if not block:
                                raise ValueError('La lectura del archivo quedó incompleta.')
                            output.write(block)
                            remaining -= len(block)
                    result = inspect_audio(path, filename)
                self.reply(200, result)
            except ValueError as error:
                self.reply(400, {'error': str(error)})
            except (OSError, TimeoutError):
                self.reply(500, {'error': 'No se pudo leer el archivo temporal. Inténtalo de nuevo.'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description='Importios: preparar música localmente')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    server = create_server(args.port)
    address = f'http://127.0.0.1:{server.server_port}'
    if sys.stdout is not None:
        print(f'Importios está abierto en {address}', flush=True)
        print('Solo prepara canciones. No conecta ni modifica el iPhone. Ctrl+C para cerrar.', flush=True)
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(address,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
