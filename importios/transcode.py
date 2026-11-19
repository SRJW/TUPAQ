"""Convert non-iOS audio formats (FLAC, OGG, Opus, WMA, etc.) to M4A (ALAC or AAC) without altering originals."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import mutagen
from mutagen.mp4 import MP4, MP4Cover

CONVERTIBLE_EXTENSIONS = {'.flac', '.ogg', '.oga', '.opus', '.wma', '.mka', '.webm'}


def find_ffmpeg(custom_path=None):
    """Locate ffmpeg binary from custom path, bundled resource, PATH, or common install folders."""
    candidates = []
    if custom_path:
        candidates.append(Path(custom_path))
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        candidates.append(Path(meipass) / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'))
    found = shutil.which('ffmpeg')
    if found:
        candidates.append(Path(found))
    if sys.platform == 'darwin':
        candidates.extend([Path('/opt/homebrew/bin/ffmpeg'), Path('/usr/local/bin/ffmpeg')])
    elif os.name == 'nt':
        local = Path(os.environ.get('LOCALAPPDATA', ''))
        candidates.extend([
            local / 'Microsoft' / 'WinGet' / 'Links' / 'ffmpeg.exe',
            Path('C:/ffmpeg/bin/ffmpeg.exe'),
        ])
    for path in candidates:
        try:
            if path and path.is_file():
                return str(path)
        except OSError:
            continue
    return None


def _extract_source_metadata(source_path):
    """Read tags, cover artwork, and embedded lyrics from FLAC/OGG/Opus/etc. via mutagen."""
    meta = {}
    try:
        audio = mutagen.File(source_path)
    except Exception:
        return meta
    if audio is None:
        return meta
    tags = audio.tags or {}

    def first(*keys):
        for key in keys:
            for candidate in (key, key.lower(), key.upper()):
                try:
                    value = tags.get(candidate)
                except (KeyError, ValueError):
                    value = None
                if value:
                    if hasattr(value, 'text'):
                        value = value.text
                    if isinstance(value, (list, tuple)):
                        value = value[0] if value else ''
                    text = str(value).strip()
                    if text:
                        return text
        return ''

    for field, keys in (
        ('title', ('title', 'TIT2', '\xa9nam')),
        ('artist', ('artist', 'TPE1', '\xa9ART')),
        ('album', ('album', 'TALB', '\xa9alb')),
        ('album_artist', ('albumartist', 'album_artist', 'TPE2', 'aART')),
        ('genre', ('genre', 'TCON', '\xa9gen')),
        ('composer', ('composer', 'TCOM', '\xa9wrt')),
        ('date', ('date', 'year', 'TDRC', 'TYER', '\xa9day')),
        ('tracknumber', ('tracknumber', 'TRCK')),
        ('tracktotal', ('tracktotal', 'totaltracks')),
        ('discnumber', ('discnumber', 'TPOS')),
        ('disctotal', ('disctotal', 'totaldiscs')),
        ('lyrics', ('lyrics', 'unsyncedlyrics', 'USLT', '\xa9lyr')),
    ):
        val = first(*keys)
        if val:
            meta[field] = val

    # Extract embedded artwork (FLAC pictures or METADATA_BLOCK_PICTURE).
    pictures = getattr(audio, 'pictures', None) or []
    if pictures:
        front = next((pic for pic in pictures if getattr(pic, 'type', 0) == 3), pictures[0])
        if getattr(front, 'data', None):
            meta['artwork'] = (bytes(front.data), str(getattr(front, 'mime', '') or ''))
    elif 'metadata_block_picture' in tags:
        import base64
        from mutagen.flac import Picture
        try:
            raw = base64.b64decode(tags['metadata_block_picture'][0])
            pic = Picture(raw)
            if pic.data:
                meta['artwork'] = (bytes(pic.data), str(pic.mime or ''))
        except Exception:
            pass
    return meta


def _parse_pair(primary, total_str=''):
    def positive(val):
        digits = str(val or '').strip()
        return int(digits) if digits.isdigit() and 0 < int(digits) <= 65535 else 0
    if '/' in str(primary or ''):
        left, _, right = str(primary).partition('/')
        num, tot = positive(left), positive(right)
    else:
        num, tot = positive(primary), positive(total_str)
    if num > 0:
        return (num, tot if tot >= num else 0)
    return None


def _apply_mp4_metadata(mp4_path, meta):
    audio = MP4(mp4_path)
    mapping = {
        'title': '\xa9nam',
        'artist': '\xa9ART',
        'album': '\xa9alb',
        'album_artist': 'aART',
        'genre': '\xa9gen',
        'composer': '\xa9wrt',
        'date': '\xa9day',
        'lyrics': '\xa9lyr',
    }
    for key, atom in mapping.items():
        if meta.get(key):
            audio[atom] = [meta[key]]
    trkn = _parse_pair(meta.get('tracknumber'), meta.get('tracktotal'))
    if trkn:
        audio['trkn'] = [trkn]
    disk = _parse_pair(meta.get('discnumber'), meta.get('disctotal'))
    if disk:
        audio['disk'] = [disk]
    if meta.get('artwork'):
        data, mime = meta['artwork']
        fmt = MP4Cover.FORMAT_PNG if 'png' in mime.lower() or data[:8] == b'\x89PNG\r\n\x1a\n' else MP4Cover.FORMAT_JPEG
        audio['covr'] = [MP4Cover(data, imageformat=fmt)]
    audio.save()


def convert_to_m4a(source_path, target_codec='alac', output_dir=None, ffmpeg_path=None):
    """Transcode a FLAC/OGG/Opus/etc. file to M4A (ALAC lossless or AAC 256k), preserving tags/cover/lyrics."""
    source = Path(source_path).resolve()
    if not source.is_file():
        raise ValueError('No se encontró el archivo original para convertir.')
    codec = (target_codec or 'alac').strip().lower()
    if codec not in ('alac', 'aac'):
        raise ValueError('El formato de destino debe ser ALAC o AAC.')
    binary = find_ffmpeg(ffmpeg_path)
    if not binary:
        raise ValueError(
            'Para convertir archivos FLAC u otros formatos necesita ffmpeg instalado '
            '(en Windows: winget install Gyan.FFmpeg; en Mac: brew install ffmpeg) '
            'o indicar su ruta en Preferencias.'
        )
    dest_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix='tupaq-convert-'))
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = source.stem or 'audio'
    destination = dest_dir / f'{stem}.m4a'
    counter = 1
    while destination.exists():
        counter += 1
        destination = dest_dir / f'{stem} ({counter}).m4a'

    command = [binary, '-y', '-v', 'error', '-i', str(source), '-vn', '-map', '0:a:0']
    if codec == 'alac':
        command += ['-c:a', 'alac']
    else:
        command += ['-c:a', 'aac', '-b:a', '256k']
    command += ['-movflags', '+faststart', str(destination)]

    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300, creationflags=creationflags)
    if result.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise ValueError('No se pudo convertir el audio con ffmpeg. Comprueba que el archivo no esté dañado.')

    meta = _extract_source_metadata(source)
    if meta:
        try:
            _apply_mp4_metadata(destination, meta)
        except Exception:
            pass
    return destination
