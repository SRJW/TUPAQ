"""Synthetic packets only: these tests do not call 3uTools services."""
import binascii
import struct
import unittest

from research.packet import decode, processing_result


def fixture(payload, opcode=0xd1):
    return struct.pack('<IBBHI', 0x35467891, opcode, 0, binascii.crc_hqx(payload, 0), len(payload))+payload


class PacketTests(unittest.TestCase):
    def test_independent_crc_check_vector(self):
        # Standard CRC-16/XMODEM check value, not produced by the fixture helper.
        data = bytes.fromhex('91784635c900c33109000000') + b'123456789'
        self.assertEqual(decode(data).payload, b'123456789')

    def test_result_is_read_without_generation(self):
        payload = struct.pack('<I', 6)+b'opaque'
        self.assertEqual(processing_result(decode(fixture(payload))), b'opaque')

    def test_reject_corrupted_crc(self):
        with self.assertRaisesRegex(ValueError, 'CRC'):
            decode(fixture(b'original')[:-1]+b'X')

    def test_reject_truncation_and_trailing_data(self):
        original = fixture(b'data')
        for data in [b'', original[:11], original[:-1], original+b'X']:
            with self.subTest(data=data), self.assertRaises(ValueError):
                decode(data)

    def test_reject_bad_magic_and_oversized_declaration(self):
        for data in [b'xxxx'+fixture(b'data')[4:], struct.pack('<IBBHI', 0x35467891, 0xd1, 0, 0, 0xffffffff)]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                decode(data)

    def test_reject_unexpected_opcode_or_invalid_inner_length(self):
        for packet in [decode(fixture(b'', 0xc9)), decode(fixture(b'x')),
                       decode(fixture(struct.pack('<I', 10)+b'short'))]:
            with self.subTest(packet=packet), self.assertRaises(ValueError):
                processing_result(packet)
