"""Private local snapshot used to bind a delta to the existing library."""
from contextlib import closing
from pathlib import Path
import sqlite3
import unicodedata

from ..library import read_catalogue
from .protocol import ProtocolError,require


def metadata_differences(track, source):
    """Canonical Unicode equality only; never trim, casefold or lose accents."""
    def same(left,right):
        return isinstance(left,str) and isinstance(right,str) and unicodedata.normalize('NFC',left)==unicodedata.normalize('NFC',right)
    return [key for key in ('title','artist','album') if not same(track.get(key),source.get(key))]


def cache_id(token):
    if type(token) is int:value=token
    elif isinstance(token,str) and token.isascii() and token.isdigit() and len(token)<=20:value=int(token)
    else:return None
    return value if 0<=value<=0xffffffff else None


def snapshot(path):
    tracks = read_catalogue(path)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA trusted_schema=OFF')
        rows = db.execute('SELECT db_pid,primary_container_pid FROM db_info').fetchall()
        require(len(rows) == 1 and all(type(x) is int and x != 0 for x in rows[0]), 'catalogue-identity')
        database, primary = rows[0]
        anchors = db.execute("SELECT value FROM _MLDatabaseProperties WHERE key='MLSyncClientSyncAnchor'").fetchall()
        require(len(anchors) == 1 and str(anchors[0][0]).isdigit(), 'catalogue-anchor')
        anchor = int(anchors[0][0])
        require(0 < anchor < 0xffffffff, 'catalogue-anchor-range')
        # Wire IDs are item_store.sync_id, not the SQLite item_pid.
        wires = db.execute('SELECT item_pid,sync_id FROM item_store').fetchall()
        require(all(type(pid) is int and type(wire) is int for pid,wire in wires), 'catalogue-wire-id')
        wire_to_item = {str(wire):str(pid) for pid,wire in wires if wire}
        require(len(wire_to_item) == sum(wire != 0 for _,wire in wires), 'catalogue-wire-duplicates')
        ids = {database,primary}
        for table in ('item_store','album','album_artist'):
            ids.update(row[0] for row in db.execute(f'SELECT sync_id FROM {table}') if type(row[0]) is int)
        originals = {str(pid) for pid, in db.execute('SELECT item_pid FROM item')}
        artist_groups = {}
        for wire,name in db.execute('SELECT sync_id,album_artist FROM album_artist'):
            if wire and isinstance(name,str):
                artist_groups.setdefault(name,[]).append(wire)
        albums = {}
        for wire,name,artist in db.execute('''SELECT a.sync_id,a.album,aa.album_artist FROM album a
                LEFT JOIN album_artist aa ON aa.album_artist_pid=a.album_artist_pid'''):
            if wire and isinstance(name,str) and isinstance(artist,str):
                albums.setdefault((name,artist),[]).append(wire)
        groups = {str(wire):(album,artist) for wire,album,artist in db.execute('''
            SELECT s.sync_id,a.sync_id,aa.sync_id FROM item i
            JOIN item_store s ON s.item_pid=i.item_pid JOIN album a ON a.album_pid=i.album_pid
            JOIN album_artist aa ON aa.album_artist_pid=a.album_artist_pid''') if wire}
        state_columns = {row[1] for row in db.execute('PRAGMA table_info(item_state)')}
        item_columns = {row[1] for row in db.execute('PRAGMA table_info(item)')}
        states = {}
        artwork_ids = set()
        artwork_tokens=set()
        artwork_tracks = {}
        artwork_known = True
        for table in ('artwork','artwork_token'):
            columns = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
            if not {'artwork_token','artwork_source_type'} <= columns:
                artwork_known = False
                continue
            for token, in db.execute(f'SELECT artwork_token FROM {table} WHERE artwork_source_type=300'):
                # Existing references can be opaque, NULL, INTEGER or decimal TEXT.
                # Keep them unchanged; reserve every representable numeric alias.
                artwork_tokens.add((type(token).__name__,token))
                identifier=cache_id(token)
                if identifier is not None:artwork_ids.add(identifier)
        if artwork_known:
            item_to_wire = {item:wire for wire,item in wire_to_item.items()}
            for pid,token in db.execute('SELECT entity_pid,artwork_token FROM artwork_token WHERE artwork_source_type=300 AND entity_type=0'):
                wire = item_to_wire.get(str(pid))
                if wire is not None and cache_id(token) is not None:artwork_tracks[wire]=cache_id(token)
        dates_known = 'date_added' in item_columns
        dates = {str(pid):value for pid,value in db.execute('SELECT item_pid,date_added FROM item')} if dates_known else {}
        if {'item_pid','is_placeholder','is_library_added','has_non_purgeable_asset','is_supported_type'} <= state_columns and 'remote_location_id' in item_columns:
            states = {str(pid):(placeholder,added,asset,supported,remote) for pid,placeholder,added,asset,supported,remote in
                db.execute('''SELECT i.item_pid,s.is_placeholder,s.is_library_added,s.has_non_purgeable_asset,
                    s.is_supported_type,i.remote_location_id FROM item i JOIN item_state s ON s.item_pid=i.item_pid''')}
    return {'database':database,'primary':primary,'anchor':anchor,'ids':ids,'originals':originals,
            'wire_to_item':wire_to_item,'tracks':{t['id']:t for t in tracks},'artists':artist_groups,'albums':albums,
            'groups':groups,'states':states,'artwork_ids':artwork_ids,'artwork_known':artwork_known,
            'artwork_tokens':artwork_tokens,'artwork_tracks':artwork_tracks,'dates':dates,'dates_known':dates_known}


def verify_originals(before, after):
    require((before['database'],before['primary']) == (after['database'],after['primary']), 'verify-library-identity')
    require(before['originals'] <= after['originals'], 'verify-original-items-missing')
    for identifier, old in before['tracks'].items():
        new = after['tracks'].get(identifier)
        require(new is not None and all(old.get(k) == new.get(k) for k in ('title','artist','album','duration','afc_path')),
                'verify-original-music-changed')


def verify_before_after(before, after, entries):
    verify_originals(before,after)
    require(after['anchor'] == before['anchor']+1, 'verify-anchor')
    targets={after['wire_to_item'].get(str(entry['track_id'])) for entry in entries}
    if before['dates_known'] and after['dates_known']:
        require(all(after['dates'].get(pid)==value for pid,value in before['dates'].items() if pid not in targets),
                'verify-original-date-changed')
    verify_owned_entries(after,entries)


def verify_owned_entries(after,entries):
    for index,entry in enumerate(entries):
        item_id = after['wire_to_item'].get(str(entry['track_id']))
        track = after['tracks'].get(item_id)
        require(track is not None and track.get('afc_path') == entry['destination'], 'verify-new-item')
        differences=metadata_differences(track,entry['source'])
        if differences:
            raise ProtocolError('verify-new-metadata',{'entry_index':index+1,
                'metadata_fields':differences,'comparison':'unicode-nfc'})
        if entry.get('added_at') and after['dates_known']:
            value=after['dates'].get(item_id)
            require(type(value) in (int,float) and value>0 and
                    any(abs(value+offset-entry['added_at'])<=5 for offset in (0,978307200,-2082844800)), 'verify-added-date')
