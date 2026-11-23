"""Check GitHub Releases for newer TUPAQ versions without downloading or running binaries."""
import json
from pathlib import Path
import re
import ssl
import sys
import urllib.error
import urllib.request

from .version import VERSION

RELEASES_API = 'https://api.github.com/repos/SRJW/TUPAQ/releases?per_page=15'
ALLOWED_PREFIX = 'https://github.com/SRJW/TUPAQ/releases/'
_VERSION_RE = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)(?:-preview\.(\d+))?$')


def build_ssl_context():
    """Return an SSL context with bundled certifi and macOS system CAs for frozen apps."""
    ctx = ssl.create_default_context()
    candidates = []
    try:
        import certifi
        cafile = certifi.where()
        if cafile and Path(cafile).is_file():
            candidates.append(cafile)
    except Exception:
        pass
    if sys.platform == 'darwin' and Path('/etc/ssl/cert.pem').is_file():
        candidates.append('/etc/ssl/cert.pem')
    for cafile in candidates:
        try:
            ctx.load_verify_locations(cafile=cafile)
        except OSError:
            continue
    return ctx


def parse_version(text):
    """Return a comparable tuple where stable release > preview of same version."""
    match = _VERSION_RE.fullmatch((text or '').strip())
    if not match:
        return None
    major, minor, patch, preview = match.groups()
    if preview is None:
        return (int(major), int(minor), int(patch), 1, 0)
    return (int(major), int(minor), int(patch), 0, int(preview))


def is_newer(candidate, current=VERSION):
    left, right = parse_version(candidate), parse_version(current)
    return left is not None and right is not None and left > right


def select_latest_release(releases, current=VERSION):
    """Pick the highest valid release tag with a trusted GitHub Releases URL."""
    best = None
    best_key = None
    for item in releases or []:
        if not isinstance(item, dict) or item.get('draft'):
            continue
        tag = str(item.get('tag_name') or '').strip()
        url = str(item.get('html_url') or '').strip()
        key = parse_version(tag)
        if key is None or not url.startswith(ALLOWED_PREFIX):
            continue
        if best_key is None or key > best_key:
            best_key = key
            best = {
                'tag': tag,
                'version': tag.lstrip('v'),
                'url': url,
                'prerelease': bool(item.get('prerelease')),
                'published_at': str(item.get('published_at') or ''),
                'assets': [
                    {'name': str(a.get('name') or ''), 'url': str(a.get('browser_download_url') or '')}
                    for a in (item.get('assets') or [])
                    if isinstance(a, dict) and str(a.get('browser_download_url') or '').startswith(ALLOWED_PREFIX)
                ],
            }
    if best is None:
        return {'available': False, 'current': current}
    return {
        'available': is_newer(best['tag'], current),
        'current': current,
        **best,
    }


def check_for_updates(current=VERSION, timeout=10):
    """Query GitHub Releases over HTTPS; never downloads installers automatically."""
    request = urllib.request.Request(
        RELEASES_API,
        headers={'Accept': 'application/vnd.github+json', 'User-Agent': f'TUPAQ/{current}'},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=build_ssl_context()) as response:
            payload = json.loads(response.read(1024 * 1024).decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
        raise RuntimeError('No se pudo comprobar si hay actualizaciones en GitHub.') from error
    if not isinstance(payload, list):
        raise RuntimeError('Respuesta de actualizaciones no reconocida.')
    return select_latest_release(payload, current=current)
