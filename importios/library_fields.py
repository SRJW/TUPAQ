"""Evidence-based display metadata; unknown values stay unknown."""
from pathlib import PurePosixPath


def format_label(code, path=None):
    suffix = PurePosixPath(path or '').suffix.lower()
    if suffix == '.m4p':
        return 'M4P · protegido' if code in (502,508,509,1001) else None
    if code in (301,302,303):
        return 'MP3' if suffix in ('','.mp3') else None
    if code == 601:
        return 'M4A · ALAC' if suffix in ('','.m4a','.alac') else None
    if code in (502,508,509,1001):
        if suffix in ('.m4a','.alac'):
            return 'M4A · AAC'
        return 'AAC' if suffix in ('','.aac') else None
    if code == 701:
        return {'':'PCM','.wav':'WAV','.aif':'AIFF','.aiff':'AIFF'}.get(suffix)
    return None


def local_tracks(tracks):
    """Do not collapse equal titles: only repeat references to the same file."""
    result,paths = [],set()
    for track in tracks:
        if track.get('usb_exists') is False:continue
        local = track.get('is_local')
        if local is False or (local is None and not track.get('afc_path')):
            continue
        path = track.get('afc_path')
        from .audio import EXTENSIONS
        if path and PurePosixPath(path).suffix.casefold() not in EXTENSIONS:continue
        if path and path in paths:
            continue
        if path:paths.add(path)
        result.append(track)
    return result
