"""Search visible metadata and actual container/codec evidence."""
from pathlib import PurePosixPath


def format_aliases(track):
    label = (track.get('format_label') or track.get('format') or '').casefold()
    container = (track.get('container') or '').casefold()
    suffix = PurePosixPath(track.get('afc_path') or track.get('path') or '').suffix.casefold()
    aliases = set(label.replace('·', ' ').split())
    if container and not track.get('format_label'):
        aliases.add(container)
    if suffix and track.get('format_source') != 'header' and (not label or label == 'pcm'):
        aliases.add(suffix.lstrip('.'))
    if label.startswith('m4a'):
        aliases.add('m4a')
        if 'alac' in label:
            aliases.add('alac')
        if 'aac' in label:
            aliases.add('aac')
    if 'alac' in aliases and track.get('format_source') != 'header' and suffix in ('', '.m4a', '.alac'):
        aliases.add('m4a')
    if aliases & {'aiff', 'aif', 'aiff-c'}:
        aliases.update(('aiff', 'aif'))
    return aliases


def matches_format(track, query):
    tokens = [term.lstrip('.') for term in (query or '').casefold().replace('·', ' ').split() if term.lstrip('.')]
    if not tokens:
        return False
    aliases = format_aliases(track)
    return all(token in aliases for token in tokens)


def matches(track, query):
    aliases = format_aliases(track)
    text = ' '.join(str(track.get(key) or '') for key in ('title', 'artist', 'album')).casefold()
    return all(term in text or term.lstrip('.') in aliases for term in query.casefold().split())

