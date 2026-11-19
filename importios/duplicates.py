"""Detect duplicate tracks in the iPhone library and against the local import queue."""
import unicodedata


def _norm(text):
    raw = ''.join(
        c for c in unicodedata.normalize('NFKD', str(text or '')).casefold()
        if not unicodedata.combining(c)
    )
    return ' '.join(raw.split())


def track_signature(track):
    """Normalized (title, artist) key for approximate duplicate matching."""
    title = _norm(track.get('title'))
    artist = _norm(track.get('artist'))
    if artist in ('sin artista', 'unknown artist'):
        artist = ''
    return (title, artist)


def durations_close(left, right, tolerance=2.5):
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return True
    if left <= 0 or right <= 0:
        return True
    return abs(left - right) <= tolerance


def duplicate_ids_in_library(tracks):
    """Return set of track IDs that appear to be duplicated within the iPhone library."""
    by_sig = {}
    for track in tracks:
        sig = track_signature(track)
        if not sig[0]:
            continue
        by_sig.setdefault(sig, []).append(track)
    duplicates = set()
    for group in by_sig.values():
        if len(group) < 2:
            continue
        for i, first in enumerate(group):
            for second in group[i + 1:]:
                if durations_close(first.get('duration'), second.get('duration')):
                    duplicates.add(first['id'])
                    duplicates.add(second['id'])
    return duplicates


def matches_phone_library(local_track, phone_tracks):
    """Return True if a local import track already appears to exist on the iPhone."""
    sig = track_signature(local_track)
    if not sig[0]:
        return False
    duration = local_track.get('duration')
    for track in phone_tracks:
        if track_signature(track) == sig and durations_close(duration, track.get('duration')):
            return True
    return False
