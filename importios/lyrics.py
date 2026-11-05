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
