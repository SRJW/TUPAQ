"""Read iOS MediaLibrary playlists (read-only) and generate standard M3U8 files."""
from pathlib import Path
import sqlite3


def read_playlists(db):
    """Extract user-visible playlists and ordered item_pid lists from MediaLibrary SQLite."""
    try:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'container', 'container_item'} <= tables:
            return []
        c_cols = {row[1] for row in db.execute('PRAGMA table_info("container")')}
        ci_cols = {row[1] for row in db.execute('PRAGMA table_info("container_item")')}
        if 'container_pid' not in c_cols or not {'container_pid', 'item_pid'} <= ci_cols:
            return []
        name_col = 'name' if 'name' in c_cols else 'title' if 'title' in c_cols else None
        if not name_col:
            return []
        extra = []
        if 'is_hidden' in c_cols:
            extra.append('COALESCE(is_hidden, 0) = 0')
        if 'smart_is_folder' in c_cols:
            extra.append('COALESCE(smart_is_folder, 0) = 0')
        if 'distinguished_kind' in c_cols:
            # Exclude master library & built-in system containers (keep 0 = regular playlist).
            extra.append('COALESCE(distinguished_kind, 0) = 0')
        where = (' WHERE ' + ' AND '.join(extra)) if extra else ''
        order_col = 'position' if 'position' in ci_cols else 'rowid'
        containers = db.execute(
            f'SELECT container_pid, "{name_col}" FROM container{where} ORDER BY "{name_col}" COLLATE NOCASE, container_pid'
        ).fetchall()
        playlists = []
        for cid, name in containers:
            if not isinstance(name, str) or not name.strip():
                continue
            rows = db.execute(
                f'SELECT item_pid FROM container_item WHERE container_pid = ? ORDER BY "{order_col}", rowid',
                (cid,),
            ).fetchall()
            track_ids = [str(row[0]) for row in rows if row[0] is not None]
            if track_ids:
                playlists.append({'id': str(cid), 'name': name.strip(), 'track_ids': track_ids})
        return playlists
    except sqlite3.Error:
        return []


def write_m3u8(path, entries):
    """Write an UTF-8 M3U8 playlist file referencing exported relative paths."""
    lines = ['#EXTM3U']
    for item in entries:
        duration = int(round(item.get('duration') or 0))
        artist = item.get('artist') or 'Sin artista'
        title = item.get('title') or 'Sin título'
        rel = str(item['relative_path']).replace('\\', '/')
        lines.append(f'#EXTINF:{duration},{artist} - {title}')
        lines.append(rel)
    target = Path(path)
    target.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return target
