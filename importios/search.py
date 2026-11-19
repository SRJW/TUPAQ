"""Search visible metadata and actual container/codec evidence."""
from pathlib import PurePosixPath


FORMAT_EXTENSIONS = {
    'mp3': {'.mp3'},
    'm4a': {'.m4a', '.alac'},
    'aac': {'.m4a'},
    'alac': {'.m4a', '.alac'},
    'wav': {'.wav'},
    'aiff': {'.aif', '.aiff'},
}

SUFFIX_ALIASES = {
    '.mp3': {'mp3'},
    '.m4a': {'m4a'},
    '.alac': {'alac', 'm4a'},
    '.m4p': {'m4p'},
    '.wav': {'wav'},
    '.aif': {'aiff', 'aif'},
    '.aiff': {'aiff', 'aif'},
}

SUFFIX_COMPATIBLE = {
    '.mp3': {'mp3'},
    '.m4a': {'m4a', 'aac', 'alac'},
    '.alac': {'m4a', 'alac'},
    '.m4p': {'m4p'},
    '.wav': {'wav', 'pcm'},
    '.aif': {'aiff', 'aif', 'aiff-c', 'pcm'},
    '.aiff': {'aiff', 'aif', 'aiff-c', 'pcm'},
}


def suffix_matches_format(path, expected_format):
    key = (expected_format or '').strip().lstrip('.').casefold()
    allowed = FORMAT_EXTENSIONS.get(key)
    if not allowed:
        return True
    return PurePosixPath(path or '').suffix.casefold() in allowed


def format_aliases(track):
    label = (track.get('format_label') or track.get('format') or '').casefold()
    container = (track.get('container') or '').casefold()
    suffix = PurePosixPath(track.get('afc_path') or track.get('path') or '').suffix.casefold()
    from_header = track.get('format_source') == 'header'
    aliases = set(label.replace('·', ' ').split())
    if container and not track.get('format_label'):
        aliases.add(container)
    if suffix and not from_header and (not label or label == 'pcm'):
        aliases.add(suffix.lstrip('.'))
    if label.startswith('m4a'):
        aliases.add('m4a')
        if 'alac' in label:
            aliases.add('alac')
        if 'aac' in label:
            aliases.add('aac')
    if 'alac' in aliases and not from_header and suffix in ('', '.m4a', '.alac'):
        aliases.add('m4a')
    if aliases & {'aiff', 'aif', 'aiff-c'}:
        aliases.update(('aiff', 'aif'))
    if not from_header and suffix in SUFFIX_COMPATIBLE:
        compatible = SUFFIX_COMPATIBLE[suffix]
        if not (aliases & compatible):
            aliases = set(SUFFIX_ALIASES[suffix])
        else:
            aliases &= compatible
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

