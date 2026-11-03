"""Fixed-request candidate signatures, ported from rustunes (MIT).

Source: fbiba/rustunes commit 057ee8fc9c9da65795a6f14497fc408c2fe23c76,
crates/music-protocol/src/protocol/signing.rs. Copyright (c) 2026 Feim Biba.
See third_party/rustunes-LICENSE.txt. No Apple DLL or 3uTools service is used.

Only the exact published request and reply envelope are supported. This does
not authenticate a reply, support Apple's other host requests, or establish
that a particular phone accepts a resulting signature. Session material must
never be logged, persisted, or reused after its corresponding session closes.
"""
import hashlib
import hmac

from Cryptodome.Cipher import AES

MAX_OPERATION_BYTES = 4 * 1024 * 1024
HOST_REQUEST = bytes.fromhex(
    '0101111111111111111111111111111111110440bc2785e0dbf166361e07980a'
    '5ea48dba95b3b8ea265d62aefea51bb7b190e0b77126290ad39bb13fecc08c25'
    'a9561c517ac11e64905da029e61bdfd0ba22c313')
_WRAP_KEY = bytes.fromhex('7776eb98ab6ce602e8e892e41ba7e915')
_KEY_XOR = bytes.fromhex('c6c7c4c5cacbc8c9cecfcccdb2b3b0b1')
_TAG_XOR = bytes.fromhex('f9fafbfcfdfefff0f1f2f3f4f5f6f7e8e9eaebec')


class FixedHostSession:
    __slots__ = ('__key', '__mask')

    def __init__(self, request, reply):
        if request != HOST_REQUEST:
            raise ValueError('Unsupported host request')
        if len(reply) != 83 or reply[:2] != b'\x01\x01' or reply[18] != 64:
            raise ValueError('Unsupported reply envelope')
        decoded = AES.new(b'\x95'*16, AES.MODE_CBC, reply[2:18]).decrypt(reply[19:83])
        raw = bytes(decoded[1+i] ^ decoded[39+i] ^ _KEY_XOR[i] for i in range(16))
        self.__key = AES.new(_WRAP_KEY, AES.MODE_ECB).encrypt(raw)
        self.__mask = bytes(decoded[18+i] ^ _TAG_XOR[i] for i in range(20))

    def sign(self, operation):
        if self.__key is None:
            raise ValueError('Session closed')
        if not 0 < len(operation) <= MAX_OPERATION_BYTES:
            raise ValueError('Operation must contain between 1 byte and 4 MiB')
        tag = hmac.new(self.__key, operation, hashlib.sha1).digest()
        return b'\x01' + bytes(a ^ b for a, b in zip(tag, self.__mask))

    def close(self):
        # Releases references; Python does not guarantee memory zeroization.
        self.__key = None
        self.__mask = None
