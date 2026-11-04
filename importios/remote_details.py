"""Verify visible songs with stat and bounded header reads, without audio copies."""
import io
import struct
from mutagen.mp4 import MP4
from .phone_paths import media_path


async def audio_details(afc,track):
    path=track.get('afc_path')
    if not path:return {}
    base,_,leaf=path.rpartition('/')
    if media_path(base,leaf)!=path:return {}
    stat=await afc.stat(path);size=stat.get('st_size')
    if stat.get('st_ifmt')!='S_IFREG' or type(size) is not int or not 0<size<=2*1024**3:return {}
    handle=await afc.fopen(path,'r');budget=8*1024**2+65536
    async def read(offset,length):
        nonlocal budget
        if offset<0 or length<0 or offset+length>size or length>budget:raise ValueError('header-bounds')
        budget-=length;await afc.fseek(handle,offset);data=bytearray()
        while len(data)<length:
            block=await afc.fread(handle,min(65536,length-len(data)))
            if not block or len(block)>length-len(data):raise ValueError('header-truncated')
            data.extend(block)
        return bytes(data)
    result={'size':size,'size_source':'usb','usb_details_read':True,'format_label':None,'format_source':'header'}
    label=None
    try:
        header=await read(0,min(size,12))
        if header[:4]==b'RIFF' and header[8:12]==b'WAVE':label='WAV'
        elif header[:4]==b'FORM' and header[8:12] in (b'AIFF',b'AIFC'):label='AIFF' if header[8:12]==b'AIFF' else 'AIFF-C'
        elif header[:4]==b'fLaC':label='FLAC'
        elif len(header)>=8 and header[4:8]==b'ftyp':
            label='M4A';offset=0;ftyp=b''
            for _ in range(1024):
                if offset+8>size:break
                atom=await read(offset,8);length,kind=struct.unpack('>I4s',atom);start=8
                if length==1:length=struct.unpack('>Q',await read(offset+8,8))[0];start=16
                elif length==0:length=size-offset
                if not start<=length<=size-offset:break
                if kind==b'ftyp' and length<=4096:ftyp=await read(offset,length)
                if kind==b'moov':
                    if ftyp and length<=8*1024**2:
                        audio=MP4(io.BytesIO(ftyp+await read(offset,length)))
                        codec=getattr(audio.info,'codec','')
                        label='M4A · ALAC' if codec=='alac' else 'M4A · AAC' if codec.startswith('mp4a') else 'M4P · protegido' if codec in ('drms','enca') else 'M4A'
                    break
                offset+=length
        else:
            offset=0
            if header[:3]==b'ID3' and len(header)>=10 and not any(byte&128 for byte in header[6:10]):
                offset=10+sum(byte<<shift for byte,shift in zip(header[6:10],(21,14,7,0)))
            if offset<size:
                frames=await read(offset,min(8192,size-offset))
                for pos in range(max(0,len(frames)-3)):
                    a,b,c=frames[pos:pos+3]
                    if a==255 and b&224==224 and (b>>3)&3!=1 and (b>>1)&3!=0 and c>>4!=15 and (c>>2)&3!=3:
                        label='MP3';break
    except Exception:
        pass
    finally:
        await afc.fclose(handle)
    if label:result.update(format_label=label,format_source='header')
    return result
