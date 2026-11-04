"""Read only artwork originals or bounded tag ranges through AFC.

Never downloads audio to render a cover, follows remote URLs, or writes to iOS.
"""
import asyncio
import io
import re
import struct

from mutagen.id3 import ID3
from mutagen.mp4 import MP4

from .artwork import thumbnail

IMAGE_LIMIT = 5*1024*1024
TAG_LIMIT = 8*1024*1024


def original_path(relative):
    if not isinstance(relative,str) or not re.fullmatch(r'[0-9a-f]{2}/[0-9a-f]{38}',relative):
        return None
    return 'iTunes_Control/iTunes/Artwork/Originals/'+relative


def catalogue_artwork(db):
    """Resolve track/album artwork, using only known columns and bounded rows."""
    required = {
        'artwork_token':{'entity_pid','entity_type','artwork_token','artwork_source_type','artwork_variant_type'},
        'artwork':{'artwork_token','artwork_source_type','artwork_variant_type','relative_path'},
    }
    for table,columns in required.items():
        if not columns <= {row[1] for row in db.execute(f'PRAGMA table_info({table})')}:
            return {}
    preferred = []
    columns = {row[1] for row in db.execute('PRAGMA table_info(best_artwork_token)')}
    if {'entity_pid','entity_type','available_artwork_token','artwork_variant_type'} <= columns:
        preferred = db.execute('''SELECT b.entity_pid,b.entity_type,a.relative_path FROM best_artwork_token b
            JOIN artwork a ON a.artwork_token=b.available_artwork_token AND a.artwork_variant_type=b.artwork_variant_type
            WHERE b.entity_type IN(0,4) ORDER BY a.artwork_source_type LIMIT 200001''').fetchall()
    rows = db.execute('''SELECT t.entity_pid,t.entity_type,a.relative_path FROM artwork_token t
        JOIN artwork a ON a.artwork_token=t.artwork_token AND a.artwork_source_type=t.artwork_source_type
        AND a.artwork_variant_type=t.artwork_variant_type WHERE t.entity_type IN(0,4)
        ORDER BY t.artwork_variant_type LIMIT 200001''').fetchall()
    if len(rows)+len(preferred)>200000:
        return {}
    result = {}
    for pid,kind,relative in preferred+rows:
        path = original_path(relative)
        if path:
            result.setdefault((str(pid),kind),path)
    return result


async def cover_for_track(afc, track, stopped=lambda:False,thumbnail_size=96):
    """At most 8 MiB of tags plus tiny headers, with all handles in mode r."""
    async def fetch(path, embedded=False):
        stat = await afc.stat(path)
        size = stat.get('st_size',-1)
        if stat.get('st_ifmt') != 'S_IFREG' or not 0 < size <= 2*1024**3:
            return None
        handle = await afc.fopen(path,'r')
        budget = TAG_LIMIT+65536
        async def read(offset,length):
            nonlocal budget
            if stopped() or length < 0 or offset < 0 or offset+length > size or length > budget:
                raise ValueError('artwork-bounds')
            budget -= length
            await afc.fseek(handle,offset)
            data = bytearray()
            while len(data) < length:
                if stopped():
                    raise asyncio.CancelledError()
                block = await afc.fread(handle,min(65536,length-len(data)))
                if not block or len(block)>length-len(data):
                    raise ValueError('artwork-truncated')
                data.extend(block)
            return bytes(data)
        try:
            if not embedded:
                return thumbnail(await read(0,size),thumbnail_size) if size <= IMAGE_LIMIT else None
            first = await read(0,min(12,size))
            if first.startswith(b'ID3'):
                if len(first)<10 or any(v&128 for v in first[6:10]):
                    return None
                tag_size = 10+sum(v << shift for v,shift in zip(first[6:10],(21,14,7,0)))
                if not 10 <= tag_size <= min(TAG_LIMIT,size):
                    return None
                return _id3_cover(await read(0,tag_size),thumbnail_size)
            if len(first)>=8 and first[4:8] == b'ftyp':
                offset, ftyp = 0, b''
                for _ in range(1024):
                    if offset+8>size or stopped():
                        return None
                    header = await read(offset,8)
                    length, kind = struct.unpack('>I4s',header)
                    header_size = 8
                    if length == 1:
                        length = struct.unpack('>Q',await read(offset+8,8))[0]
                        header_size = 16
                    elif length == 0:
                        length = size-offset
                    if not header_size <= length <= size-offset:
                        return None
                    if kind == b'ftyp' and length<=4096:
                        ftyp = await read(offset,length)
                    if kind == b'moov':
                        if length>TAG_LIMIT or not ftyp:
                            return None
                        audio = MP4(io.BytesIO(ftyp+await read(offset,length)))
                        covers = (audio.tags or {}).get('covr')
                        return thumbnail(bytes(covers[0]),thumbnail_size) if covers else None
                    offset += length
            if first[:4] in (b'RIFF',b'FORM'):
                endian = '<I' if first[:4] == b'RIFF' else '>I'
                offset = 12
                for _ in range(1024):
                    if offset+8>size or stopped():
                        return None
                    header = await read(offset,8)
                    length = struct.unpack(endian,header[4:])[0]
                    if length>size-offset-8:
                        return None
                    if header[:4].lower() == b'id3 ':
                        return _id3_cover(await read(offset+8,length)) if length<=TAG_LIMIT else None
                    offset += 8+length+(length&1)
            return None
        finally:
            await afc.fclose(handle)
    for path in track.get('artwork_paths',[]):
        if stopped():
            return None
        # Paths originate only in our validated catalogue resolver.
        prefix = 'iTunes_Control/iTunes/Artwork/Originals/'
        if not path.startswith(prefix) or original_path(path[len(prefix):]) != path:
            continue
        try:
            image = await fetch(path)
            if image:
                return image
        except Exception:
            continue
    path = track.get('afc_path')
    if path and not stopped():
        from .phone_paths import media_path
        base,_,leaf = path.rpartition('/')
        if media_path(base,leaf) == path:
            try:
                return await fetch(path,embedded=True)
            except Exception:
                return None
    return None


def _id3_cover(data,size=96):
    tags = ID3(io.BytesIO(data))
    pictures = tags.getall('APIC')
    if not pictures:
        return None
    picture = next((p for p in pictures if p.type == 3),pictures[0])
    return thumbnail(picture.data,size)
