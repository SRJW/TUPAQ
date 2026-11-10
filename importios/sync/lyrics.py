"""Independent implementation of the native USB plain-lyrics payload.

AMPDevicesAgent 1.7.0.155: checksum RVA 32f2ac, UTF-8 serializer 32f4f8,
USB dispatch 466da8 and filename 47d118. See docs/LETRAS-INVESTIGACION.md.
No Apple binary is loaded or distributed. Device UI confirmation is separate
from verification of the text registered in its catalogue.
"""
import hashlib
import struct
from pathlib import Path

from .protocol import require

MAX_TEXT_BYTES=256*1024


def host_checksum(text):
    """MD5 of exact UTF-16BE units, XOR its four big-endian words.

    No BOM, trailing NUL, newline conversion, trimming or normalization.
    The native routine returns 0 for an empty string and maps a nonempty
    XOR result of 0 to 1. MD5 is a compatibility checksum, not security.
    """
    if not isinstance(text,str):raise TypeError('lyrics-text-type')
    if len(text)>MAX_TEXT_BYTES or len(text.encode('utf-8'))>MAX_TEXT_BYTES:
        raise ValueError('lyrics-text-size')
    if not text:return 0
    digest=hashlib.md5(text.encode('utf-16be'),usedforsecurity=False).digest()
    result=0
    for word in struct.unpack('>4I',digest):result ^= word
    return result or 1


def prepare(source,directory):
    """Extract exact bounded text; keep it out of journals and diagnostics."""
    import mutagen
    from ..lyrics import embedded_lyrics
    if not source.get('send_lyrics',True):return None
    audio=mutagen.File(source['path'])
    result=embedded_lyrics(audio.tags if audio is not None else None)
    if not result['lyrics_embedded']:return None
    text=result['lyrics_text']
    require(isinstance(text,str),'lyrics-source-size')
    try:
        data=text.encode('utf-8');checksum=host_checksum(text)
    except (UnicodeError,ValueError):
        require(False,'lyrics-source-encoding')
    require(0<len(data)<=MAX_TEXT_BYTES and checksum!=0,'lyrics-source-size')
    digest=hashlib.sha256(data).hexdigest()
    folder=Path(directory);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=folder/(digest+'.txt')
    if not path.exists():
        with path.open('xb') as stream:stream.write(data)
        path.chmod(0o600)
    require(path.read_bytes()==data,'lyrics-source-changed')
    return {'path':str(path),'id':digest,'size':len(data),'checksum':checksum,'kind':'plain',
            'source_kind':result['lyrics_kind']}


def catalogue_records(db):
    """Private comparison evidence, without retaining the lyrics themselves."""
    columns={row[1] for row in db.execute('PRAGMA table_info(lyrics)')}
    if not {'item_pid','checksum','lyrics'}<=columns:return None
    records={}
    for pid,checksum,text in db.execute('SELECT item_pid,checksum,lyrics FROM lyrics'):
        require(str(pid) not in records,'lyrics-catalogue-duplicate')
        try:data=text.encode('utf-8') if isinstance(text,str) else None
        except UnicodeError:data=None
        records[str(pid)]={'checksum':checksum&0xffffffff if type(checksum) is int else None,
                          'id':hashlib.sha256(data).hexdigest() if data is not None else None,
                          'size':len(data) if data is not None else None}
    return records


def verify(snapshot,entry,item_id):
    expected=entry.get('lyrics')
    if expected is None:return
    actual=(snapshot.get('lyrics_records') or {}).get(item_id)
    require(actual is not None and all(actual.get(key)==expected.get(key) for key in ('checksum','id','size')),
            'verify-lyrics-registration')
