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


async def verify(afc,after,entries):
    from ..transfers import read_remote
    for entry in entries:
        picture=entry.get('artwork')
        if not picture:continue
        wire=str(entry['track_id'])
        require(after['artwork_tracks'].get(wire)==picture['cache_id'],'verify-artwork-registration')
        track=after['tracks'][after['wire_to_item'][wire]]
        matched=False
        for path in track.get('artwork_paths',[]):
            try:
                _,digest,size=await read_remote(afc,path,limit=5*1024**2)
                if (digest,size)==(picture['id'],picture['size']):matched=True;break
            except Exception:
                continue
        require(matched,'verify-artwork-original')


def allocate_cache_id(reserved):
    candidate=max(reserved|{99})+1
    if candidate>0xffffffff:
        candidate=next((value for value in range(100,100+len(reserved)+1) if value not in reserved),None)
    require(candidate is not None and candidate<=0xffffffff,'artwork-cache-range')
    reserved.add(candidate)
    return candidate
