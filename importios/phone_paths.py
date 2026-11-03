"""Accept catalogue audio paths only inside known shared Media audio roots."""
import re


def media_path(base, leaf):
    if not isinstance(base, str) or not isinstance(leaf, str):
        return None
    base = base.removeprefix('/')
    if not re.fullmatch(r'(?:iTunes_Control/Music/F[0-9]{2}|(?:Purchases|Downloads)(?:/[A-Za-z0-9_\-]{1,80}){0,3})', base):
        return None
    if '..' in leaf or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _.\-]{0,126}\.(?:m4a|mp3|wav|aif|aiff|flac|m4p)', leaf, re.I):
        return None
    return base+'/'+leaf
