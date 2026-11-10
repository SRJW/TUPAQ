"""Read embedded lyrics without modifying tags or declaring unknown ATC assets."""
import hashlib

TEXT_LIMIT=256*1024


def embedded_lyrics(tags):
    if not tags:return {'lyrics_embedded':False,'lyrics_kind':None,'lyrics_text':None}
    text=None;kind='plain'
    values=tags.get('\xa9lyr')
    if values:
        text=next((v for v in values if isinstance(v,str) and v.strip()),None)
    if text is None and hasattr(tags,'getall'):
        frames=tags.getall('USLT')
        text=next((f.text for f in frames if isinstance(f.text,str) and f.text.strip()),None)
        if text is None:
            for frame in tags.getall('SYLT'):
                words=[part[0] for part in frame.text if isinstance(part,(tuple,list)) and part and isinstance(part[0],str)]
                candidate=''.join(words)
                if candidate.strip():text=candidate;kind='timed';break
    if not isinstance(text,str) or not text.strip():
        return {'lyrics_embedded':False,'lyrics_kind':None,'lyrics_text':None}
    data=text.encode('utf-8',errors='replace')
    return {'lyrics_embedded':True,'lyrics_kind':kind,'lyrics_chars':len(text),
            'lyrics_text':text if len(data)<=TEXT_LIMIT else None,
            'lyrics_sha256':hashlib.sha256(data).hexdigest()}


def descriptor(tags):
    return {k:v for k,v in embedded_lyrics(tags).items() if k!='lyrics_text'}


def catalogue_lyrics(db):
    columns={row[1] for row in db.execute('PRAGMA table_info(lyrics)')}
    if not {'item_pid','lyrics'}<=columns:return None
    flags=[name for name in ('store_lyrics_available','time_synced_lyrics_available','downloaded_catalog_lyrics_available') if name in columns]
    fields=','.join(flags)
    rows=db.execute("SELECT item_pid,CASE WHEN typeof(lyrics)='text' AND length(trim(lyrics))>0 THEN 1 ELSE 0 END"+(','+fields if fields else '')+' FROM lyrics LIMIT 200001')
    return {str(row[0]):{'lyrics_registered':bool(row[1]),'lyrics_online_available':any(value==1 for value in row[2:])} for row in rows}


def state(track):
    if track.get('lyrics_registered'):return 'registered'
    if track.get('lyrics_embedded'):return 'embedded'
    if track.get('lyrics_online_available'):return 'online'
    return None


def label(track):
    from .i18n import tr
    if track.get('lyrics_registered') and track.get('lyrics_embedded'):return tr('Letra incluida y registrada en Música')
    if track.get('lyrics_registered'):return tr('Letra registrada en Música')
    if track.get('lyrics_embedded'):return tr('Letra incluida en el archivo; uso en Música no verificado')
    if track.get('lyrics_online_available'):return tr('Letra disponible en línea; no se ha comprobado su descarga')
    return tr('No se ha detectado letra')


def _checksum_probe(db):
    """Bounded, local, read-only hypotheses; never return lyrics or checksum values.

    Matches are observations about this catalogue, not a qualified USB contract.
    No whole-file/tag checksum is compared with a text checksum.
    """
    import zlib
    columns={row[1] for row in db.execute('PRAGMA table_info(lyrics)')}
    if not {'checksum','lyrics'}<=columns:return {'schema_available':False}
    counts={name:0 for name in ('crc32_utf8','adler32_utf8','crc32_utf16le','crc32_utf16be','md5_fold_utf16be')}
    checked=0;scanned=0
    rows=db.execute("SELECT checksum,lyrics FROM lyrics WHERE typeof(checksum)='integer' AND checksum!=0 AND typeof(lyrics)='text' AND length(lyrics) BETWEEN 1 AND 65536 LIMIT 33")
    for checksum,text in rows:
        scanned+=1
        if scanned>32:break
        if not -2**31<=checksum<=2**32-1:continue
        if not text.strip():continue
        checked+=1;expected=checksum&0xffffffff
        from .sync.lyrics import host_checksum
        for name,value in (
            ('crc32_utf8',zlib.crc32(text.encode('utf-8'))),
            ('adler32_utf8',zlib.adler32(text.encode('utf-8'))),
            ('crc32_utf16le',zlib.crc32(text.encode('utf-16le'))),
            ('crc32_utf16be',zlib.crc32(text.encode('utf-16be'))),
            ('md5_fold_utf16be',host_checksum(text))):
            counts[name]+=int(value==expected)
    return {'schema_available':True,'samples_checked':checked,'sample_limit':32,
            'more_samples_available':scanned>32,'algorithm_matches':counts,'usb_contract_verified':False}


def checksum_probe(db):
    # Optional research diagnostics must never prevent the library from loading.
    import sqlite3
    try:return _checksum_probe(db)
    except (sqlite3.Error,UnicodeError,ValueError,OverflowError):
        return {'probe_unavailable':True,'usb_contract_verified':False}
