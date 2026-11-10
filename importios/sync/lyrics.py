"""Host-derived lyrics checksum; not an enabled USB delivery contract.

Static chain in the user's iTunes.dll SHA256 09c79c46...5cc7c8:
setter RVA f5c3da -> 9e0980 -> 9e0a30; stored at record+68 and announced
by RVA 26239f. This establishes the old host algorithm, not iOS 27 delivery.
See docs/LETRAS-INVESTIGACION.md. No DLL is loaded or distributed.
"""
import hashlib
import struct

MAX_TEXT_BYTES=256*1024


def host_checksum(text):
    """MD5 of exact UTF-16BE units, XOR its four big-endian words.

    No BOM, trailing NUL, newline conversion, trimming or normalization.
    The native routine returns 0 for an empty string and maps a nonempty
    XOR result of 0 to 1. MD5 is a compatibility checksum, not security.
    """
    if not isinstance(text,str):raise TypeError('lyrics-text-type')
    if len(text)>MAX_TEXT_BYTES or len(text.encode('utf-8'))>MAX_TEXT_BYTES:
        raise ValueError('lyrics-text-size')
    if not text:return 0
    digest=hashlib.md5(text.encode('utf-16be'),usedforsecurity=False).digest()
    result=0
    for word in struct.unpack('>4I',digest):result ^= word
    return result or 1
