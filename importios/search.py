"""Search visible metadata and actual container/codec evidence."""
from pathlib import PurePosixPath

def matches(track,query):
    label=(track.get('format_label') or track.get('format') or '').casefold()
    suffix=PurePosixPath(track.get('afc_path') or track.get('path') or '').suffix.casefold()
    aliases=set(label.replace('·',' ').split())
    if suffix and (not label or label=='pcm'):aliases.add(suffix.lstrip('.'))
    if label.startswith('m4a'):aliases.update(('m4a','alac' if 'alac' in label else 'aac' if 'aac' in label else 'm4a'))
    if 'aiff' in aliases:aliases.add('aif')
    text=' '.join(str(track.get(key,'')) for key in ('title','artist','album')).casefold()
    return all(term in text or term.lstrip('.') in aliases for term in query.casefold().split())
