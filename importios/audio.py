"""Read actual audio headers; extensions alone never establish compatibility."""

import hashlib
from pathlib import Path

import mutagen
from mutagen.aiff import AIFF
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE

EXTENSIONS = {'.mp3', '.wav', '.m4a', '.alac', '.aif', '.aiff'}


def inspect_audio(path, filename):
    name = filename.replace('\\', '/').rsplit('/', 1)[-1]
    suffix = Path(name).suffix.lower()
    if suffix not in EXTENSIONS:
        raise ValueError('Formato no admitido. Elige MP3, WAV, M4A o AIFF.')
    try:
        audio = mutagen.File(path)
    except (mutagen.MutagenError, OSError, ValueError) as error:
        raise ValueError('No se pudo leer el audio. El archivo puede estar dañado.') from error
    if isinstance(audio, MP3):
        fmt, extensions = 'MP3', {'.mp3'}
    elif isinstance(audio, WAVE):
        fmt, extensions = 'WAV', {'.wav'}
    elif isinstance(audio, AIFF):
        fmt, extensions = 'AIFF', {'.aif', '.aiff'}
    elif isinstance(audio, MP4):
        codec = getattr(audio.info, 'codec', '')
        if codec == 'alac':
            fmt, extensions = 'ALAC', {'.m4a', '.alac'}
        elif codec.startswith('mp4a'):
            fmt, extensions = 'AAC', {'.m4a'}
        else:
            raise ValueError('El códec de este archivo M4A no está admitido.')
    else:
        raise ValueError('El contenido no es MP3, WAV, M4A (AAC/ALAC) o AIFF.')
    if suffix not in extensions:
        raise ValueError(f'El contenido es {fmt}, pero la extensión no coincide.')
    tags = audio.tags or {}

    def tag(*keys):
        for key in keys:
            value = tags.get(key)
            if value:
                if hasattr(value, 'text'):
                    value = value.text
                if isinstance(value, (list, tuple)):
                    value = value[0] if value else ''
                return str(value)
        return ''

    with open(path, 'rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    year=tag('TDRC','TYER','\xa9day')[:4]
    from .lyrics import descriptor
    return {
        'id': digest,
        'filename': name,
        'title': tag('TIT2', '\xa9nam') or Path(name).stem,
        'artist': tag('TPE1', '\xa9ART'),
        'album': tag('TALB', '\xa9alb'),
        'format': fmt,
        'container': 'M4A' if isinstance(audio, MP4) else fmt,
        'duration': round(audio.info.length, 2),
        'sample_rate': getattr(audio.info, 'sample_rate', None),
        'bit_depth':getattr(audio.info,'bits_per_sample',None) if fmt in ('ALAC','WAV','AIFF') else None,
        'channels':getattr(audio.info,'channels',None),
        'bit_rate':getattr(audio.info,'bitrate',0)/1000 if getattr(audio.info,'bitrate',0) else None,
        'genre':tag('TCON','\xa9gen'),
        **({'year':int(year)} if len(year)==4 and year.isdigit() and 0<int(year)<=9999 else {}),
        'size': Path(path).stat().st_size,
        'has_artwork': bool(tags.get('covr')) or any(str(key).startswith('APIC') for key in tags),
        **descriptor(tags),
    }


def read_artwork(path,limit=5*1024*1024):
    """Read an embedded front cover within the requested byte limit; never modify tags."""
    try:
        audio = mutagen.File(path)
    except (mutagen.MutagenError, OSError, ValueError):
        return None
    tags = audio.tags if audio is not None else None
    if not tags:
        return None
    covers = tags.get('covr')
    if covers:
        data = covers[0]
    elif hasattr(tags, 'getall'):
        pictures = tags.getall('APIC')
        if not pictures:
            return None
        data = next((picture.data for picture in pictures if picture.type == 3), pictures[0].data)
    else:
        return None
    return bytes(data) if 0 < len(data) <= limit else None
