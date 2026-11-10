"""Create a local M4A/TTML experiment; never connects to an iPhone or Internet.

This converts line timestamps. It does not establish that Music supports
custom karaoke, and never invents word timestamps. No song is bundled.
"""
from pathlib import Path
import hashlib
import math
import re
import shutil
import struct
import tempfile
import xml.etree.ElementTree as ET

from mutagen.mp4 import MP4

MAX_FILE=256*1024*1024
MAX_TEXT=256*1024
NS='http://www.w3.org/ns/ttml'
TTP='http://www.w3.org/ns/ttml#parameter'


def full_hash(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def media_hash(path):
    """Hash mdat payloads exactly, independently of changed metadata/offsets."""
    path=Path(path);size=path.stat().st_size;digest=hashlib.sha256();total=0;offset=0
    with path.open('rb') as stream:
        while offset+8<=size:
            stream.seek(offset);length,kind=struct.unpack('>I4s',stream.read(8));header=8
            if length==1:
                raw=stream.read(8)
                if len(raw)!=8:raise ValueError('El contenedor de audio está truncado.')
                length=struct.unpack('>Q',raw)[0];header=16
            elif length==0:length=size-offset
            if length<header or offset+length>size:raise ValueError('El contenedor de audio no es válido.')
            if kind==b'mdat':
                remaining=length-header
                while remaining:
                    block=stream.read(min(1024*1024,remaining))
                    if not block:raise ValueError('El audio está truncado.')
                    digest.update(block);total+=len(block);remaining-=len(block)
            offset+=length
    if offset!=size or total==0:raise ValueError('No se reconoce el audio del contenedor.')
    return total,digest.hexdigest()


def ttml_from_lrc(text,duration_ms):
    if not isinstance(text,str) or len(text.encode('utf-8'))>MAX_TEXT:
        raise ValueError('La letra debe ser texto de hasta 256 KB.')
    records=[]
    for line in text.splitlines():
        if not line.strip():continue
        match=re.fullmatch(r'\[(\d{1,3}):(\d{2})(?:\.(\d{1,3}))?\] ?(.*)',line)
        if match is None:raise ValueError('Esta prueba necesita una letra LRC por líneas, con marcas [mm:ss.xx].')
        minutes,seconds,fraction,words=match.groups()
        if re.match(r'\[\d{1,3}:\d{2}',words):
            raise ValueError('Esta prueba admite una marca de tiempo por línea.')
        stamp=(int(minutes)*60+int(seconds))*1000+int((fraction or '').ljust(3,'0') or '0')
        if int(seconds)>=60 or stamp>duration_ms:raise ValueError('Una marca de tiempo queda fuera del audio.')
        if any(ord(c)<32 and c!='\t' for c in words):raise ValueError('La letra contiene caracteres no válidos para XML.')
        records.append((stamp,words))
    if not records or not any(words.strip() for _,words in records):raise ValueError('No hay líneas de letra para convertir.')
    if any(a[0]>=b[0] for a,b in zip(records,records[1:])):
        raise ValueError('Las marcas deben avanzar en el tiempo sin repetirse.')
    ET.register_namespace('',NS);ET.register_namespace('ttp',TTP)
    root=ET.Element('{'+NS+'}tt',{'{http://www.w3.org/XML/1998/namespace}lang':'en','{'+TTP+'}timeBase':'media'})
    def clock(ms):return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d}.{ms%1000:03d}'
    body=ET.SubElement(root,'{'+NS+'}body',{'dur':clock(duration_ms)});group=ET.SubElement(body,'{'+NS+'}div');count=0
    for index,(start,words) in enumerate(records):
        end=records[index+1][0] if index+1<len(records) else duration_ms
        if not words.strip():continue
        if end<=start:raise ValueError('La última línea no tiene duración dentro del audio.')
        paragraph=ET.SubElement(group,'{'+NS+'}p',{'begin':clock(start),'end':clock(end)})
        paragraph.text=words;count+=1
    payload=ET.tostring(root,encoding='utf-8',xml_declaration=True).decode('utf-8')
    if len(payload.encode('utf-8'))>MAX_TEXT:raise ValueError('La letra TTML supera el límite de 256 KB.')
    ET.fromstring(payload)
    return payload,count


