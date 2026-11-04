"""Verify visible songs with stat and bounded header reads, without audio copies."""
import io
import struct
import math
from mutagen.mp4 import MP4
from mutagen.mp3 import MPEGInfo
from .phone_paths import media_path


class HeaderStream(io.BytesIO):
    def __init__(self,data,size):super().__init__(data);self.virtual_size=size
    def seek(self,offset,whence=0):
        return super().seek(self.virtual_size+offset,0) if whence==2 else super().seek(offset,whence)


async def audio_details(afc,track):
    path=track.get('afc_path')
    if not path:return {}
    base,_,leaf=path.rpartition('/')
    if media_path(base,leaf)!=path:return {}
    from pymobiledevice3.services.afc import AfcFileNotFoundError
    try:stat=await afc.stat(path)
    except (FileNotFoundError,AfcFileNotFoundError):return {'usb_exists':False,'usb_details_read':True}
    size=stat.get('st_size')
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
    result={'size':size,'size_source':'usb','usb_exists':True,'usb_details_read':True,'format_label':None,'format_source':'header'}
    label=seconds=None
    try:
        header=await read(0,min(size,12))
        if header[:4] in (b'RIFF',b'FORM'):
            wave=header[:4]==b'RIFF' and header[8:12]==b'WAVE'
            aiff=header[:4]==b'FORM' and header[8:12] in (b'AIFF',b'AIFC')
            if wave or aiff:
                label='WAV' if wave else 'AIFF' if header[8:12]==b'AIFF' else 'AIFF-C'
                offset=12;byte_rate=data_size=None
                for _ in range(1024):
                    if offset+8>size:break
                    chunk=await read(offset,8);length=struct.unpack('<I' if wave else '>I',chunk[4:])[0]
                    if length>size-offset-8:break
                    if wave and chunk[:4]==b'fmt ' and 16<=length<=4096:
                        fmt=await read(offset+8,16);encoding,channels,rate,byte_rate=struct.unpack_from('<HHII',fmt)
                        if encoding not in (1,3) or not 0<channels<=32 or rate<=0:byte_rate=None
                    if wave and chunk[:4]==b'data':data_size=length
                    if wave and byte_rate and data_size is not None:seconds=data_size/byte_rate;break
                    if aiff and chunk[:4]==b'COMM' and length>=18:
                        comm=await read(offset+8,18);frames=struct.unpack_from('>I',comm,2)[0]
                        exponent=struct.unpack_from('>H',comm,8)[0];mantissa=struct.unpack_from('>Q',comm,10)[0]
                        rate=math.ldexp(mantissa,(exponent&0x7fff)-16383-63)
                        if rate>0 and not exponent&0x8000:seconds=frames/rate
                        break
                    offset+=8+length+(length&1)
        elif header[:4]==b'fLaC':
            label='FLAC'
            info=await read(4,38)
            if info[0]&127==0 and int.from_bytes(info[1:4],'big')==34:
                timing=int.from_bytes(info[14:22],'big');rate=(timing>>44)&0xfffff
                if rate:seconds=(timing&0xfffffffff)/rate
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
                        seconds=getattr(audio.info,'length',None)
                        label='M4A · ALAC' if codec=='alac' else 'M4A · AAC' if codec.startswith('mp4a') else 'M4P · protegido' if codec in ('drms','enca') else 'M4A'
                    break
                offset+=length
        else:
            offset=0
            if header[:3]==b'ID3' and len(header)>=10 and not any(byte&128 for byte in header[6:10]):
                offset=10+sum(byte<<shift for byte,shift in zip(header[6:10],(21,14,7,0)))
            if offset<size:
                frames=await read(offset,min(65536,size-offset))
                info=MPEGInfo(HeaderStream(frames,size-offset),offset=0)
                label='MP3';seconds=info.length
    except Exception:
        pass
    finally:
        await afc.fclose(handle)
    if label:result.update(format_label=label,format_source='header')
    if isinstance(seconds,(int,float)) and math.isfinite(seconds) and 0<seconds<=7*86400:
        result.update(duration=seconds,duration_source='header')
    return result
