"""Read-only projection from supported local headers into ATC audio fields."""
from pathlib import Path
import math
import struct
import unicodedata
import mutagen

from ..audio import inspect_audio
from .protocol import require


def numbering(tags,id3_key,mp4_key):
    """Project optional numbering without inventing a position or changing tags."""
    value=tags.get(mp4_key)
    if isinstance(value,(list,tuple)) and value and isinstance(value[0],(list,tuple)):
        parts=value[0]
    else:
        value=tags.get(id3_key)
        if hasattr(value,'text'):value=value.text
        if isinstance(value,(list,tuple)):value=value[0] if value else ''
        label=str(value) if value is not None else ''
        parts=label.split('/',2) if len(label)<=4096 else []
    def positive_integer(value):
        value=str(value).strip()
        if not value or len(value)>4096 or not value.isdecimal():return None
        digits=''.join(str(unicodedata.decimal(c)) for c in value).lstrip('0')
        if not digits or len(digits)>5:return None
        number=int(digits)
        return number if number<=65535 else None
    position=positive_integer(parts[0]) if parts else None
    total=positive_integer(parts[1]) if len(parts)>1 else None
    # A total without a position, or smaller than it, is not a qualified pair.
    # Keep a valid position; omit only the unusable optional information.
    return position,total if position is not None and total is not None and total>=position else None


def inspect_source(path, expected_hash=None):
    path = Path(path).resolve()
    require(path.is_file() and 0 < path.stat().st_size <= 256*1024*1024, 'source-size')
    source = inspect_audio(path,path.name)
    require(expected_hash is None or source['id'] == expected_hash, 'source-changed')
    audio = mutagen.File(path)
    info, tags = audio.info, audio.tags or {}
    rate, channels = int(info.sample_rate), int(info.channels)
    require(rate > 0 and math.isfinite(info.length) and info.length > 0, 'source-timing')
    bits = int(getattr(info,'bits_per_sample',0))
    fmt = source['format']
    if fmt == 'ALAC':
        require(bits in (16,20,24,32) and channels in (1,2), 'alac-profile')
        code, kind, extension = 601, 'Apple Lossless audio file', '.m4a'
    elif fmt == 'MP3':
        require(info.layer == 3 and info.version in (1,2,2.5) and rate <= 48000 and channels in (1,2), 'mp3-profile')
        code, kind, extension = {1:301,2:302,2.5:303}[info.version], 'MPEG audio file', '.mp3'
    elif fmt == 'AAC':
        code = {'mp4a.40.2':502,'mp4a.40.5':508,'mp4a.40.29':509,'mp4a.40.42':1001}.get(info.codec)
        require(code is not None and 1 <= channels <= 8 and rate <= (192000 if code in (508,509) else 96000), 'aac-profile')
        kind, extension = 'AAC audio file', '.m4a'
    else:
        require(bits in (8,16,24) and channels in (1,2), 'pcm-profile')
        if fmt == 'WAV':
            require(info.audio_format == 1, 'wav-not-integer-pcm')
            kind, extension = 'WAV audio file', '.wav'
        else:
            with path.open('rb') as stream:
                header = stream.read(12)
                require(header[:4] == b'FORM' and header[8:] in (b'AIFF',b'AIFC'), 'aiff-header')
                if header[8:] == b'AIFC':
                    compressed = None
                    while stream.tell()+8 <= source['size']:
                        chunk = stream.read(8)
                        length = struct.unpack('>I',chunk[4:])[0]
                        require(length <= source['size']-stream.tell(), 'aiff-chunk')
                        if chunk[:4] == b'COMM':
                            require(length >= 22, 'aiff-comm')
                            compressed = stream.read(22)[18:22]
                            break
                        stream.seek(length+(length&1),1)
                    require(compressed in (b'NONE',b'sowt'), 'aiff-not-integer-pcm')
            kind, extension = 'AIFF audio file', '.aif'
        code = 701
    def text(*keys):
        for key in keys:
            value = tags.get(key)
            if value:
                if hasattr(value,'text'):
                    value = value.text
                if isinstance(value,(list,tuple)):
                    value = value[0]
                value = str(value)
                require(0 < len(value) <= 4096 and not any(ord(c)<32 for c in value), 'metadata-text')
                return value
        return ''
    source.update(title=text('TIT2','\xa9nam') or path.stem,
                  artist=text('TPE1','\xa9ART') or 'Sin artista', album=text('TALB','\xa9alb') or 'Sin álbum',
                  album_artist=text('TPE2','aART') or text('TPE1','\xa9ART') or 'Sin artista',
                  genre=text('TCON','\xa9gen'),composer=text('TCOM','\xa9wrt'),
                  path=str(path),sample_rate=rate,channels=channels,samples=round(info.length*rate),
                  audio_format=code,kind=kind,extension=extension,
                  bit_rate=round(rate*bits*channels/1000) if fmt in ('ALAC','WAV','AIFF') else round(info.bitrate/1000))
    require(source['samples'] > 0 and source['bit_rate'] > 0, 'source-timing')
    require(fmt != 'MP3' or source['bit_rate'] <= 320, 'mp3-bitrate')
    for keys, first, second in [(('TRCK','trkn'),'track_number','track_count'),(('TPOS','disk'),'disc_number','disc_count')]:
        for key,number in zip((first,second),numbering(tags,*keys)):
            if number is not None:source[key]=number
    year = text('TDRC','TYER','\xa9day')[:4]
    if year.isdigit() and 0 < int(year) <= 9999:
        source['year'] = int(year)
    return source
