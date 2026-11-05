"""Embed catalogue artwork only into an already verified local export copy."""
from pathlib import Path
import mutagen
from mutagen.id3 import APIC
from mutagen.mp4 import MP4,MP4Cover
from mutagen.mp3 import MP3
from mutagen.wave import WAVE
from mutagen.aiff import AIFF
from .artwork import image_info


def embed(path,data):
    if not data or len(data)>20*1024*1024 or not image_info(data):return False
    jpeg=data.startswith(b'\xff\xd8');png=data.startswith(b'\x89PNG\r\n\x1a\n')
    if not (jpeg or png):return False
    audio=mutagen.File(path)
    if not isinstance(audio,(MP3,MP4,WAVE,AIFF)):return False
    tags=audio.tags
    if tags and (tags.get('covr') or hasattr(tags,'getall') and tags.getall('APIC')):return False
    before=(audio.info.sample_rate,audio.info.channels,audio.info.length)
    if tags is None:audio.add_tags()
    if isinstance(audio,MP4):audio['covr']=[MP4Cover(data,imageformat=MP4Cover.FORMAT_JPEG if jpeg else MP4Cover.FORMAT_PNG)]
    else:audio.tags.add(APIC(encoding=3,mime='image/jpeg' if jpeg else 'image/png',type=3,desc='Cover',data=data))
    audio.save()
    after=mutagen.File(path)
    if (after.info.sample_rate,after.info.channels,after.info.length)!=before:raise ValueError('export-artwork-audio-changed')
    return True