def create_trial(source,target):
    source,target=Path(source).resolve(),Path(target).resolve()
    if source==target or target.exists():raise ValueError('Elige un nombre nuevo: no se sobrescribe ningún archivo.')
    if target.suffix.lower()!='.m4a':raise ValueError('Guarda la copia con extensión .m4a.')
    if not source.is_file() or not 0<source.stat().st_size<=MAX_FILE:raise ValueError('Elige un M4A de hasta 256 MB.')
    original_hash=full_hash(source);audio=MP4(source)
    if not (audio.info.codec=='alac' or audio.info.codec.startswith('mp4a.')):
        raise ValueError('La prueba admite M4A AAC o ALAC.')
    seconds=audio.info.length
    if not math.isfinite(seconds) or seconds<=0:raise ValueError('No se pudo leer la duración del audio.')
    values=(audio.tags or {}).get('\xa9lyr',[])
    if not values or not isinstance(values[0],str):raise ValueError('El archivo no tiene letra incrustada en ©lyr.')
    payload,count=ttml_from_lrc(values[0],round(seconds*1000));original_media=media_hash(source)
    with tempfile.TemporaryDirectory(prefix='tupaq-ttml-',dir=target.parent) as temporary:
        copy=Path(temporary)/'trial.m4a';shutil.copyfile(source,copy)
        prepared=MP4(copy);prepared.tags['\xa9lyr']=[payload]
        prepared.tags['\xa9nam']=[str(audio.tags.get('\xa9nam',[source.stem])[0])+' [Prueba TTML]']
        prepared.tags['\xa9alb']=[str(audio.tags.get('\xa9alb',['Sin álbum'])[0])+' [Prueba TUPAQ]']
        prepared.save();checked=MP4(copy)
        if checked.tags['\xa9lyr']!=[payload] or media_hash(copy)!=original_media:
            raise ValueError('La copia no superó la comprobación de audio y letra.')
        if any(checked.tags.get(key)!=value for key,value in audio.tags.items() if key not in ('\xa9lyr','\xa9nam','\xa9alb')):
            raise ValueError('La copia no conservó los demás metadatos y la carátula.')
        if full_hash(source)!=original_hash:raise ValueError('El original cambió durante la lectura.')
        created=False
        try:
            # Exclusive creation also refuses a file created after preflight.
            with target.open('xb') as stream:
                created=True
                with copy.open('rb') as content:shutil.copyfileobj(content,stream)
            if full_hash(target)!=full_hash(copy):raise ValueError('No se pudo comprobar la copia guardada.')
        except BaseException:
            if created:target.unlink(missing_ok=True)
            raise
    return {'lines':count,'audio_unchanged':True,'original_unchanged':True,'karaoke_verified':False}


def main():
    import argparse
    import tkinter as tk
    from tkinter import filedialog,messagebox
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-report',type=Path)
    args=parser.parse_args();root=tk.Tk();root.withdraw()
    try:
        if args.check_report:
            root.update();args.check_report.write_text('ttml-trial-ready',encoding='ascii');return
        source=filedialog.askopenfilename(parent=root,title='TUPAQ: elige el M4A original con letra LRC',filetypes=[('Audio M4A','*.m4a')])
        if not source:return
        path=Path(source)
        target=filedialog.asksaveasfilename(parent=root,title='Guardar copia de prueba TTML',initialdir=str(path.parent),
            initialfile=path.stem+' [Prueba TTML].m4a',defaultextension='.m4a',filetypes=[('Audio M4A','*.m4a')])
        if not target:return
        try:
            result=create_trial(source,target)
        except Exception as error:
            message=str(error) if isinstance(error,ValueError) else 'No se pudo crear la copia. Comprueba el archivo y la carpeta de destino.'
            messagebox.showerror('TUPAQ: copia no creada',message,parent=root);return
        messagebox.showinfo('TUPAQ: copia de prueba creada',
            f"Se guardó la copia con {result['lines']} líneas TTML.\n\nEl original, el audio y la carátula se conservan.\n\nImporta esta copia con TUPAQ preview.30 y comprueba su letra en Música del iPhone.\nEs una prueba: el karaoke todavía no está validado.\n\n"+str(target),parent=root)
    finally:root.destroy()


if __name__=='__main__':main()
