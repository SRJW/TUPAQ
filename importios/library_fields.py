"""Evidence-based display metadata; unknown values stay unknown."""
from pathlib import PurePosixPath


def format_label(code, path=None):
    suffix = PurePosixPath(path or '').suffix.lower()
    if suffix == '.m4p' and code in (502,508,509,1001):
        return 'M4P · protegido'
    if code in (301,302,303):return 'MP3'
    if code == 601:return 'M4A · ALAC'
    if code in (502,508,509,1001):return 'M4A · AAC' if suffix in ('.m4a','.alac') else 'AAC'
    if code == 701:return {'.wav':'WAV','.aif':'AIFF','.aiff':'AIFF'}.get(suffix,'PCM')
    return None


def local_tracks(tracks):
    """Do not collapse equal titles: only repeat references to the same file."""
    result,paths = [],set()
    for track in tracks:
        local = track.get('is_local')
        if local is False or (local is None and not track.get('afc_path')):
            continue
        path = track.get('afc_path')
        if path and path in paths:
            continue
        if path:paths.add(path)
        result.append(track)
    return result
