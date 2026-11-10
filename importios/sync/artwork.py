"""Prepare one bounded front cover as a separate native Artwork asset."""
import hashlib
from pathlib import Path

from PySide6.QtCore import QByteArray,QBuffer,QIODevice,QSize,Qt
from PySide6.QtGui import QImageReader

from ..audio import read_artwork
from .protocol import require


def prepare(path,directory,container):
    data=read_artwork(path)
    if not data:return None
    require(len(data)<=5*1024**2,'artwork-image-size')
    source=QBuffer();source.setData(QByteArray(data));source.open(QIODevice.OpenModeFlag.ReadOnly)
    reader=QImageReader(source);size=reader.size()
    require(size.isValid() and size.width()*size.height()<=16_000_000,'artwork-image-profile')
    reader.setScaledSize(size.scaled(QSize(1600,1600),Qt.AspectRatioMode.KeepAspectRatio))
    image=reader.read();require(not image.isNull(),'artwork-image-profile')
    # Native Artwork is a JPEG asset. Keep a valid JPEG untouched; project PNG
    # into JPEG for this separate asset without rewriting the audio original.
    if not data.startswith(b'\xff\xd8'):
        output=QBuffer();output.open(QIODevice.OpenModeFlag.WriteOnly)
        require(image.save(output,'JPEG',90),'artwork-image-profile')
        data=bytes(output.data())
    require(0<len(data)<=5*1024**2,'artwork-image-size')
    digest=hashlib.sha256(data).hexdigest()
    directory=Path(directory);directory.mkdir(mode=0o700,exist_ok=True)
    destination=directory/(digest+'.jpg')
    if destination.exists():require(destination.read_bytes()==data,'artwork-local-collision')
    else:
        with destination.open('xb') as output:output.write(data)
        destination.chmod(0o600)
    # One projected picture: complete MP4 data atom adds 16 bytes; ID3 +1.
    return {'path':str(destination),'id':digest,'size':len(data),'checksum':len(data)+(17 if container=='M4A' else 1)}


def originals(db):
    """Exact local-cache candidates, independent of the display cover policy.

    Source 300's decimal token is the announced cache ID. artwork_type 1/6
    describes track/album use; matching it to artwork_token's type is invalid.
    See rustunes docs/04, sections 10.3-10.4. Only original variant 0 is used.
    """
    from .catalogue import cache_id
    from ..remote_artwork import original_path
    columns={row[1] for row in db.execute('PRAGMA table_info(artwork)')}
    if not {'artwork_token','artwork_source_type','artwork_variant_type','relative_path'} <= columns:return {}
    rows=db.execute('SELECT artwork_token,relative_path FROM artwork WHERE artwork_source_type=300 AND artwork_variant_type=0 LIMIT 200001').fetchall()
    if len(rows)>200000:return {}
    result={}
    for token,relative in rows:
        identifier=cache_id(token);path=original_path(relative)
        if identifier is not None and path:
            result.setdefault(identifier,set()).add(path)
    return {key:sorted(paths) for key,paths in result.items()}


async def verify(afc,after,entries):
    from ..transfers import read_remote
    from .protocol import ProtocolError
    for index,entry in enumerate(entries):
        picture=entry.get('artwork')
        if not picture:continue
        wire=str(entry['track_id'])
        require(after['artwork_tracks'].get(wire)==picture['cache_id'],'verify-artwork-registration')
        # Never use best_artwork_token or album previews to verify our upload.
        paths=after.get('artwork_originals',{}).get(picture['cache_id'],[])
        matched=False;readable=0;different=0
        for path in paths if len(paths)==1 else []:
            try:
                _,digest,size=await read_remote(afc,path,limit=5*1024**2)
                readable+=1
                if (digest,size)==(picture['id'],picture['size']):matched=True;break
                different+=1
            except Exception:
                continue
        if not matched:
            raise ProtocolError('verify-artwork-original',{'entry_index':index+1,
                'path_candidates':len(paths),'readable_candidates':readable,'different_candidates':different,
                'lookup':'local-cache-original'})


def allocate_cache_id(reserved):
    candidate=max(reserved|{99})+1
    if candidate>0xffffffff:
        candidate=next((value for value in range(100,100+len(reserved)+1) if value not in reserved),None)
    require(candidate is not None and candidate<=0xffffffff,'artwork-cache-range')
    reserved.add(candidate)
    return candidate
