"""Private local snapshot used to bind a delta to the existing library."""
from contextlib import closing
from pathlib import Path
import sqlite3

from ..library import read_catalogue
from .protocol import require


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
        if {'item_pid','is_placeholder','is_library_added','has_non_purgeable_asset','is_supported_type'} <= state_columns and 'remote_location_id' in item_columns:
            states = {str(pid):(placeholder,added,asset,supported,remote) for pid,placeholder,added,asset,supported,remote in
                db.execute('''SELECT i.item_pid,s.is_placeholder,s.is_library_added,s.has_non_purgeable_asset,
                    s.is_supported_type,i.remote_location_id FROM item i JOIN item_state s ON s.item_pid=i.item_pid''')}
    return {'database':database,'primary':primary,'anchor':anchor,'ids':ids,'originals':originals,
            'wire_to_item':wire_to_item,'tracks':{t['id']:t for t in tracks},'artists':artist_groups,'albums':albums,
            'groups':groups,'states':states}


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
    for entry in entries:
        item_id = after['wire_to_item'].get(str(entry['track_id']))
        track = after['tracks'].get(item_id)
        require(track is not None and track.get('afc_path') == entry['destination'], 'verify-new-item')
        require(all(track[k] == entry['source'][k] for k in ('title','artist','album')), 'verify-new-metadata')
